import json
import sys
import types
from pathlib import Path

from solstice_agent.gateway.channels.email_channel import EmailChannel


class _FakeCache:
    def __init__(self):
        self.payload = ""

    def deserialize(self, payload: str):
        self.payload = payload


class _FakeApp:
    def __init__(self, result):
        self._result = result

    def get_accounts(self):
        return [{"username": "agent@example.com"}]

    def acquire_token_silent(self, scopes, account):
        return self._result


def _install_fake_msal(monkeypatch, result, capture):
    def _public_client_application(client_id, authority, token_cache):
        capture["client_id"] = client_id
        capture["authority"] = authority
        capture["cache_payload"] = getattr(token_cache, "payload", "")
        return _FakeApp(result)

    fake_msal = types.SimpleNamespace(
        SerializableTokenCache=_FakeCache,
        PublicClientApplication=_public_client_application,
    )
    monkeypatch.setitem(sys.modules, "msal", fake_msal)


def test_email_channel_uses_shared_graph_cache(tmp_path, monkeypatch):
    capture = {}
    _install_fake_msal(monkeypatch, {"access_token": "cached-token"}, capture)

    credentials_path = tmp_path / "outlook_credentials.json"
    cache_path = tmp_path / "outlook_token.json"
    credentials_path.write_text(json.dumps({"client_id": "client-123"}), encoding="utf-8")
    cache_path.write_text('{"cached": true}', encoding="utf-8")

    channel = EmailChannel(
        {
            "email": "agent@example.com",
            "provider": "graph",
            "graph_credentials_path": str(credentials_path),
            "graph_cache_path": str(cache_path),
        }
    )

    assert channel._get_graph_token() == "cached-token"
    assert capture["client_id"] == "client-123"
    assert capture["cache_payload"] == '{"cached": true}'


def test_email_channel_prefers_explicit_graph_token(tmp_path):
    credentials_path = tmp_path / "outlook_credentials.json"
    cache_path = tmp_path / "outlook_token.json"
    credentials_path.write_text(json.dumps({"client_id": "client-123"}), encoding="utf-8")
    cache_path.write_text('{"cached": true}', encoding="utf-8")

    channel = EmailChannel(
        {
            "email": "agent@example.com",
            "provider": "graph",
            "graph_token": "explicit-token",
            "graph_credentials_path": str(credentials_path),
            "graph_cache_path": str(cache_path),
        }
    )

    assert channel._get_graph_token() == "explicit-token"


def test_email_channel_reports_shared_cache_scope_failure(tmp_path, monkeypatch):
    capture = {}
    _install_fake_msal(monkeypatch, {"error": "interaction_required"}, capture)

    credentials_path = tmp_path / "outlook_credentials.json"
    cache_path = tmp_path / "outlook_token.json"
    credentials_path.write_text(json.dumps({"client_id": "client-123"}), encoding="utf-8")
    cache_path.write_text('{"cached": true}', encoding="utf-8")

    channel = EmailChannel(
        {
            "email": "agent@example.com",
            "provider": "graph",
            "graph_credentials_path": str(credentials_path),
            "graph_cache_path": str(cache_path),
        }
    )

    result = channel.create_draft("contact@example.com", "test body", {"subject": "test"})

    assert result["success"] is False
    assert "Mail.Send" in result["error"]
    assert "shared MSAL cache" in result["error"]
