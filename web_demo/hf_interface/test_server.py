from fastapi.testclient import TestClient

from . import server


client = TestClient(server.app)


def test_config_points_at_realtime_server() -> None:
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["s2sUrl"] == (server.SPEECH_TO_SPEECH_URL or "ws://testserver/v1/realtime")
    assert body["allowDirect"] is True
    assert body["lb"] is False
    assert body["rtc"] is False


def test_interface_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ConvFill Realtime" in response.text


def test_search_requires_a_key(monkeypatch) -> None:
    monkeypatch.setattr(server, "SERPER_API_KEY", "")
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 503


def test_agents_sdk_bundle_is_served() -> None:
    response = client.get("/vendor/openai-realtime-agents.umd.js")
    assert response.status_code == 200
    assert "OpenAIAgentsRealtime" in response.text


def test_https_config_uses_secure_same_origin_socket():
    with TestClient(server.app, base_url="https://voice.example") as secure:
        body = secure.get("/api/config").json()
        assert body["s2sUrl"] == (server.SPEECH_TO_SPEECH_URL or "wss://voice.example/v1/realtime")
        assert "api_key" not in str(body).lower()


def test_readiness_requires_pipeline_and_both_model_services(monkeypatch):
    import httpx
    original = httpx.AsyncClient
    seen = []
    def respond(request):
        seen.append(request.url.path)
        if request.url.path == "/v1/pool":
            return httpx.Response(200, json={"available": 1})
        return httpx.Response(503)
    monkeypatch.setenv("CONVFILL_REASONER_URL", "https://reasoner/v1")
    def make_client(**kwargs):
        kwargs.pop("transport", None)
        return original(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(server.httpx, "AsyncClient", make_client)
    assert client.get("/readyz").status_code == 503
    assert seen == ["/v1/pool", "/v1/models"]


def test_websocket_admission_forwarding_and_reconnect(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from starlette.websockets import WebSocketDisconnect
    import pytest

    class Backend:
        def __init__(self):
            self.messages = asyncio.Queue()
        async def send(self, value):
            await self.messages.put(value)
        def __aiter__(self):
            return self
        async def __anext__(self):
            return await self.messages.get()

    @asynccontextmanager
    async def connect(*args, **kwargs):
        yield Backend()

    monkeypatch.setattr(server.websockets, "connect", connect)
    with TestClient(server.app) as live:
        with live.websocket_connect("/v1/realtime") as first:
            first.send_text("first-session")
            assert first.receive_text() == "first-session"
            with pytest.raises(WebSocketDisconnect) as rejected:
                with live.websocket_connect("/v1/realtime"):
                    pass
            assert rejected.value.code == 1013
        with live.websocket_connect("/v1/realtime") as second:
            second.send_text("clean-reconnect")
            assert second.receive_text() == "clean-reconnect"
    assert server._session_active is False


def test_websocket_rejects_cross_origin_browser():
    from starlette.websockets import WebSocketDisconnect
    import pytest
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect("/v1/realtime", headers={"origin": "https://untrusted.example"}):
            pass
    assert rejected.value.code == 1008


def test_websocket_access_grants_are_redacted_from_logs():
    import logging
    record = logging.LogRecord("uvicorn.error", logging.INFO, "", 0,
                               'WebSocket %s [accepted]',
                               ('/v1/realtime?__sign=temporary-grant&model=s2s',), None)
    assert server.RedactAccessGrants().filter(record)
    assert "temporary-grant" not in record.getMessage()
    assert "model=s2s" in record.getMessage()
