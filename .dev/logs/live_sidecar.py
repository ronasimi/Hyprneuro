"""Persistent live sidecar launcher for durable-task testing (read-only, no capture)."""
import asyncio
import json
import os
import sys
from pathlib import Path

SOCKET = Path(os.environ.get("HYPRNEURO_TEST_SOCKET", "/run/user/1000/hyprneuro-test/sidecar.sock"))
DB = SOCKET.parent / "state" / "test.sqlite3"
SKILLS = SOCKET.parent / "skills"


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
    from hyprneuro.sidecar import serve
    SOCKET.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    SKILLS.mkdir(parents=True, exist_ok=True)
    (SKILLS / "kitty.json").write_text(json.dumps({
        "app_id": "kitty", "name": "Kitty terminal", "description": "Terminal",
        "version": "1", "tags": ["terminal"], "body": "Run shell commands in the terminal.",
        "tools_schema": {"type": "object"}}))
    (SKILLS / "google-chrome.json").write_text(json.dumps({
        "app_id": "google-chrome", "name": "Chrome", "description": "Browser",
        "version": "1", "tags": ["browser"], "body": "Browser skill body",
        "tools_schema": {"type": "object"}}))
    print(json.dumps({"socket": str(SOCKET), "db": str(DB)}), flush=True)
    asyncio.run(serve(allow_ingest=True, watch_hyprland=True, assistant_enabled=True,
                      assistant_recent_apps=5, socket_path=SOCKET, db_path=DB,
                      skills_dir=str(SKILLS)))


if __name__ == "__main__":
    main()
