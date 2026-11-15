"""Version-aware Hyprland IPC. Never accept model-provided Lua, shell or dispatch strings."""
import asyncio
import json
import os
from pathlib import Path
import re
import socket
import time

IPC_TIMEOUT_SECONDS = 3


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Desktop operation deadline exceeded")
    return remaining

QUERIES = {"clients","activewindow","activeworkspace","workspaces","monitors","layers","devices","version","binds","configerrors"}

class Hyprland:
    def directory(self):
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}",sig):
            raise RuntimeError("Missing/invalid HYPRLAND_INSTANCE_SIGNATURE")
        root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))/"hypr"/sig
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            raise RuntimeError("Unsafe Hyprland socket directory")
        return root.resolve()

    def _request(self, command, *, deadline=None):
        deadline = time.monotonic() + IPC_TIMEOUT_SECONDS if deadline is None else deadline
        # The executor may start this read after its caller has timed out. Never
        # open a socket then; a running worker also shares the TOTAL deadline.
        _remaining(deadline)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            path=str(self.directory()/".socket.sock")
            sock.settimeout(_remaining(deadline))
            sock.connect(path)
            sock.settimeout(_remaining(deadline))
            sock.sendall(command.encode());out=bytearray()
            while True:
                sock.settimeout(_remaining(deadline))
                data=sock.recv(65536)
                if not data:break
                out.extend(data)
                if len(out)>4*1024*1024:raise RuntimeError("Compositor response too large")
            _remaining(deadline)
            return out.decode()

    async def query(self, name, *, deadline=None):
        if name not in QUERIES:raise ValueError("Unknown compositor query")
        deadline = time.monotonic() + IPC_TIMEOUT_SECONDS if deadline is None else deadline
        _remaining(deadline)
        async with asyncio.timeout_at(deadline):
            value=await asyncio.to_thread(self._request,"j/"+name,deadline=deadline)
            result=json.loads(value)
            _remaining(deadline)
            return result

    async def action(self, operation, value=None, *, before_dispatch=None, deadline=None):
        # A direct adapter call cannot bypass the controller's authority gate.
        if before_dispatch is None:
            raise PermissionError("Desktop dispatch requires an authority gate")
        deadline = time.monotonic() + IPC_TIMEOUT_SECONDS if deadline is None else deadline
        _remaining(deadline)
        expression=dispatch_expression(operation,value)
        writer=None
        try:
            async with asyncio.timeout_at(deadline):
                version=await self.query("version",deadline=deadline)
                if not str(version.get("tag","")).startswith("v0.57."):
                    raise RuntimeError("Desktop mutations require tested Hyprland 0.57.x; read-only IPC remains available")
                reader,writer=await asyncio.open_unix_connection(str(self.directory()/".socket.sock"))
                # Connection establishment and version lookup may suspend. The
                # final focus + authority check runs AFTER both. No await or
                # to_thread queue lies between that check and the wire write.
                await before_dispatch()
                _remaining(deadline)
                writer.write(("dispatch "+expression).encode())
                await writer.drain()
                chunks=bytearray()
                while data:=await reader.read(65536):
                    chunks.extend(data)
                    if len(chunks)>4*1024*1024:raise RuntimeError("Compositor response too large")
                result=chunks.decode()
                _remaining(deadline)
        finally:
            if writer is not None:
                writer.close()
                # Cleanup must not extend the operation after a cancellation or
                # deadline. A separate scope also bounds wait_closed in finally.
                try:
                    async with asyncio.timeout_at(deadline):
                        await writer.wait_closed()
                except TimeoutError:raise
                except OSError:pass
        _remaining(deadline)
        if result.strip()!="ok":raise RuntimeError("Hyprland rejected action: "+result[:1000])
        return {"ok":True,"operation":operation,"value":value}

    async def events(self, callback):
        while True:
            writer=None
            try:
                reader,writer=await asyncio.open_unix_connection(str(self.directory()/".socket2.sock"),limit=65536)
                while line:=await reader.readline():
                    name,sep,data=line.decode(errors="replace").rstrip("\n").partition(">>")
                    if sep:await callback(name,data[:2048])
            except (OSError,ValueError,RuntimeError):
                await asyncio.sleep(2)
            finally:
                if writer:
                    writer.close()
                    try:await writer.wait_closed()
                    except OSError:pass
            await asyncio.sleep(.25)

def dispatch_expression(operation,value=None):
    if operation in ("focus_direction","move_direction"):
        if value not in ("left","right","up","down"):raise ValueError("Invalid direction")
        fn="focus" if operation=="focus_direction" else "window.move"
        return 'hl.dsp.'+fn+'({ direction = "'+value+'" })'
    if operation in ("workspace","move_workspace"):
        if type(value) is not int or not 1<=value<=100:raise ValueError("Workspace must be 1..100")
        fn="focus" if operation=="workspace" else "window.move"
        return f"hl.dsp.{fn}({{ workspace = {value} }})"
    if operation=="toggle_float":return 'hl.dsp.window.float({ action = "toggle" })'
    if operation=="toggle_split":return 'hl.dsp.layout("togglesplit")'
    raise ValueError("Unsupported desktop operation")
