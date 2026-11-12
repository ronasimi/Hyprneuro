"""Level 3 live validation: run the real sidecar against the live compositor.

Read-only. No screenshots, no model calls. Uses a throwaway socket/db path so
it never clobbers any existing installation. The Hyprland adapter uses the real
XDG_RUNTIME_DIR + HYPRLAND_INSTANCE_SIGNATURE from the environment.
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
from hyprneuro.sidecar import serve
from hyprneuro.sidecar_client import request
from hyprneuro.desktop import Hyprland


async def main():
    tmp = tempfile.mkdtemp(prefix="hyprneuro-live-")
    root = Path(tmp)
    socket = root / "sidecar.sock"
    db = root / "state" / "live.sqlite3"
    skills = root / "skills"
    skills.mkdir()
    (skills / "google-chrome.json").write_text(json.dumps({
        "app_id": "google-chrome", "name": "Chrome", "description": "Browser",
        "version": "1", "tags": ["browser"], "body": "Chrome skill body",
        "tools_schema": {"type": "object"}}))

    stop = asyncio.Event()
    service = asyncio.create_task(serve(
        allow_ingest=True, watch_hyprland=True, assistant_enabled=True,
        assistant_recent_apps=5, socket_path=socket, db_path=db,
        shutdown=stop, skills_dir=str(skills)))

    # Wait for the socket.
    for _ in range(200):
        if socket.exists():
            break
        await asyncio.sleep(0.02)
    assert socket.exists(), "sidecar socket did not appear"

    report = {"socket": str(socket), "db": str(db)}

    # 1. Health.
    health = await request({"action": "health"}, socket_path=socket)
    report["health"] = {k: health.get(k) for k in
                        ("service", "assistant_enabled", "assistant_apps", "ingest_enabled")}

    # 2. Real focused window (ground truth) via the compositor directly.
    desktop = Hyprland()
    ground = await desktop.query("activewindow")
    report["ground_truth"] = {
        "class": ground.get("class"), "title": (ground.get("title") or "")[:80],
        "workspace": (ground.get("workspace") or {}).get("id"),
        "address": ground.get("address")}

    # 3. app_context via IPC should reflect the real focus (model-free).
    ctx = None
    for _ in range(100):
        ctx = await request({"action": "app_context"}, socket_path=socket)
        if ctx["focused"] and ctx["focused"]["app_class"] == ground.get("class"):
            break
        await asyncio.sleep(0.05)
    report["app_context"] = ctx
    match = ctx and ctx["focused"] and ctx["focused"]["app_class"] == ground.get("class")
    report["focus_match"] = bool(match)

    # 4. Skill discovery for the focused app.
    report["skill_discover"] = await request({"action": "skill_discover"}, socket_path=socket)

    # 5. Memory roundtrip over live IPC.
    await request({"action": "memory_remember", "scope": "app", "key": "live.probe",
                   "value": {"ok": True}, "app_id": "google-chrome"}, socket_path=socket)
    report["memory_recall"] = await request({"action": "memory_recall", "scope": "app",
                                             "app_id": "google-chrome"}, socket_path=socket)

    # 6. Durable task record over live IPC.
    created = await request({"action": "task_create", "goal": "Live validation task",
                             "state": {"app_id": ground.get("class")}}, socket_path=socket)
    report["task_created"] = created
    report["task_get"] = await request({"action": "task_get", "id": created["id"]},
                                       socket_path=socket)

    # 7. Latency: 20 paired app_context trials (warm, read-only).
    trials = []
    for _ in range(20):
        t0 = time.perf_counter()
        await request({"action": "app_context"}, socket_path=socket)
        trials.append((time.perf_counter() - t0) * 1000)
    trials.sort()
    report["app_context_latency_ms"] = {
        "n": len(trials), "p50": round(trials[len(trials)//2], 2),
        "p95": round(trials[int(len(trials)*0.95)], 2), "max": round(trials[-1], 2)}

    stop.set()
    await asyncio.wait_for(service, 5)
    print(json.dumps(report, indent=2, default=str))
    print("FOCUS_MATCH:", report["focus_match"])


if __name__ == "__main__":
    asyncio.run(main())
