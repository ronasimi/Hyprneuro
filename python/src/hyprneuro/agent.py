"""Agent chat: streaming LFM client for the GTK UI (Phase 6 integration).

Routes a chat to the appropriate running LFM endpoint (text:8081 / omni:8082)
and yields content deltas as they stream. Reuses the existing llama.cpp
servers; makes no inference-stack changes. Reviewed static images route to
Omni. Stdlib-only (no external dependencies), so it runs in the sidecar's
existing venv.

The GTK UI opens a connection to the sidecar and sends an ``agent_chat``
request; the sidecar streams ``{"type":"delta","text":...}`` lines followed by
a single ``{"type":"done","text":...}`` line. Deltas have an explicit
``channel`` (answer or reasoning); only answer text belongs in history.
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


class ThinkingParser:
    """Split the deployed template's <think> delimiters across arbitrary deltas.

    Hold only a possible delimiter suffix, never a whole reasoning block. Native
    reasoning_content is handled separately and does not change content state.
    """
    def __init__(self):
        self.pending = ""
        self.thinking = False

    def feed(self, text: str, *, final: bool = False):
        self.pending += text
        out = []
        while self.pending:
            token = "</think>" if self.thinking else "<think>"
            index = self.pending.find(token)
            if index >= 0:
                if index:
                    out.append(self.event(self.pending[:index]))
                self.pending = self.pending[index + len(token):]
                self.thinking = not self.thinking
                continue
            keep = 0
            if not final:
                for n in range(1, min(len(token), len(self.pending) + 1)):
                    if self.pending.endswith(token[:n]):
                        keep = n
            count = len(self.pending) - keep
            if count:
                out.append(self.event(self.pending[:count]))
                self.pending = self.pending[count:]
            break
        return out

    def event(self, text):
        return {"type": "delta", "channel": "reasoning" if self.thinking else "answer",
                "text": text}


async def _body_lines(reader, chunked, timeout_s):
    """HTTP chunk boundaries and SSE line boundaries are independent."""
    if not chunked:
        while line := await asyncio.wait_for(reader.readline(), timeout_s):
            yield line
        return
    pending = b""
    while True:
        header = await asyncio.wait_for(reader.readline(), timeout_s)
        if not header:
            raise ValueError("Chat stream closed during HTTP chunk framing")
        size = int(header.split(b";", 1)[0].strip(), 16)
        if not size:
            if pending:
                yield pending
            return
        if size > 1024 * 1024:
            raise ValueError("Oversized HTTP chunk")
        pending += await asyncio.wait_for(reader.readexactly(size), timeout_s)
        if await asyncio.wait_for(reader.readexactly(2), timeout_s) != b"\r\n":
            raise ValueError("Invalid HTTP chunk terminator")
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield line + b"\n"
        if len(pending) > 65536:
            raise ValueError("Oversized SSE line")


async def stream_chat(messages: list[dict], *, role: str = "text",
                      max_tokens: int = 1024, temperature: float = 0.2,
                      timeout_s: float = 120.0) -> AsyncIterator[dict]:
    """Yield channel-labelled deltas from the existing endpoint for `role` (text|omni).

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
        status = await asyncio.wait_for(reader.readline(), timeout_s)
        if len(status.split()) < 2 or status.split()[1] != b"200":
            raise ValueError("Chat endpoint returned a non-200 HTTP response")
        # Consume HTTP response headers.
        chunked = False
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout_s)
            if line in (b"\r\n", b"\n", b""):
                break
            if line.lower().startswith(b"transfer-encoding:"):
                chunked = b"chunked" in line.lower()
        # Stream the SSE body. Do not turn an interrupted stream into success.
        parser = ThinkingParser()
        complete = False
        async for line in _body_lines(reader, chunked, timeout_s):
            text = line.decode("utf-8", "replace").strip()
            if not text.startswith("data:"):
                continue
            data = text[len("data:"):].strip()
            if data == "[DONE]":
                complete = True
                break
            try:
                obj = json.loads(data)
            except (ValueError, TypeError):
                continue
            if not isinstance(obj, dict):
                raise ValueError("Invalid chat stream object")
            if obj.get("error"):
                raise ValueError("Chat endpoint reported a stream error")
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    yield {"type": "delta", "channel": "reasoning", "text": reasoning}
                content = delta.get("content")
                if isinstance(content, str):
                    for event in parser.feed(content):
                        yield event
            # Capture timings/usage from the final chunk (present on finish).
            timings = obj.get("timings")
            usage = obj.get("usage")
            if timings or usage:
                metrics = {}
                if isinstance(timings, dict):
                    if "prompt_per_second" in timings:
                        metrics["prefill_tps"] = round(timings["prompt_per_second"], 1)
                    if "predicted_per_second" in timings:
                        metrics["decode_tps"] = round(timings["predicted_per_second"], 1)
                    cache_n = timings.get("cache_n", 0)
                    prompt_n = timings.get("prompt_n", 0)
                    if prompt_n and cache_n:
                        metrics["cache_hit_pct"] = round(100 * cache_n / prompt_n, 1)
                if isinstance(usage, dict) and "cache_hit_pct" not in metrics:
                    pt = usage.get("prompt_tokens_details") or {}
                    cached = pt.get("cached_tokens", 0)
                    total_pt = usage.get("prompt_tokens", 0)
                    if total_pt:
                        metrics["cache_hit_pct"] = round(100 * cached / total_pt, 1)
                if metrics:
                    yield {"type": "metrics", **metrics}
        for event in parser.feed("", final=True):
            yield event
        if not complete:
            raise ValueError("Chat stream ended before [DONE]")
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
