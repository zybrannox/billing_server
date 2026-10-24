"""A basic load test: hammer the main list endpoints and report latency.

    ./venv/bin/python scripts/load_test.py --base http://localhost:8000 \
        --email you@example.com --password '...' [--users 10] [--seconds 20]

Logs in once (the login route is rate limited per IP, so virtual users share
that one session; staff account, read-only GETs only - it never writes), then loops over the endpoints for the duration and prints p50/p95/p99
and error counts per endpoint. Target: p95 under 200 ms on list pages.
Point it at a copy of production data, not at production during working hours.
"""
import argparse
import asyncio
import statistics
import time
from collections import defaultdict

import httpx

ENDPOINTS = [
    "/projects/?page=1&page_size=10",
    "/invoices/?page=1&page_size=20",
    "/customers/?page=1&page_size=20",
    "/companies/?page=1&page_size=20",
    "/quotations/?page=1&page_size=20",
    "/dashboard/summary?granularity=month",
    "/dashboard/notifications/deliveries",
]


async def virtual_user(base, cookies, deadline, samples, errors):
    async with httpx.AsyncClient(
        base_url=base, timeout=30, cookies=cookies, headers={"X-Requested-With": "load-test"}
    ) as client:
        while time.monotonic() < deadline:
            for path in ENDPOINTS:
                start = time.perf_counter()
                try:
                    response = await client.get(path)
                    ok = response.status_code == 200
                except httpx.HTTPError:
                    ok = False
                elapsed_ms = (time.perf_counter() - start) * 1000
                key = path.split("?")[0]
                if ok:
                    samples[key].append(elapsed_ms)
                else:
                    errors[key] += 1


def percentile(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct / 100))]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=20)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30, headers={"X-Requested-With": "load-test"}) as client:
        login = await client.post("/auth/login", json={"email": args.email, "password": args.password})
        if login.status_code != 200:
            raise SystemExit(f"login failed: HTTP {login.status_code} {login.text[:200]}")
        cookies = dict(client.cookies)

    samples, errors = defaultdict(list), defaultdict(int)
    deadline = time.monotonic() + args.seconds
    await asyncio.gather(*(
        virtual_user(args.base, cookies, deadline, samples, errors) for _ in range(args.users)
    ))

    print(f"{'endpoint':42} {'n':>6} {'p50':>7} {'p95':>7} {'p99':>7} {'errors':>7}")
    worst_p95 = 0.0
    for path in sorted(set(samples) | set(errors)):
        values = samples.get(path, [])
        if values:
            p95 = percentile(values, 95)
            worst_p95 = max(worst_p95, p95)
            print(f"{path:42} {len(values):6d} {statistics.median(values):7.0f} {p95:7.0f} "
                  f"{percentile(values, 99):7.0f} {errors.get(path, 0):7d}")
        else:
            print(f"{path:42} {0:6d} {'-':>7} {'-':>7} {'-':>7} {errors.get(path, 0):7d}")
    verdict = "PASS" if worst_p95 <= 200 and not errors else "CHECK"
    print(f"\nworst p95: {worst_p95:.0f} ms (target <= 200 ms), errors: {sum(errors.values())} -> {verdict}")


if __name__ == "__main__":
    asyncio.run(main())
