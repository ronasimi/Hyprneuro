"""`hyprneuro-assistant` CLI — the hotkey entry point (Phase 6).

A thin, stateless command over the assistant controller. A Hyprland hotkey
binds a key to one of these, e.g.:

    exec hyprneuro-assistant status      # show focus + tasks + approvals
    exec hyprneuro-assistant stop        # emergency stop (lease + active task)
    exec hyprneuro-assistant stream 3    # follow a task's progress

Every command is read-only or fail-safe; none performs inference. Output is
compact JSON so a native Wayland UI (or a quick terminal) can render it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .assistant_controller import AssistantController
from .sidecar_client import request, paths


def _controller(socket_path: str | None) -> AssistantController:
    sock = Path(socket_path) if socket_path else paths()[0]
    return AssistantController(lambda payload, **kw: request(payload, socket_path=sock))


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


async def _run(args: argparse.Namespace) -> int:
    c = _controller(args.socket)
    if args.cmd == "status":
        _print(await c.status())
    elif args.cmd == "tasks":
        _print(await c.tasks())
    elif args.cmd == "select":
        _print(await c.select_task(args.id))
    elif args.cmd == "stream":
        updates = []
        await c.stream(args.id, updates.append, max_polls=args.max_polls)
        _print({"updates": updates})
    elif args.cmd == "request-approval":
        a = await c.request_approval(args.task_id, args.op, args.reason or "")
        _print({**a, "note": "confirm in the assistant UI session; "
                             "approval ids are per-controller-instance"})
    elif args.cmd == "pause":
        _print(await c.pause(args.id))
    elif args.cmd == "resume":
        _print(await c.resume(args.id))
    elif args.cmd == "stop":
        _print(await c.emergency_stop())
    else:  # pragma: no cover
        raise SystemExit(2)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hyprneuro-assistant",
                                description="Hotkey entry point for the Hyprneuro assistant.")
    p.add_argument("--socket", default=None, help="sidecar socket path (default: configured)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="focus + tasks + approvals + telemetry snapshot")
    sub.add_parser("tasks", help="list durable tasks")
    for name in ("select", "stream", "pause", "resume"):
        sp = sub.add_parser(name)
        sp.add_argument("id")
        if name == "stream":
            sp.add_argument("--max-polls", type=int, default=60)
    ra = sub.add_parser("request-approval")
    ra.add_argument("task_id")
    ra.add_argument("op")
    ra.add_argument("reason", nargs="?")
    sub.add_parser("stop", help="emergency stop: clear desktop lease + pause active task")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
