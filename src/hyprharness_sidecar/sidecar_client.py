"""Async read/write client for the independent sidecar Unix RPC service."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from .sidecar import paths, MAX_REQUEST, MAX_RESPONSE


async def request(payload, *, socket_path=None, timeout=5):
    socket_path = Path(socket_path) if socket_path else paths()[0]
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) + 1 > MAX_REQUEST:
        raise ValueError("Sidecar RPC request too large")
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(socket_path),
                                                                          limit=MAX_RESPONSE+1), timeout)
    try:
        writer.write(encoded + b"\n")
        await asyncio.wait_for(writer.drain(), timeout)
        raw = await asyncio.wait_for(reader.readline(), timeout)
        if not raw.endswith(b"\n") or len(raw) > MAX_RESPONSE:
            raise RuntimeError("Invalid sidecar response")
        data = json.loads(raw)
        if data.get("ok") is not True:
            raise RuntimeError(data.get("error", "Sidecar rejected request"))
        return data["result"]
    finally:
        writer.close()
        await writer.wait_closed()
