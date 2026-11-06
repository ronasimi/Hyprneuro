from dataclasses import dataclass, fields
from pathlib import Path
import os
import tomllib

@dataclass(frozen=True)
class Config:
    text_port: int = 8081
    omni_port: int = 8082
    decision_port: int = 8083
    model_timeout: float = 120
    max_tokens: int = 2048
    max_hops: int = 8
    tape_chars: int = 20000
    decision_chars: int = 1400
    reasoning_policy: str = "adaptive"
    thinking_threshold: float = .5
    ambiguity_margin: float = .1
    conservative_thinking: bool = True
    tool_threshold: float = .5
    approval_seconds: float = 120
    monitor_seconds: float = 2
    max_jobs: int = 4
    memory_reserve_mib: int = 256
    external_search: bool = False
    input_backend: str = "wtype"

    @classmethod
    def load(cls, path=None):
        p = Path(path) if path else Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config"))/"hyprharness/config.toml"
        data = tomllib.loads(p.read_text()) if p.exists() else {}
        unknown = data.keys() - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown config keys: {sorted(unknown)}")
        c = cls(**data)
        for field in fields(cls):
            value=getattr(c,field.name)
            valid=type(value) in (int,float) if field.type is float else type(value) is field.type
            if not valid:raise ValueError(f"Invalid type for {field.name}")
        if not all(isinstance(x, int) and 1 <= x <= 65535 for x in (c.text_port, c.omni_port, c.decision_port)):
            raise ValueError("Invalid model port")
        if not (1 <= c.max_hops <= 32 and 32 <= c.max_tokens <= 8192 and 1000 <= c.tape_chars <= 64000):
            raise ValueError("Invalid model/context limits")
        if not (100 <= c.decision_chars <= 1600 and 1 <= c.max_jobs <= 16 and 64 <= c.memory_reserve_mib <= 4096):
            raise ValueError("Invalid decision/job limits")
        if not all(0 <= x <= 1 for x in (c.thinking_threshold, c.tool_threshold, c.ambiguity_margin)):
            raise ValueError("Invalid thresholds")
        if c.monitor_seconds < .5 or not 1 <= c.approval_seconds <= 600 or not 1 <= c.model_timeout <= 600:
            raise ValueError("Invalid timing limits")
        if c.reasoning_policy not in ("adaptive", "on", "off"):
            raise ValueError("reasoning_policy must be adaptive, on or off")
        if c.input_backend not in ("wtype", "ydotool"):
            raise ValueError("input_backend must be wtype or ydotool")
        return c

def backend_digest():
    import hashlib
    h=hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def state_dir():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local/state"))/"hyprharness"

def socket_path():
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("XDG_RUNTIME_DIR is required; run inside your user session")
    return Path(root)/"hyprharness/control.sock"

def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError(f"Unsafe directory: {path}")
    path.chmod(0o700)
    return path
