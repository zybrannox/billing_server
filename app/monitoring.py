"""Optional error tracking (Sentry).

Off unless SENTRY_DSN is set, so development and tests never report anything.
Reports unhandled exceptions with the route and a stack trace, but never
request bodies, cookies or headers (send_default_pii is off and the request
data is stripped below): a failed payment request must not ship a customer's
details, an auth cookie or a password to a third party.
"""
import os


def _scrub(event, hint):
    request = event.get("request")
    if request:
        for key in ("data", "cookies", "headers", "query_string"):
            request.pop(key, None)
    return event


def init_monitoring() -> bool:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENVIRONMENT", "development"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
        before_send=_scrub,
    )
    return True
