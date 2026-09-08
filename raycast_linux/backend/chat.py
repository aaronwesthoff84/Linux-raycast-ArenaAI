"""Central agent chat service supporting Hermes backend with history and streaming.

Adheres to standard OpenAI-compatible chat completion APIs exposed by Hermes Agent:
  https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import AsyncIterator

import httpx

from . import storage

log = logging.getLogger("raycast-linux.chat")

DEFAULT_ENDPOINT = "http://127.0.0.1:8642"
DEFAULT_MODEL = "nousresearch/hermes-3-llama-3.1-8b"


class ChatService:
    """Manages chat conversations, secure provider configuration, and Hermes generation."""

    def __init__(self, data_path: str | None = None) -> None:
        base_dir = data_path or storage.data_dir()
        self._conv_store = storage.JsonStore(
            os.path.join(base_dir, "chat_conversations.json"),
            default=[],
        )
        self._config_store = storage.JsonStore(
            os.path.join(base_dir, "chat_config.json"),
            default={
                "provider": "hermes",
                "endpoint": DEFAULT_ENDPOINT,
                "api_key": "",
                "model": DEFAULT_MODEL,
            },
        )
        self._active_tasks: dict[str, asyncio.Event] = {}

    # -- Configuration --------------------------------------------------------
    def get_config(self, mask_key: bool = True) -> dict:
        cfg = dict(self._config_store.load())
        if mask_key and cfg.get("api_key"):
            key = cfg["api_key"]
            if len(key) > 6:
                cfg["api_key"] = key[:3] + "..." + key[-3:]
            else:
                cfg["api_key"] = "***"
        return cfg

    def update_config(self, **kwargs) -> dict:
        cfg = dict(self._config_store.load())
        for k, v in kwargs.items():
            if v is not None and k in ("provider", "endpoint", "api_key", "model"):
                cfg[k] = str(v).strip()
        self._config_store.save(cfg)
        return self.get_config(mask_key=True)

    # -- Conversations History ------------------------------------------------
    def list_conversations(self) -> list[dict]:
        convs = self._conv_store.load()
        return [
            {
                "id": c["id"],
                "title": c.get("title", "Conversation"),
                "created_at": c.get("created_at", 0),
                "updated_at": c.get("updated_at", 0),
                "message_count": len(c.get("messages", [])),
            }
            for c in sorted(convs, key=lambda x: x.get("updated_at", 0), reverse=True)
        ]

    def create_conversation(self, title: str = "New Chat") -> dict:
        convs = list(self._conv_store.load())
        now = time.time()
        conv = {
            "id": f"conv_{uuid.uuid4().hex[:12]}",
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        convs.append(conv)
        self._conv_store.save(convs)
        return conv

    def get_conversation(self, conv_id: str) -> dict | None:
        convs = self._conv_store.load()
        for c in convs:
            if c["id"] == conv_id:
                return c
        return None

    def delete_conversation(self, conv_id: str) -> bool:
        convs = list(self._conv_store.load())
        initial_len = len(convs)
        convs = [c for c in convs if c["id"] != conv_id]
        if len(convs) != initial_len:
            self._conv_store.save(convs)
            return True
        return False

    def clear_conversation(self, conv_id: str) -> bool:
        convs = list(self._conv_store.load())
        for c in convs:
            if c["id"] == conv_id:
                c["messages"] = []
                c["updated_at"] = time.time()
                self._conv_store.save(convs)
                return True
        return False

    def add_message(self, conv_id: str, role: str, content: str) -> dict | None:
        convs = list(self._conv_store.load())
        for c in convs:
            if c["id"] == conv_id:
                msg = {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "role": role,
                    "content": content,
                    "timestamp": time.time(),
                }
                c.setdefault("messages", []).append(msg)
                c["updated_at"] = msg["timestamp"]
                if len(c["messages"]) == 1 and role == "user":
                    # Derive title from first user prompt
                    first_line = content.strip().split("\n")[0][:40]
                    c["title"] = first_line or "New Chat"
                self._conv_store.save(convs)
                return msg
        return None

    # -- Generation & Cancellation -------------------------------------------
    def cancel(self, conv_id: str) -> bool:
        event = self._active_tasks.get(conv_id)
        if event:
            event.set()
            return True
        return False

    async def send_message(
        self,
        conv_id: str,
        prompt: str,
        stream: bool = False,
    ) -> dict | AsyncIterator[str]:
        conv = self.get_conversation(conv_id)
        if not conv:
            raise ValueError(f"Conversation {conv_id} not found")

        self.add_message(conv_id, "user", prompt)
        conv = self.get_conversation(conv_id)
        messages_payload = [
            {"role": m["role"], "content": m["content"]}
            for m in conv.get("messages", [])
        ]

        cfg = self._config_store.load()
        endpoint = cfg.get("endpoint", DEFAULT_ENDPOINT).rstrip("/")
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", DEFAULT_MODEL)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": messages_payload,
            "stream": stream,
        }

        cancel_event = asyncio.Event()
        self._active_tasks[conv_id] = cancel_event

        if not stream:
            return await self._call_sync(conv_id, endpoint, headers, payload, cancel_event)
        else:
            return self._call_stream(conv_id, endpoint, headers, payload, cancel_event)

    async def _call_sync(
        self,
        conv_id: str,
        endpoint: str,
        headers: dict,
        payload: dict,
        cancel_event: asyncio.Event,
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                task = asyncio.create_task(
                    client.post(f"{endpoint}/v1/chat/completions", json=payload, headers=headers)
                )
                while not task.done():
                    if cancel_event.is_set():
                        task.cancel()
                        self.add_message(conv_id, "assistant", "[Generation cancelled by user]")
                        return {"ok": False, "cancelled": True, "message": "Cancelled"}
                    await asyncio.sleep(0.05)

                resp = await task
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                msg = self.add_message(conv_id, "assistant", content)
                return {"ok": True, "message": msg, "model": payload.get("model", "")}
        except httpx.ConnectError:
            err_msg = f"Cannot connect to Hermes API server at {endpoint}. Ensure the server is running."
            self.add_message(conv_id, "assistant", f"[Error: {err_msg}]")
            return {"ok": False, "error": err_msg}
        except httpx.HTTPStatusError as e:
            err_msg = f"Hermes API error: HTTP {e.response.status_code} - {e.response.text}"
            self.add_message(conv_id, "assistant", f"[Error: {err_msg}]")
            return {"ok": False, "error": err_msg}
        except Exception as e:
            err_msg = f"Unexpected error communicating with Hermes: {e}"
            self.add_message(conv_id, "assistant", f"[Error: {err_msg}]")
            return {"ok": False, "error": err_msg}
        finally:
            self._active_tasks.pop(conv_id, None)

    async def _call_stream(
        self,
        conv_id: str,
        endpoint: str,
        headers: dict,
        payload: dict,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[str]:
        accumulated: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    f"{endpoint}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if cancel_event.is_set():
                            yield json.dumps({"chunk": "", "cancelled": True}) + "\n"
                            accumulated.append(" [Cancelled]")
                            break
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            raw = line[6:].strip()
                            if raw == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(raw)
                                delta = chunk_data["choices"][0]["delta"].get("content", "")
                                if delta:
                                    accumulated.append(delta)
                                    yield json.dumps({"chunk": delta, "cancelled": False}) + "\n"
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except httpx.ConnectError:
            err = f"Cannot connect to Hermes API server at {endpoint}."
            yield json.dumps({"error": err}) + "\n"
            accumulated.append(f"[Error: {err}]")
        except Exception as e:
            err = f"Streaming error: {e}"
            yield json.dumps({"error": err}) + "\n"
            accumulated.append(f"[Error: {err}]")
        finally:
            full_text = "".join(accumulated)
            if full_text:
                self.add_message(conv_id, "assistant", full_text)
            self._active_tasks.pop(conv_id, None)
