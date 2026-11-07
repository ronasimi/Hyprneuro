"""Opt-in Chrome MV3 native messaging host and host manifest installer.

Reads only bounded metadata messages from a single configured extension ID.
Never reads cookies, page bodies or browser history files; stdout is binary
native messaging frames only. No root access and no shell execution.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

from .browser_ingest import EXTENSION_ID, HOST_NAME, read_token
from .sidecar_client import request

MAX_IN = 8192
MAX_OUT = 8192
BROWSERS = {
    "chrome": "google-chrome",
    "chromium": "chromium",
    "brave": "BraveSoftware/Brave-Browser",
}


def config_dir():
    # Keep the existing extension allowlist across the Hyprneuro rename.
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hyprharness"


def expected_origin_file():
    return config_dir() / "chrome_extension_id"


def ensure_user_file(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise PermissionError("Unsafe Chrome native host configuration")


def expected_origin(path=None):
    path = Path(path) if path is not None else expected_origin_file()
    ensure_user_file(path)
    ext_id = path.read_text(encoding="ascii").strip()
    if not EXTENSION_ID.fullmatch(ext_id):
        raise ValueError("Invalid installed extension ID")
    return "chrome-extension://" + ext_id + "/"


def read_frame(stream):
    header = stream.read(4)
    if header == b"":
        return None
    if len(header) != 4:
        raise ValueError("Truncated Chrome native message header")
    length = struct.unpack("=I", header)[0]
    if not 0 < length <= MAX_IN:
        raise ValueError("Chrome event exceeds native host limit")
    raw = stream.read(length)
    if len(raw) != length:
        raise ValueError("Truncated Chrome event payload")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected Chrome event object")
    return value


def write_frame(stream, data):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_OUT:
        raise ValueError("Oversized Chrome native host response")
    stream.write(struct.pack("=I", len(payload)) + payload)
    stream.flush()


def run_host(origin, *, stdin=None, stdout=None, config_path=None, token_file=None,
             sender=None):
    """Run Chrome binary IPC; tests can inject a fake local async sender."""
    if origin != expected_origin(config_path):
        raise PermissionError("Extension origin is not authorized")
    token = read_token(token_file)
    inp = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    while True:
        event = read_frame(inp)
        if event is None:
            break
        try:
            payload = {"action": "browser_record", "token": token, "event": event}
            response = asyncio.run(sender(payload) if sender else request(payload))
            write_frame(out, {"ok": True, "result": response})
        except Exception as exc:
            write_frame(out, {"ok": False, "error": str(exc)[:200]})


def install(extension_id, browser, *, executable=None, home=None, replace=False):
    """Only called by an explicit user CLI command; no auto-registration."""
    if not isinstance(extension_id, str) or not EXTENSION_ID.fullmatch(extension_id):
        raise ValueError("Invalid Chrome extension ID (32 letters a-p)")
    if browser not in BROWSERS:
        raise ValueError("Unknown Chrome-family browser")
    executable = executable or shutil.which("hyprneuro-chrome-host")
    if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
        raise FileNotFoundError("Install Hyprneuro first so the Chrome host entry point is on PATH")
    base = Path(home) if home else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if not base.is_absolute():
        raise ValueError("Expected absolute XDG config directory")
    config = base / "hyprharness"
    target = base / BROWSERS[browser] / "NativeMessagingHosts" / (HOST_NAME + ".json")
    for directory in (config, target.parent):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid():
            raise PermissionError("Unsafe native host directory")
        directory.chmod(0o700)
    identity = config / "chrome_extension_id"
    for path in (identity, target):
        if path.is_symlink() or (path.exists() and (not replace or path.stat().st_uid != os.getuid())):
            raise PermissionError("Refusing to overwrite existing Chrome host registration")
    manifest = {"name": HOST_NAME,
                "description": "Opt-in local Hyprneuro Chrome Recall bridge",
                "path": str(executable), "type": "stdio",
                "allowed_origins": ["chrome-extension://" + extension_id + "/"]}
    for path, body in ((identity, extension_id + "\n"),
                       (target, json.dumps(manifest, indent=2) + "\n")):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, body.encode("utf-8"))
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
    return target


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        parser = argparse.ArgumentParser(description="Register explicitly approved local Chrome native host")
        parser.add_argument("action", choices=("install",))
        parser.add_argument("--extension-id", required=True)
        parser.add_argument("--browser", choices=tuple(BROWSERS), default="chrome")
        parser.add_argument("--replace", action="store_true")
        args = parser.parse_args()
        target = install(args.extension_id, args.browser, replace=args.replace)
        print(str(target))
        return
    if len(sys.argv) < 2:
        raise SystemExit("Expected Chrome extension origin or explicit install command")
    try:
        run_host(sys.argv[1])
    except Exception as exc:
        print("Chrome host: " + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
