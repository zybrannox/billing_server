from starlette.requests import Request

from app.rate_limiting import client_ip


def _request(peer, headers=None):
    return Request({"type": "http", "client": (peer, 5000),
                    "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]})


def test_real_ip_is_taken_from_the_tunnel_header_when_the_peer_is_loopback():
    assert client_ip(_request("127.0.0.1", {"CF-Connecting-IP": "203.0.113.7"})) == "203.0.113.7"
    assert client_ip(_request("::1", {"CF-Connecting-IP": " 203.0.113.8 "})) == "203.0.113.8"


def test_the_header_cannot_be_forged_by_a_direct_client():
    assert client_ip(_request("198.51.100.4", {"CF-Connecting-IP": "203.0.113.7"})) == "198.51.100.4"


def test_without_the_header_the_peer_is_used():
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"
