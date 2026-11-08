"""Independent, optional Hyprneuro observational sidecar.

It provides metadata storage and read-only, bounded context feeds for
LFM3 text and Omni without launching either model or a new Pi agent loop.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from dataclasses import asdict, fields
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import time

from .sidecar_store import SidecarStore

MAX_REQUEST = 65536
MAX_RESPONSE = 262144
RETENTION_INTERVAL_SECONDS = 3600


def paths():
    """Keep legacy paths: the rename must not strand records or live clients."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_absolute():
        raise RuntimeError("XDG_RUNTIME_DIR is required")
    root = Path(runtime) / "hyprharness"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "sidecar.sock", state / "hyprharness" / "sidecar" / "observations.sqlite3"


def ensure_private(path):
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError("Unsafe sidecar directory")
    path.chmod(0o700)


def prune_old(store, days):
    """Delete observations older than the retention window; return deleted count."""
    before_ms = int(time.time() * 1000) - int(days * 86_400_000)
    return store.prune(before_ms=before_ms)["deleted"]


async def run_retention(store, days, *, interval_seconds=RETENTION_INTERVAL_SECONDS):
    """Prune on startup, then on a fixed interval. A failed prune never kills the service."""
    while True:
        try:
            prune_old(store, days)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


class SidecarServer:
    def __init__(self, store, *, allow_ingest=False, capture_enabled=False,
                 on_demand=False, browser_ingress=None, alert_enabled=False, resources_enabled=False):
        self.store = store
        self.allow_ingest = allow_ingest
        self.capture_enabled = capture_enabled
        self.on_demand = on_demand
        self.alert_enabled = alert_enabled
        self.resources_enabled = resources_enabled
        self.watcher = None
        self.browser_ingress = browser_ingress
        self.browser_capture_source = None
        self.handlers = set()
        self.embeddings = None
        self.active_settings = {}
        self.settings_file = None
        self.producers = []

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected JSON object")
        action = request.get("action")
        if action == "health":
            state = {"service": "hyprneuro", "ingest_enabled": self.allow_ingest,
                     "capture_enabled": self.capture_enabled,
                     "on_demand_enabled": self.on_demand, "alert_enabled": self.alert_enabled,
                     "resources_enabled": self.resources_enabled}
            if not self.capture_enabled and not self.on_demand and not self.alert_enabled and not self.resources_enabled and self.embeddings is None:
                state["models_invoked"] = False  # No model path can run.
            state["browser_enabled"] = self.browser_ingress is not None
            state["journal"] = self.store.journal_status()
            state["active_settings"] = self.active_settings
            state["settings_file"] = self.settings_file
            state["collectors"] = {task.get_name(): ("running" if not task.done() else
                "stopped" if task.cancelled() else "failed" if task.exception() else "finished")
                for task in self.producers}
            return state
        if action == "record":
            if not self.allow_ingest:
                raise PermissionError("Sidecar ingest disabled; opt in explicitly")
            return self.store.record(request.get("event"))
        if action in ("search", "context"):
            args = {k: v for k, v in request.items()
                    if k in ("query", "start_ms", "end_ms", "source", "limit", "role", "order", "match", "offset")}
            if action == "search":
                args.pop("role", None)
                return self.store.search(**args)
            for key in ("limit", "order", "match", "offset"):
                args.pop(key, None)
            return self.store.context(**args)
        # Exact URL is a separate read-only lookup. Opening it is NOT an RPC
        # here; the browser opener must go through broker action approval.
        if action == "page_url":
            return self.store.page_url(request.get("id"))
        if action == "alerts":
            return self.store.alerts(limit=request.get("limit", 20), offset=request.get("offset", 0))
        if action == "details":
            return self.store.details(request.get("id"))
        raise ValueError("Unknown sidecar RPC action")

    async def dispatch_async(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected JSON object")
        if request.get("action") == "search" and request.get("semantic"):
            if self.embeddings is None:
                raise PermissionError("Semantic search disabled; explicitly configure a local embeddings service")
            return await self.embeddings.search(self.store, request)
        if request.get("action") == "browser_record":
            if not self.allow_ingest or self.browser_ingress is None:
                raise PermissionError("Chrome ingestion disabled")
            result, candidate = self.browser_ingress.record(request)
            if candidate is not None and self.browser_capture_source is not None:
                await self.browser_capture_source.on_candidate(candidate)
            return result
        if request.get("action") == "verify_navigation":
            if set(request) != {"action", "id", "since_ms"}:
                raise ValueError("Invalid navigation verification request")
            return self.store.verify_navigation(request["id"], request["since_ms"])
        if request.get("action") != "omni_observe":
            return self.dispatch(request)
        # The native Pi tool must show user approval for EVERY foreground
        # request. Sidecar also requires a separately enabled session flag.
        # The same-UID broker/socket is not a security boundary against a
        # malicious process running as the same user.
        if not self.on_demand or not self.allow_ingest or self.watcher is None:
            raise PermissionError("On-demand Omni observations are disabled")
        if set(request) != {"action", "purpose"}:
            raise ValueError("Invalid Omni observation request")
        purpose = request["purpose"]
        if purpose not in ("read_text", "describe", "both"):
            raise ValueError("Unknown Omni observation purpose")
        from .recall import CaptureCandidate
        result = await self.watcher.observe_requested(
            CaptureCandidate(source="hyprland", event="pi_request"))
        if not result.get("captured") or not result.get("id"):
            raise RuntimeError("Omni observation produced no record")
        row = self.store.observation(result["id"])
        # Give main Pi a SMALL, explicitly requested excerpt. Background
        # observations never inject text into the Pi session automatically.
        answer = {"id": result["id"], "untrusted": True,
                  "time_ms": row["time_ms"], "app_id": row["app_id"],
                  "title": row["title"], "source": "omni"}
        if purpose in ("read_text", "both"):
            answer["ocr_excerpt"] = row["ocr_text"][:800]
        if purpose in ("describe", "both"):
            answer["description"] = row["description"][:650]
        return answer

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            try:
                sock = writer.get_extra_info("socket")
                _, uid, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET,
                                                                socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise PermissionError("Wrong peer UID")
                raw = await asyncio.wait_for(reader.readline(), 5)
                if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST:
                    raise ValueError("Invalid or oversized RPC frame")
                response = {"ok": True, "result": await self.dispatch_async(json.loads(raw))}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            try:
                data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                if len(data) > MAX_RESPONSE:
                    data = b'{"ok":false,"error":"Response exceeds limit"}'
                writer.write(data + b"\n")
                await writer.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.handlers.discard(task)


async def serve(*, allow_ingest=False, watch_hyprland=False, allow_capture=False,
                allow_on_demand=False, d1_visual=False, allow_browser=False,
                alert=False, alert_journal=False, alert_network=False, alert_resources=False,
                notifications=None, explanation_enabled=False, retention_days=0,
                active_settings=None, settings_file=None,
                semantic_enabled=False, embeddings_url="", embeddings_model="", socket_path=None, db_path=None, shutdown=None,
                desktop=None, models=None, unlock_guard=None, grabber=None,
                excluded_apps=(), excluded_origins=(), browser_token_file=None):
    alert_journal = alert or alert_journal
    alert_network = alert or alert_network
    notifications = bool(alert) if notifications is None else notifications
    if not math.isfinite(retention_days) or retention_days < 0:
        raise ValueError("retention_days must be finite and nonnegative")
    if watch_hyprland and not allow_ingest:
        raise ValueError("--watch-hyprland requires explicit --allow-ingest")
    if allow_capture and not (allow_ingest and watch_hyprland):
        raise ValueError("--allow-capture requires --allow-ingest and --watch-hyprland")
    if allow_on_demand and not allow_ingest:
        raise ValueError("--allow-on-demand requires --allow-ingest")
    if d1_visual and not allow_capture:
        raise ValueError("--d1-visual requires --allow-capture")
    if allow_browser and not allow_ingest:
        raise ValueError("--allow-browser requires --allow-ingest")
    if alert_resources and not allow_ingest:
        raise ValueError("--alert-resources requires explicit --allow-ingest")
    if (alert_journal or alert_network) and not allow_ingest:
        raise ValueError("--alert requires explicit --allow-ingest")
    socket_path = Path(socket_path) if socket_path else paths()[0]
    db_path = Path(db_path) if db_path else paths()[1]
    ensure_private(socket_path.parent)
    ensure_private(db_path.parent)
    if socket_path.is_symlink() or (socket_path.exists() and
                                    not stat.S_ISSOCK(socket_path.stat().st_mode)):
        raise RuntimeError("Refusing unsafe sidecar socket")
    if socket_path.exists():
        # A running socket must not be removed by a second instance.
        probe = socket.socket(socket.AF_UNIX)
        probe.settimeout(0.4)
        try:
            probe.connect(str(socket_path))
        except OSError:
            socket_path.unlink()
        else:
            raise RuntimeError("Sidecar already running")
        finally:
            probe.close()
    store = SidecarStore(db_path)
    worker = SidecarServer(store, allow_ingest=allow_ingest,
                           capture_enabled=allow_capture, on_demand=allow_on_demand,
                           alert_enabled=bool(alert_journal or alert_network), resources_enabled=alert_resources)
    from .settings import Settings
    worker.active_settings = active_settings or asdict(Settings(
        allow_ingest=allow_ingest, watch_hyprland=watch_hyprland, allow_capture=allow_capture,
        allow_on_demand=allow_on_demand, allow_browser=allow_browser, d1_visual=d1_visual,
        alert_journal=alert_journal, alert_network=alert_network, alert_resources=alert_resources,
        notifications=notifications, explanation_enabled=explanation_enabled,
        semantic_enabled=semantic_enabled, embeddings_url=embeddings_url, embeddings_model=embeddings_model,
        retention_enabled=retention_days > 0, retention_days=retention_days,
        excluded_apps=tuple(excluded_apps), excluded_origins=tuple(excluded_origins)))
    worker.settings_file = str(settings_file) if settings_file else None
    server = None
    producers = []
    worker.producers = producers
    source = None
    model_scheduler = None
    browser_token_file = Path(browser_token_file) if browser_token_file else None
    try:
        if semantic_enabled:
            from .semantic import Embeddings
            worker.embeddings = Embeddings(embeddings_url, embeddings_model)
            await worker.embeddings.embed(["Hyprneuro endpoint verification"])
        server = await asyncio.start_unix_server(worker.handle, path=str(socket_path), limit=MAX_REQUEST+1)
        socket_path.chmod(0o600)
        if allow_browser:
            from .browser_ingest import BrowserIngress, create_token, token_path
            if browser_token_file is None:
                browser_token_file = token_path()
            if browser_token_file.parent != socket_path.parent:
                # A test may supply another private runtime path. Production
                # always places the token next to the protected socket.
                ensure_private(browser_token_file.parent)
            token = create_token(browser_token_file)
            worker.browser_ingress = BrowserIngress(store, token=token,
                                                      excluded_origins=excluded_origins)
        if allow_capture or allow_on_demand:
            from .recall import (CapturePolicy, LoginSessionGuard, ScreenWatcher,
                                 DEFAULT_EXCLUDED_APPS)
            from .model_dispatch import ScheduledModels
            if desktop is None:
                from .desktop import Hyprland
                desktop = Hyprland()
            if models is None:
                from .config import Config
                from .models import Models
                models = Models(Config.load())
            model_scheduler = ScheduledModels(models)
            guard = unlock_guard or LoginSessionGuard().unlocked
            apps = DEFAULT_EXCLUDED_APPS | frozenset(str(app).lower() for app in excluded_apps)
            policy = CapturePolicy(enabled=True, check_unlocked=guard,
                                   excluded_app_ids=apps, visual_d1=d1_visual)
            worker.watcher = ScreenWatcher(desktop, model_scheduler, store, policy, grabber)
        if watch_hyprland:
            from .sidecar_sources import HyprlandSource
            if desktop is None:
                from .desktop import Hyprland
                desktop = Hyprland()
            source = HyprlandSource(store)
            capture_source = None
            if allow_capture:
                from .recall_events import D1CaptureSource
                capture_source = D1CaptureSource(worker.watcher)
                worker.browser_capture_source = capture_source
                producers.append(asyncio.create_task(capture_source.run(), name="capture"))

            async def on_event(name, data):
                # Both handlers enqueue; the compositor's socket2 loop is
                # never held up by D1, Omni or SQLite writes.
                await source.on_event(name, data)
                if capture_source is not None:
                    await capture_source.on_event(name, data)

            producers.extend([asyncio.create_task(source.flush(), name="hyprland_store"),
                              asyncio.create_task(desktop.events(on_event), name="hyprland")])
        if alert_journal or alert_network or alert_resources:
            from .event_stream import EventIntake
            from .escalation import EscalationRouter
            from .notify import Notifier
            if models is None:
                from .config import Config
                from .models import Models
                models = Models(Config.load())
            router = EscalationRouter(models, store, notifier=Notifier() if notifications else None,
                                      explanation_enabled=explanation_enabled)
            intake = EventIntake(store=store)
            if alert_journal:
                await router.recover()
                producers.append(asyncio.create_task(intake.follow_journal(router.escalate), name="journal"))
            if alert_network:
                producers.append(asyncio.create_task(intake.network_alerts(router.escalate), name="network"))
            if alert_resources:
                producers.append(asyncio.create_task(intake.resource_alerts(router.escalate), name="resources"))
        if retention_days > 0:
            producers.append(asyncio.create_task(run_retention(store, retention_days), name="retention"))
        stop = shutdown or asyncio.Event()
        if shutdown is None:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass
        await stop.wait()
    finally:
        if server:
            server.close()
        for worker_task in producers:
            worker_task.cancel()
        if producers:
            await asyncio.gather(*producers, return_exceptions=True)
        handlers = list(worker.handlers)
        for task in handlers:
            task.cancel()
        if handlers:
            await asyncio.gather(*handlers, return_exceptions=True)
        if server:
            await server.wait_closed()
        if model_scheduler:
            await model_scheduler.stop()
        socket_path.unlink(missing_ok=True)
        if allow_browser and browser_token_file is not None:
            browser_token_file.unlink(missing_ok=True)
        store.close()


def build_parser():
    parser = argparse.ArgumentParser(description="Hyprneuro observational sidecar")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("serve", help="Independent user-level JSONL/Unix service")
    cmd.add_argument("--config", help="Private Hyprneuro JSON settings (not legacy model TOML)")
    cmd.add_argument("--no-settings", action="store_true", help="Ignore saved feature settings; all defaults off")
    for name in ("allow_ingest", "watch_hyprland", "allow_capture", "allow_on_demand",
                 "allow_browser", "d1_visual", "alert_journal", "alert_network", "alert_resources",
                 "notifications", "semantic_enabled", "explanation_enabled", "retention_enabled"):
        cmd.add_argument("--" + name.replace("_", "-"), action=argparse.BooleanOptionalAction, default=None,
                         help="Explicit on/off override of saved " + name)
    cmd.add_argument("--alert", action=argparse.BooleanOptionalAction, default=None,
                     help="Legacy shorthand: journal + network + notifications; granular flags override")
    cmd.add_argument("--exclude-origin", action="append", default=None, dest="excluded_origins")
    cmd.add_argument("--exclude-app", action="append", default=None, dest="excluded_apps")
    cmd.add_argument("--retention-days", type=float, default=None, metavar="DAYS",
                     help="Explicit deletion window (0 disables); overrides saved retention toggle unless specified")
    cmd.add_argument("--embeddings-url", default=None)
    cmd.add_argument("--embeddings-model", default=None)
    tui = sub.add_parser("tui", help="Manual curses history/search/alerts/status/settings UI")
    tui.add_argument("--config", help="Private Hyprneuro settings path")
    sub.add_parser("health")
    search = sub.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--start-ms", type=int)
    search.add_argument("--end-ms", type=int)
    search.add_argument("--source")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--order", choices=("recent", "relevance"), default="recent")
    search.add_argument("--match", choices=("terms", "phrase", "prefix", "fuzzy"), default="terms")
    search.add_argument("--semantic", action="store_true")
    context = sub.add_parser("context")
    context.add_argument("role", choices=("text", "omni"))
    context.add_argument("--query", default="")
    context.add_argument("--start-ms", type=int)
    context.add_argument("--end-ms", type=int)
    context.add_argument("--source")
    return parser


def resolve_settings(args):
    from .settings import Settings
    saved = Settings() if args.no_settings else Settings.load(args.config)
    values = asdict(saved)
    for field in fields(Settings):
        value = getattr(args, field.name)
        if value is not None:
            values[field.name] = value
    if args.alert is not None:
        for name in ("alert_journal", "alert_network", "notifications"):
            if getattr(args, name) is None:
                values[name] = args.alert
    if args.retention_days is not None and args.retention_enabled is None:
        values["retention_enabled"] = args.retention_days > 0
    return Settings(**values).validate(prerequisites=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "tui":
        from .tui import run
        run(config_path=args.config)
        return
    if args.command == "serve":
        try:
            settings = resolve_settings(args)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        values = asdict(settings)
        active = values.copy()
        values.pop("retention_enabled")
        if not settings.retention_enabled:
            values["retention_days"] = 0
        from .settings import settings_path
        asyncio.run(serve(**values, active_settings=active,
                          settings_file=None if args.no_settings else args.config or settings_path()))
        return
    from .sidecar_client import request
    query = vars(args).copy()
    query.pop("command")
    query["action"] = args.command
    print(json.dumps(asyncio.run(request(query)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
