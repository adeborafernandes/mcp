import importlib
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

ISSUER = "https://demo.authkit.app"
PUBLIC = "https://mcp.example.com/mcp"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", ISSUER)
    monkeypatch.setenv("MCP_PUBLIC_URL", PUBLIC)
    monkeypatch.setenv("MCP_ALLOWED_EMAILS", "eu@exemplo.com")
    monkeypatch.setenv("MCP_ALLOWED_SUBS", "user_ok")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "")
    import proxy
    importlib.reload(proxy)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeKey:
        def __init__(self, k): self.key = k

    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return FakeKey(key.public_key())

    proxy.jwks = FakeJwks()
    proxy.client = httpx.AsyncClient(
        base_url="http://up",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=httpx.ByteStream(b'{"via":"upstream"}'))),
    )
    return proxy, key


def tok(key, **over):
    claims = {"iss": ISSUER, "aud": PUBLIC, "sub": "user_ok", "exp": int(time.time()) + 300}
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256")


def call(proxy, token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(proxy.app).post("/mcp", headers=h, json={})


def test_valid_by_sub(env):
    p, k = env
    assert call(p, tok(k)).status_code == 200


def test_valid_by_email(env):
    p, k = env
    assert call(p, tok(k, sub="outro", email="EU@exemplo.com")).status_code == 200


def test_no_token_401_with_metadata(env):
    p, _ = env
    r = call(p)
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers["www-authenticate"]


def test_not_allowed_403(env):
    p, k = env
    assert call(p, tok(k, sub="intruso", email="x@y.com")).status_code == 403


@pytest.mark.parametrize("over", [{"exp": 1}, {"aud": "https://outro"}, {"iss": "https://evil"}])
def test_bad_claims_401(env, over):
    p, k = env
    assert call(p, tok(k, **over)).status_code == 401


def test_wrong_signature_401(env):
    p, _ = env
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert call(p, tok(other)).status_code == 401


def test_metadata_and_health(env):
    p, _ = env
    c = TestClient(p.app)
    m = c.get("/.well-known/oauth-protected-resource/mcp").json()
    assert m["resource"] == PUBLIC and m["authorization_servers"] == [ISSUER]
    assert c.get("/healthz").status_code == 200


def test_fail_closed_without_allowlist(monkeypatch, env):
    p, k = env
    monkeypatch.setattr(p, "OAUTH_ENABLED", False)
    assert call(p, tok(k)).status_code == 401
