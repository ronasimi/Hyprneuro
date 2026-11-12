"""Phase 9 final scorecard.

Produces a single JSON scorecard mapping each production acceptance criterion
to a measured value or a structural guarantee, with the evidence reference.
Read-only against the local LFM endpoints; makes no inference-stack changes.
"""
import http.client
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python" / "src"))
from hyprneuro.model_router import ModelRouter

PORTS = {"text": 8081, "omni": 8082, "decision": 8083}
MODELS = {"text": "lfm-text", "omni": "lfm-omni", "decision": "d1-omni-600m"}


def pct(values, p):
    values = sorted(values)
    if not values:
        return None
    k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return round(values[k], 2)


def http_health(role):
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORTS[role], timeout=5)
        c.request("GET", "/health")
        body = c.getresponse().read().decode().strip()
        c.close()
        return body
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def ttft(role, payload, n=4):
    ts = []
    for _ in range(n):
        c = http.client.HTTPConnection("127.0.0.1", PORTS[role], timeout=60)
        t0 = time.perf_counter()
        c.request("POST", {"text": "/v1/chat/completions", "omni": "/v1/chat/completions",
                            "decision": "/v1/systemone"}[role],
                  json.dumps(payload).encode(), {"Content-Type": "application/json"})
        c.getresponse().read()
        ts.append((time.perf_counter() - t0) * 1000)
        c.close()
    return {"p50_ms": pct(ts, 50), "p95_ms": pct(ts, 95), "n": n}


def routing_cost():
    router = ModelRouter()
    t0 = time.perf_counter()
    for _ in range(2000):
        router.route("code")
    route_ms = (time.perf_counter() - t0) * 1000 / 2000
    d1_invoked = 0
    for kind in ("chat", "code", "tool", "general", "vision"):
        d1_invoked += 1 if router.route(kind) == "decision" else 0
    return {"route_ms": round(route_ms, 5), "d1_invoked_for_ordinary_kinds": d1_invoked}


def test_count():
    try:
        p = subprocess.run([str(REPO / "python/.venv/bin/python"), "-m", "pytest", "tests/", "-q"],
                           cwd=REPO / "python", capture_output=True, text=True, timeout=300)
        last = [ln for ln in p.stdout.splitlines() if "passed" in ln][-1]
        return last.strip()
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def main():
    out = {"ts": int(time.time()), "schema": "hyprneuro.scorecard/1"}
    out["endpoints"] = {r: http_health(r) for r in PORTS}
    out["latency"] = {
        "text": ttft("text", {"model": MODELS["text"], "messages": [
            {"role": "user", "content": "One word: sky?"}], "max_tokens": 8,
            "temperature": 0, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False}}),
        "decision": ttft("decision", {"state": json.dumps({"source": "hyprland",
            "event": "activewindowv2"})[:600],
            "questions": {"capture": {"type": "noul", "instructions": "Yes/no"}}}),
    }
    out["routing"] = routing_cost()
    out["tests"] = test_count()
    # Structural guarantees (enforced by code + unit/integration tests, not measured here):
    out["structural"] = {
        "no_llm_on_focus": "AppRegistry/AppWatcher perform zero inference on focus events (metadata only); tested in test_application.py",
        "unauthorized_actions_blocked": "PermissionBroker: privileged ops require recorded approval; desktop actions gated by auth+lease+focus (test_authorization.py, test_desktop_control.py)",
        "desktop_control_lease": "Exclusive, time-bounded, pausable, fail-closed on restart (test_desktop_control.py)",
        "assistant_opt_in": "assistant_enabled defaults False; all assistant IPC raises when disabled (test_assistant_ipc.py)",
        "no_second_runtime": "Pi Durable subagents execute; Hyprneuro provides context/state/IPC only (extensions/app-aware.ts)",
        "schema_version": 3,
        "prompt_cache_reuse": "measured per-benchmark; cross-request KV reuse recorded as optimization target (no model-stack change)",
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
