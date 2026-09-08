"""Tests for Hermes Chat Service and backend API endpoints."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from raycast_linux.backend.chat import ChatService
from raycast_linux.backend.server import ServiceHub, build_app


@pytest.fixture()
def chat_service(tmp_path):
    return ChatService(data_path=str(tmp_path))


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return ServiceHub()


@pytest.fixture()
def client(hub):
    app = build_app(hub)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ Unit tests
def test_chat_config_defaults_and_masking(chat_service):
    cfg = chat_service.get_config(mask_key=True)
    assert cfg["provider"] == "hermes"
    assert "endpoint" in cfg
    assert cfg["api_key"] == ""

    # Short key
    chat_service.update_config(api_key="12345")
    assert chat_service.get_config(mask_key=True)["api_key"] == "***"
    assert chat_service.get_config(mask_key=False)["api_key"] == "12345"

    # Longer key
    chat_service.update_config(api_key="sk-hermes-secret-key-123456789")
    masked = chat_service.get_config(mask_key=True)["api_key"]
    assert masked.startswith("sk-")
    assert masked.endswith("789")
    assert "..." in masked


def test_chat_config_update(chat_service):
    updated = chat_service.update_config(
        endpoint="http://192.168.1.10:8000/v1",
        model="custom-hermes-model",
    )
    assert updated["endpoint"] == "http://192.168.1.10:8000/v1"
    assert updated["model"] == "custom-hermes-model"


def test_conversation_crud_and_title_derivation(chat_service):
    conv = chat_service.create_conversation("Initial Chat")
    conv_id = conv["id"]
    assert conv["title"] == "Initial Chat"

    listed = chat_service.list_conversations()
    assert len(listed) == 1
    assert listed[0]["id"] == conv_id

    # Add user message -> title updates if first message
    msg = chat_service.add_message(conv_id, "user", "How do I list files in Python?\nSecond line")
    assert msg["role"] == "user"
    c = chat_service.get_conversation(conv_id)
    assert c["title"] == "How do I list files in Python?"
    assert len(c["messages"]) == 1

    # Add assistant response
    chat_service.add_message(conv_id, "assistant", "Use os.listdir() or pathlib.Path.")
    c = chat_service.get_conversation(conv_id)
    assert len(c["messages"]) == 2

    # Clear conversation
    assert chat_service.clear_conversation(conv_id) is True
    c = chat_service.get_conversation(conv_id)
    assert len(c["messages"]) == 0

    # Delete conversation
    assert chat_service.delete_conversation(conv_id) is True
    assert chat_service.get_conversation(conv_id) is None
    assert len(chat_service.list_conversations()) == 0


def test_send_message_sync_mock(chat_service):
    async def _test():
        conv = chat_service.create_conversation("Hermes Test")
        conv_id = conv["id"]

        mock_resp = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello from mock Hermes!",
                    }
                }
            ]
        }

        mock_http_response = httpx.Response(
            200,
            json=mock_resp,
            request=httpx.Request("POST", "http://localhost"),
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_http_response
            result = await chat_service.send_message(conv_id, "Hello Hermes", stream=False)

            assert result["ok"] is True
            assert result["message"]["content"] == "Hello from mock Hermes!"

            # Check saved in conversation history
            conv = chat_service.get_conversation(conv_id)
            assert len(conv["messages"]) == 2
            assert conv["messages"][0]["role"] == "user"
            assert conv["messages"][1]["role"] == "assistant"

    import asyncio
    asyncio.run(_test())


def test_send_message_connection_error(chat_service):
    async def _test():
        conv = chat_service.create_conversation("Error Test")
        conv_id = conv["id"]

        with patch.object(httpx.AsyncClient, "post", side_effect=httpx.ConnectError("Connection refused")):
            result = await chat_service.send_message(conv_id, "Ping", stream=False)
            assert result["ok"] is False
            assert "Cannot connect" in result["error"]

    import asyncio
    asyncio.run(_test())


# -------------------------------------------------------- API endpoint tests
def test_api_chat_endpoints(client):
    # Config
    cfg = client.get("/api/chat/config").json()
    assert cfg["provider"] == "hermes"

    update_res = client.post(
        "/api/chat/config",
        json={"endpoint": "http://hermes.local:8000/v1", "model": "hermes-fast"},
    ).json()
    assert update_res["endpoint"] == "http://hermes.local:8000/v1"
    assert update_res["model"] == "hermes-fast"

    # Conversations
    create_res = client.post("/api/chat/conversations", json={"title": "Web Test"}).json()
    conv_id = create_res["id"]

    get_res = client.get(f"/api/chat/conversations/{conv_id}").json()
    assert get_res["id"] == conv_id

    list_res = client.get("/api/chat/conversations").json()
    assert any(c["id"] == conv_id for c in list_res)

    # Clear
    clear_res = client.post(f"/api/chat/conversations/{conv_id}/clear").json()
    assert clear_res["ok"] is True

    # Cancel
    cancel_res = client.post(f"/api/chat/conversations/{conv_id}/cancel").json()
    assert "ok" in cancel_res

    # Delete
    del_res = client.delete(f"/api/chat/conversations/{conv_id}").json()
    assert del_res["ok"] is True

    # 404 for missing
    assert client.get(f"/api/chat/conversations/{conv_id}").status_code == 404
