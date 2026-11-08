"""Private Hyprneuro feature settings, separate from legacy model configuration."""
from dataclasses import asdict, dataclass, fields
import json
import math
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class Settings:
    allow_ingest: bool = False
    watch_hyprland: bool = False
    allow_capture: bool = False
    allow_on_demand: bool = False
    allow_browser: bool = False
    d1_visual: bool = False
    alert_journal: bool = False
    alert_network: bool = False
    alert_resources: bool = False
    notifications: bool = False
    semantic_enabled: bool = False
    explanation_enabled: bool = False
    retention_enabled: bool = False
    retention_days: float = 7
    embeddings_url: str = ''
    embeddings_model: str = ''
    excluded_apps: tuple = ()
    excluded_origins: tuple = ()

    def validate(self, *, prerequisites=False):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.type is bool and type(value) is not bool:
                raise ValueError(f'{f.name} must be boolean')
        if type(self.retention_days) not in (int, float) or not math.isfinite(self.retention_days) or self.retention_days < 0:
            raise ValueError('retention_days must be finite and nonnegative')
        for name in ('embeddings_url', 'embeddings_model'):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 500 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError(f'Invalid {name}')
        for name in ('excluded_apps', 'excluded_origins'):
            values = getattr(self, name)
            if (not isinstance(values, (tuple, list)) or len(values) > 100 or
                    any(not isinstance(v, str) or not v or len(v) > 300 or
                        any(ord(c) < 32 or ord(c) == 127 for c in v) for v in values)):
                raise ValueError(f'Invalid {name}')
        if prerequisites:
            if self.retention_enabled and self.retention_days <= 0:
                raise ValueError("retention_enabled requires positive retention_days")
            collectors = (self.watch_hyprland, self.allow_capture, self.allow_on_demand,
                          self.allow_browser, self.alert_journal, self.alert_network, self.alert_resources)
            if any(collectors) and not self.allow_ingest:
                raise ValueError('Collectors/capture require explicit allow_ingest')
            if self.allow_capture and not self.watch_hyprland:
                raise ValueError('allow_capture requires watch_hyprland')
            if self.d1_visual and not self.allow_capture:
                raise ValueError('d1_visual requires allow_capture')
            if (self.notifications or self.explanation_enabled) and not any((self.alert_journal, self.alert_network, self.alert_resources)):
                raise ValueError('Notifications/explanations require an explicit alert collector')
            if self.semantic_enabled:
                from .semantic import Embeddings
                Embeddings(self.embeddings_url, self.embeddings_model)
        return self

    @classmethod
    def load(cls, path=None):
        p = Path(path) if path else settings_path()
        _safe_file(p)
        if not p.exists():
            return cls()
        if p.stat().st_size > 32768:
            raise ValueError('Settings file exceeds 32 KiB')
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or data.keys() - {f.name for f in fields(cls)}:
            raise ValueError('Unknown/invalid Hyprneuro settings')
        return cls(**data).validate()

    def save(self, path=None):
        self.validate()
        p = Path(path) if path else settings_path()
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _safe_file(p)
        p.parent.chmod(0o700)
        fd, temporary = tempfile.mkstemp(dir=p.parent, prefix='.settings-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(asdict(self), stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, p)
            directory = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)


def settings_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'hyprneuro/settings.json'


def _safe_file(p):
    if p.parent.is_symlink() or (p.parent.exists() and p.parent.stat().st_uid != os.getuid()):
        raise ValueError('Unsafe settings directory')
    if p.is_symlink() or (p.exists() and (not p.is_file() or p.stat().st_uid != os.getuid())):
        raise ValueError('Unsafe settings file')
