"""Manual stdlib curses UI. Read-only RPC plus explicit private settings saves.

No service starts/restarts, shell execution, alert management or automatic Pi pull.
"""
import asyncio
import curses
from dataclasses import asdict, fields, replace
import json
import sys
import textwrap
import unicodedata

from .settings import Settings, settings_path
from .sidecar_client import request

VIEWS = ('history', 'search', 'alerts', 'details', 'status', 'settings')
PAGE = 20
MAX_OFFSET = 1000


def safe_text(value):
    """Make every terminal control/format code point inert, including ESC/C1/bidi."""
    text = str(value)[:32768]
    return ''.join(f'[U+{ord(c):04X}]' if unicodedata.category(c).startswith('C') else c for c in text)


def settings_rows(draft, saved, active):
    rows = []
    for f in fields(Settings):
        name = f.name
        value = getattr(draft, name)
        old = getattr(saved, name)
        current = active.get(name, 'unknown')
        # JSON comparison treats persisted lists and in-memory tuples alike.
        same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        status = 'unsaved' if not same(value, old) else ('restart/CLI override' if not same(current, old) else 'active=saved')
        rows.append(f'{name}: draft={json.dumps(value)} | saved={json.dumps(old)} | active={json.dumps(current)} [{status}]')
    return rows


def render(view, rows, *, selected=0, width=100, height=24, offset=0, message=''):
    """Pure bounded renderer; untrusted data is always text, never terminal markup."""
    width, height = max(1, min(width, 500)), max(1, min(height, 200))
    lines = ['Hyprneuro | 1 History 2 Search 3 Alerts 4 Details 5 Status 6 Settings',
             f'{view} | offset={offset} | r refresh, j/k select, PgUp/PgDn page, Enter details/edit, q quit']
    visible = max(0, height-4)
    if view == 'settings' and rows:
        lines.append(f'Setting {selected+1}/{len(rows)} (j/k selects every setting)')
        # Show active/saved/draft on separate lines, not hidden past the terminal
        # edge of a wide table. Only the selected setting is expanded.
        for part in rows[selected].split(' | '):
            lines.extend(textwrap.wrap(safe_text(part), max(1, width-2))[:8])
        lines = lines[:max(0, height-2)]
    else:
        start = max(0, selected-visible+1)
        for i, row in enumerate(rows[start:start+visible], start):
            lines.append(('> ' if i == selected else '  ') + safe_text(row))
    lines += [message, 'Untrusted observations. Settings: Space toggle, Enter edit, w save; restart manually.']
    return [safe_text(line)[:width] for line in lines[:height]]


class App:
    def __init__(self, config_path=None, rpc=None):
        self.path = config_path or settings_path()
        self.saved = Settings.load(self.path)
        self.draft = self.saved
        self.rpc = rpc or (lambda packet: asyncio.run(request(packet)))
        self.view = 'history'
        self.query = ''
        self.match = 'terms'
        self.order = 'recent'
        self.semantic = False
        self.offset = 0
        self.selected = 0
        self.records = []
        self.detail = {}
        self.health = {}
        self.message = ''
        self.refresh()

    def refresh(self):
        try:
            self.health = self.rpc({'action': 'health'})
            if self.view in ('history', 'search'):
                self.records = self.rpc({'action': 'search', 'limit': PAGE, 'offset': self.offset,
                    'query': self.query if self.view == 'search' else '', 'match': self.match,
                    'order': self.order, 'semantic': self.semantic if self.view == 'search' else False})
            elif self.view == 'alerts':
                self.records = self.rpc({'action': 'alerts', 'limit': PAGE, 'offset': self.offset})
            self.message = ('Read-only refresh complete. / query, m match, o order, e semantic; '
                            f'current: {self.match}/{self.order}/semantic={self.semantic}.' if self.view == 'search' else
                            'Read-only refresh complete. No service or Pi action performed.')
            if self.view == 'settings':
                active_path = self.health.get('settings_file')
                if active_path is None:
                    self.message = 'Server ignores saved settings (--no-settings/API); restart manually with --config to load this file.'
                elif str(active_path) != str(self.path):
                    self.message = f'Server uses a different settings file: {active_path}. Saving here will NOT change that file.'
        except (OSError, RuntimeError, ValueError) as exc:
            self.health = {}
            self.records = []
            self.message = f'Service unavailable/error: {exc}. Settings remain available; nothing started.'
        self.selected = min(self.selected, max(0, len(self.rows())-1))

    def rows(self):
        if self.view == 'settings':
            return settings_rows(self.draft, self.saved, self.health.get('active_settings', {}))
        if self.view in ('details', 'status'):
            value = self.detail if self.view == 'details' else self.health
            # Bound wrapping/allocation even if an unexpected response is large.
            text = json.dumps(value, ensure_ascii=False, indent=2)[:32768]
            return [part for line in text.splitlines() for part in textwrap.wrap(safe_text(line), 100)][:1000]
        return [f"#{r['id']} {r.get('time_ms')} {r.get('source')} {r.get('title') or r.get('reason') or r.get('message') or ''}"
                for r in self.records[:PAGE]]

    def switch(self, view):
        self.view, self.offset, self.selected = view, 0, 0
        self.refresh()

    def page(self, direction):
        if self.view in ('history', 'search', 'alerts'):
            if self.view == 'search' and self.semantic:
                self.message = 'Semantic results are capped at 20; no pagination beyond the bounded candidate set.'
                return
            self.offset = max(0, min(MAX_OFFSET, self.offset + PAGE*direction))
            self.selected = 0
            self.refresh()
        else:
            self.selected = max(0, min(len(self.rows())-1, self.selected+PAGE*direction))

    def save(self):
        if json.dumps(asdict(Settings.load(self.path)), sort_keys=True) != json.dumps(asdict(self.saved), sort_keys=True):
            raise ValueError('Settings changed on disk; use r in settings to reload before saving')
        self.draft.save(self.path)
        self.saved = self.draft
        try:
            self.saved.validate(prerequisites=True)
            validity = 'Prerequisites configured (external services not verified).'
        except ValueError as exc:
            validity = f'Startup will refuse this configuration: {exc}.'
        self.message = f'Saved to {self.path}; not applied. Restart manually; CLI overrides may still apply. {validity}'

    def toggle(self):
        if self.view != 'settings':
            return
        f = fields(Settings)[self.selected]
        if f.type is bool:
            self.draft = replace(self.draft, **{f.name: not getattr(self.draft, f.name)})
            self.message = 'Draft only; prerequisites are NEVER silently enabled. w saves for manual restart.'

    def open_record(self):
        if self.view not in ('history', 'search', 'alerts') or not self.records:
            return
        self.detail = self.rpc({'action': 'details', 'id': self.records[self.selected]['id']})
        self.view, self.selected = 'details', 0


def prompt(screen, label, initial='', limit=500):
    """Printable-only bounded input; no echo of raw control sequences."""
    value = initial[:limit]
    while True:
        height, width = screen.getmaxyx()
        try:
            screen.move(max(0, height-1), 0)
            screen.clrtoeol()
            screen.addnstr(max(0, height-1), 0, safe_text(label+value), max(0, width-1))
        except curses.error:
            pass
        screen.refresh()
        key = screen.get_wch()
        if key in ('\n', '\r'):
            return value
        if key == '\x1b':
            return None
        if key in (curses.KEY_BACKSPACE, '\x7f', '\b'):
            value = value[:-1]
        elif isinstance(key, str) and key.isprintable() and not unicodedata.category(key).startswith('C') and len(value) < limit:
            value += key


def loop(screen, app):
    screen.keypad(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        for y, line in enumerate(render(app.view, app.rows(), selected=app.selected,
                                       width=width-1, height=height, offset=app.offset, message=app.message)):
            try:
                screen.addnstr(y, 0, line, max(0, width-1))
            except curses.error:
                pass
        screen.refresh()
        key = screen.get_wch()
        try:
            if key == 'q':
                return
            if isinstance(key, str) and key in '123456':
                app.switch(VIEWS[int(key)-1])
            elif key in ('j', curses.KEY_DOWN):
                app.selected = min(max(0, len(app.rows())-1), app.selected+1)
            elif key in ('k', curses.KEY_UP):
                app.selected = max(0, app.selected-1)
            elif key in (curses.KEY_NPAGE, 'n'):
                app.page(1)
            elif key in (curses.KEY_PPAGE, 'p'):
                app.page(-1)
            elif key == 'r':
                if app.view == 'settings':
                    app.saved = Settings.load(app.path)
                    app.draft = app.saved
                app.refresh()
            elif key == ' ':
                app.toggle()
            elif key == 'w' and app.view == 'settings':
                app.save()
            elif key == '/' and app.view == 'search':
                value = prompt(screen, 'Query (Enter submit, Esc cancel): ', app.query, 300)
                if value is not None:
                    app.query, app.offset, app.selected = value, 0, 0
                    app.refresh()
            elif key == 'm' and app.view == 'search':
                modes = ('terms', 'phrase', 'prefix', 'fuzzy')
                app.match = modes[(modes.index(app.match)+1) % len(modes)]
                app.message = f'Search match={app.match}; r to query. / edit query, o order, e semantic.'
            elif key == 'o' and app.view == 'search':
                app.order = 'relevance' if app.order == 'recent' else 'recent'
                app.message = f'Search order={app.order}; r to query.'
            elif key == 'e' and app.view == 'search':
                app.semantic = not app.semantic
                app.message = f'Query semantic={app.semantic}; requires active opt-in endpoint. r to query.'
            elif key in ('\n', '\r', curses.KEY_ENTER):
                if app.view == 'settings':
                    f = fields(Settings)[app.selected]
                    if f.type is bool:
                        app.toggle()
                    else:
                        current = getattr(app.draft, f.name)
                        initial = json.dumps(current) if f.type is tuple else str(current)
                        value = prompt(screen, f'{f.name} (lists as JSON): ', initial, 2000 if f.type is tuple else 500)
                        if value is not None:
                            value = float(value) if f.type is float else json.loads(value) if f.type is tuple else value
                            draft = replace(app.draft, **{f.name: value})
                            draft.validate()
                            app.draft = draft
                else:
                    app.open_record()
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            app.message = f'Error: {exc}'


def run(config_path=None):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit('TUI requires an interactive terminal; use health/search for scripted access')
    try:
        app = App(config_path)
        curses.wrapper(loop, app)
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, curses.error) as exc:
        raise SystemExit(f'Cannot open TUI: {safe_text(exc)}') from exc
