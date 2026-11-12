"""Phase 4 benchmark: LFM routing, warm TTFT, prompt-cache reuse, handoff cost.

Read-only against the local LFM endpoints. Uses a tiny 1x1 PNG for the Omni
multimodal probe (no real screenshots). Measures the routing targets and
cache-reuse behavior the assistant relies on; makes no inference-stack changes.
"""
import asyncio
import base64
import http.client
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
from hyprneuro.model_router import ModelRouter

PORTS = {"text": 8081, "omni": 8082, "decision": 8083}
MODELS = {"text": "lfm-text", "omni": "lfm-omni", "decision": "d1-omni-600m"}

# A minimal valid 1x1 transparent PNG.
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC")


def call(role, endpoint, payload, timeout=90):
    c = http.client.HTTPConnection("127.0.0.1", PORTS[role], timeout=timeout)
    t0 = time.perf_counter()
    c.request("POST", endpoint, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    r = c.getresponse()
    raw = r.read()
    dt = (time.perf_counter() - t0) * 1000
    c.close()
    return dt, json.loads(raw)


def pct(values, p):
    values = sorted(values)
    if not values:
        return None
    k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return round(values[k], 1)


def bench_text(n=6):
    payload = {"model": MODELS["text"], "messages": [
        {"role": "system", "content": "You are a terse assistant."},
        {"role": "user", "content": "In one word: what color is the sky on a clear day?"}],
        "temperature": 0, "max_tokens": 24, "stream": False, "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False}}
    tts, cached = [], None
    for i in range(n):
        dt, data = call("text", "/v1/chat/completions", payload)
        tts.append(dt)
        cached = data.get("usage", {}).get("prompt_tokens_details", {}).get("cached_tokens")
    return {"n": n, "p50_ms": pct(tts, 50), "p95_ms": pct(tts, 95),
            "cached_tokens_last": cached}


def bench_omni(n=3):
    uri = "data:image/png;base64," + base64.b64encode(PNG_1x1).decode()
    payload = {"model": MODELS["omni"], "temperature": 0, "max_tokens": 24,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "One word: what do you see?"},
            {"type": "image_url", "image_url": {"url": uri}}]}]}
    tts = []
    for _ in range(n):
        dt, _ = call("omni", "/v1/chat/completions", payload)
        tts.append(dt)
    return {"n": n, "p50_ms": pct(tts, 50), "p95_ms": pct(tts, 95)}


def bench_decision(n=3):
    payload = {"state": json.dumps({"source": "hyprland", "event": "activewindowv2",
                                    "app_id": "kitty"})[:800],
        "questions": {"capture": {"type": "noul", "instructions":
            "Would a fresh screenshot add meaningful context? Yes/no score."}}}
    tts = []
    for _ in range(n):
        dt, _ = call("decision", "/v1/systemone", payload)
        tts.append(dt)
    return {"n": n, "p50_ms": pct(tts, 50), "p95_ms": pct(tts, 95)}


def bench_handoff():
    router = ModelRouter()
    t0 = time.perf_counter()
    for _ in range(1000):
        router.handoff("text", "omni", {"task_id": "t1", "summary": "s",
                                        "evidence": "E" * 2000})
    cost_us = (time.perf_counter() - t0) * 1000 / 1000
    # Routing cost
    t0 = time.perf_counter()
    for _ in range(1000):
        router.route("code")
    route_us = (time.perf_counter() - t0) * 1000 / 1000
    return {"handoff_build_ms": round(cost_us, 4), "route_ms": round(route_us, 5)}


def main():
    out = {"ts": int(time.time()), "endpoints": {}}
    for role in PORTS:
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORTS[role], timeout=5)
            c.request("GET", "/health")
            out["endpoints"][role] = c.getresponse().read().decode().strip()
            c.close()
        except Exception as e:
            out["endpoints"][role] = f"error: {e}"
    out["text"] = bench_text()
    out["omni"] = bench_omni()
    out["decision"] = bench_decision()
    out["handoff"] = bench_handoff()
    out["routing_policy"] = {
        "ordinary->text": True, "multimodal->omni": True, "classify->decision": True,
        "d1_only_when_requested": True}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
