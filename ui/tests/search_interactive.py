"""Actual GTK read-only search/details/filter/error/reconnect. No inference.
Usage: python ui/tests/search_interactive.py SESSION BINARY [--service]
--service inspects only existing observations through the actual installed UI.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from desktop_driver import Atspi, Desktop

repo = Path(__file__).resolve().parents[2]
root = Path.home() / 'Workspace/hyprneuro-search' / time.strftime('gui-%Y%m%d-%H%M%S')
root.mkdir(parents=True)
session, binary = sys.argv[1:3]
service = '--service' in sys.argv
unit = 'hyprneuro-ui.service'
installed = Path.home() / '.local/bin/hyprneuro-ui'
oldhash = hashlib.sha256(installed.read_bytes()).hexdigest()
pid = int(subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value']))
Desktop(session, pid).safe()
backend = ui = None
try:
    if not service:
        subprocess.run(['systemctl', '--user', 'stop', unit], check=True)
        env = dict(os.environ, PYTHONPATH=str(repo / 'python/src'), PYTHONDONTWRITEBYTECODE='1',
                   ASAN_OPTIONS='detect_leaks=0:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                   GDK_WAYLAND_DISABLE='ext_background_effect_manager_v1')
        env.pop('G_DEBUG', None)
        backend = subprocess.Popen([str(repo / 'python/.venv/bin/python'), str(repo / 'ui/tests/search_fixture.py'), str(root)],
                                   env=env, stdout=(root / 'sidecar.log').open('w'), stderr=subprocess.STDOUT)
        for _ in range(100):
            assert backend.poll() is None
            if (root / 'sidecar.sock').exists():
                break
            time.sleep(.05)
        env['HYPHARNESS_SIDECAR'] = str(root / 'sidecar.sock')
        ui = subprocess.Popen([binary], env=env, stdout=(root / 'gui.log').open('w'), stderr=subprocess.STDOUT)
        pid = ui.pid
    d = Desktop(session, pid)
    sha = hashlib.sha256(Path(f'/proc/{pid}/exe').read_bytes()).hexdigest()
    assert sha == hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    print('EXECUTED', binary, sha, root, flush=True)
    d.wait(lambda: d.find('button', 'Settings'))
    d.activate('button', 'Settings')
    d.activate('button', 'Search observations')
    d.wait(lambda: 'Explicit search only · existing records · no collectors or model calls' in d.labels())
    assert not (root / 'requests.jsonl').exists(), 'Page entry must not issue search'

    def query(text):
        node = d.wait(lambda: d.find('text', 'Observation query (300 characters maximum)'))
        assert Atspi.EditableText.set_text_contents(node, text)
        d.wait(lambda: Atspi.Text.get_text(d.find('text', 'Observation query (300 characters maximum)'), 0, -1) == text)

    def run_search(fast_error=False):
        previous = d.labels()
        d.activate('button', 'Search / Recent')
        if not service and not fast_error:
            d.wait(lambda: 'Searching stored observations…' in d.labels())
        if fast_error:
            d.wait(lambda: any(s.startswith('Search unavailable:') and s not in previous for s in d.labels()))
        d.wait(lambda: any(s.startswith(('Up to 10 results', 'No matching stored', 'Search unavailable:')) for s in d.labels()))

    def rows():
        return [n.get_name() for n in d.nodes(pid) if n.get_role_name() == 'button' and n.get_name().startswith('#')]

    def detail():
        node = d.find('text', 'Stored observation details (untrusted, read-only)')
        return Atspi.Text.get_text(node, 0, -1)

    def select_filter(name, downs):
        node = next(n for n in d.nodes(pid) if n.get_role_name() == 'toggle button' and n.get_description() == name)
        r = node.get_component_iface().get_extents(Atspi.CoordType.WINDOW)
        l = d.layer()
        # WINDOW extents are page-local (SCREEN origins are zero on layer-shell).
        # Add the verified panel's 12px padding + 1px border, not guessed columns.
        d.pointer(l['x'] + 13 + r.x + r.width // 2, l['y'] + 13 + r.y + r.height // 2)
        d.keys('-k', 'Home', *sum((['-k', 'Down'] for _ in range(downs)), []), '-k', 'Return')
        expected = (['All sources','hyprland','chrome','journal','network','resource','omni','manual']
                    if 'source' in name else ['Any time','Last 24 hours','Today (local)'])[downs]
        d.wait(lambda: any(n.get_role_name() == 'combo box' and n.get_description() == name and n.get_name() == expected
                           for n in d.nodes(pid)))
        time.sleep(.4)  # let the real dropdown popover finish closing

    if service:
        # Independently compare actual public RPC records, no seeding production.
        import socket
        def rpc(request):
            with socket.socket(socket.AF_UNIX) as c:
                c.connect(str(Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprharness/sidecar.sock'))
                c.sendall((json.dumps(request) + '\n').encode())
                result = json.loads(c.makefile('rb').readline(262144))
                assert result['ok'], result
                return result['result']
        health = rpc({'action': 'health'})
        assert not health['capture_enabled'] and not health['browser_enabled'], health
        expected = rpc({'action': 'search', 'limit': 10})
        query('');run_search()
        current = rows()
        assert len(current) == len(expected), (current, expected)
        if expected:
            first = expected[0]
            name = next(n for n in current if n.startswith(f"#{first['id']} · "))
            assert first['title'] in name and first['source'] in name
            d.activate('button', name)
            d.wait(lambda: 'Stored details · read-only · no URLs opened or data sent to a model' in d.labels())
            actual = rpc({'action': 'details', 'id': first['id']})
            assert f"#{actual['id']} · " in detail() and actual['title'] in detail(), detail()
            (root / 'inspected-public-record.json').write_text(json.dumps(actual, indent=2))
        else:
            assert 'No matching stored observations' in d.labels()
        (root / 'health-before.json').write_text(json.dumps(health, indent=2))
        assert rpc({'action': 'health'})['active_settings'] == health['active_settings']
        print('PASS actual installed GTK + real sidecar existing observations/details; no seeds/models/collectors', flush=True)
    else:
        query('');run_search();assert len(rows()) == 10
        query('needle')
        d.activate('button', 'Search / Recent')
        d.wait(lambda: 'Searching stored observations…' in d.labels())
        # Back remains usable while RPC runs on a worker thread.
        d.activate('button', '← Settings')
        d.wait(lambda: d.find('button', 'Search observations'))
        d.activate('button', 'Search observations')
        d.wait(lambda: any(s.startswith('Up to 10 results') for s in d.labels()))
        assert len(rows()) == 2, rows()
        recent = next(s for s in rows() if 'needle recent' in s)
        d.activate('button', recent)
        d.wait(lambda: 'Stored details · read-only · no URLs opened or data sent to a model' in d.labels())
        assert '<b>untrusted</b>' in detail() and 'https://example.test/docs' in detail()
        assert 'NEVER_EXPOSE' not in detail() and '#hidden' not in detail(), detail()
        (root / 'literal-detail.txt').write_text(detail())
        select_filter('Observation source filter', 7)  # manual
        run_search();assert len(rows()) == 1 and 'needle old' in rows()[0], rows()
        select_filter('Observation time filter', 1)  # last24h
        run_search();assert not rows() and 'No matching stored observations' in d.labels()
        select_filter('Observation source filter', 0)
        select_filter('Observation time filter', 2)  # today
        run_search();assert len(rows()) == 1 and 'needle recent' in rows()[0], rows()
        (root / 'mode.txt').write_text('missing-details')
        d.activate('button', rows()[0])
        d.wait(lambda: any(s.startswith('Search unavailable: Observation not found') for s in d.labels()))
        assert 'https://example.test' not in detail()
        (root / 'mode.txt').write_text('malformed');run_search()
        assert not rows() and any('invalid sidecar response' in s for s in d.labels())
        (root / 'mode.txt').unlink()
        os.replace(root / 'sidecar.sock', root / 'offline.sock')
        try:
            run_search(fast_error=True);assert not rows() and any(s.startswith('Search unavailable:') for s in d.labels())
        finally:
            os.replace(root / 'offline.sock', root / 'sidecar.sock')
        query('needle');run_search();assert len(rows()) == 1
        query('doesnotexist');run_search();assert not rows()
        db = sqlite3.connect(f'file:{root / "db.sqlite3"}?mode=ro', uri=True)
        assert db.execute('SELECT count(*) FROM observations').fetchone()[0] == 14
        db.close()
        requests = [json.loads(line) for line in (root / 'requests.jsonl').read_text().splitlines()]
        assert all(set(r) <= {'action', 'query', 'limit', 'source', 'start_ms', 'end_ms', 'id'} for r in requests)
        assert all(r['action'] in ('search', 'details') for r in requests)
        print('PASS actual GTK search/recent10, query/source/time, literal details, no private URL, empty/error/malformed/reconnect, responsive Back, unchanged fixture store', flush=True)
    (root / 'final-labels.json').write_text(json.dumps(d.labels(), indent=2))
    d.activate('button', '← Settings');d.activate('button', '← Back')
    for n in d.nodes(pid):
        if n.get_role_name() == 'button' and (n.get_name() == 'Settings' or 'transcript:' in n.get_name()):
            rect = n.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            assert (rect.width, rect.height) == (16,16), (n.get_name(), rect)
    assert service or ui.poll() is None
finally:
    if ui is not None:
        ui.terminate();ui.wait(timeout=10)
    if backend is not None:
        backend.terminate();backend.wait(timeout=10)
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == oldhash
    if not service:
        subprocess.run(['systemctl', '--user', 'start', unit], check=True)
