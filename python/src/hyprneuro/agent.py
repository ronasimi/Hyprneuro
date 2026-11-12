"""Agent chat: streaming LFM client for the GTK UI (Phase 6 integration).

Routes a chat to the appropriate running LFM endpoint (text:8081 / omni:8082)
and yields content deltas as they stream. Reuses the existing llama.cpp
servers; makes no inference-stack changes. Media (images/audio) routes to
Omni. Stdlib-only (no external dependencies), so it runs in the sidecar's
existing venv.

The GTK UI opens a connection to the sidecar and sends an ``agent_chat``
request; the sidecar streams ``{"type":"delta","text":...}`` lines followed by
a single ``{"type":"done","text":...}`` line.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

HOST = "127.0.0.1"
# role -> (port, model-id). Verified against the live endpoints.
ENDPOINTS = {
    "text": (8081, "lfm-text"),
    "omni": (8082, "lfm-omni"),
}
DEFAULT_SYSTEM = (
    "You are Hyprneuro, a local, application-aware assistant running on the "
    "user's Hyprland desktop. Be concise and helpful. You have local context "
    "about the focused application and system state; use it when relevant. "
    "Never reveal that you are a local small model unless asked."
)


async def stream_chat(messages: list[dict], *, role: str = "text",
                      max_tokens: int = 1024, temperature: float = 0.2,
                      timeout_s: float = 120.0) -> AsyncIterator[str]:
    """Yield content deltas from the LFM endpoint for `role` (text|omni).

    Uses a raw asyncio TCP connection + manual SSE parsing so no external
    HTTP client is required. Yields nothing on a clean [DONE] with no content.
    """
    if role not in ENDPOINTS:
        raise ValueError("role must be text or omni")
    port, model = ENDPOINTS[role]
    payload: dict = {
        "model": model, "messages": messages, "stream": True,
        "max_tokens": int(max_tokens), "temperature": float(temperature),
    }
    if role == "text":
        # Match the existing LFM text config (no thinking tokens in the reply).
        payload["cache_prompt"] = True
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    reader, writer = await asyncio.wait_for(asyncio.open_connection(HOST, port), 5)
    try:
        body = json.dumps(payload).encode("utf-8")
        req = (f"POST /v1/chat/completions HTTP/1.1\r\n"
               f"Host: {HOST}:{port}\r\n"
               f"Content-Type: application/json\r\n"
               f"Content-Length: {len(body)}\r\n"
               f"Connection: close\r\n\r\n").encode("ascii") + body
        writer.write(req)
        await asyncio.wait_for(writer.drain(), timeout_s)
        # Consume HTTP response headers.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout_s)
            if line in (b"\r\n", b"\n", b""):
                break
        # Stream the SSE body.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout_s)
            if not line:
                break
            text = line.decode("utf-8", "replace").strip()
            if not text.startswith("data:"):
                continue
            data = text[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except (ValueError, TypeError):
                continue
            choices = obj.get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    yield delta
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def health(role: str = "text") -> bool:
    """True if the endpoint for `role` answers /health."""
    port, _ = ENDPOINTS.get(role, (8081, ""))
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(HOST, port), 3)
        try:
            writer.write(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                         b"Connection: close\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.readline(), 3)
            return b"200" in data
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
    except (OSError, asyncio.TimeoutError):
        return False
