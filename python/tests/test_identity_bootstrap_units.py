"""Real owned systemd units, NOT production units or human/native acceptance.

Explicit opt-in under the machine lease. Tests systemd262 show API and actual
EnvironmentFile precedence without changing manager-global environment.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import uuid

from test_identity_bootstrap import BootstrapTests
from hyprneuro.identity_bootstrap import DIGEST_VARIABLE, read_unit_environment


@unittest.skipUnless(os.environ.get('HN_BOUNDARY_PRIVATE_UNITS') == '1',
                     'Requires machine-leased owned user-unit fixtures')
class BootstrapUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_environmentfile_precedence_and_prestart_rejections(self):
        fixture = BootstrapTests()
        fixture.setUp()
        runtime = Path('/run/user') / str(os.getuid()) / 'systemd/user'
        runtime.mkdir(exist_ok=True)
        unit_paths = []
        prefix = 'hyprneuro-test-bootstrap-' + uuid.uuid4().hex
        commands = []
        observations = {}
        evidence = Path(os.environ['HN_BOUNDARY_EVIDENCE_ROOT']) / prefix if os.environ.get('HN_BOUNDARY_EVIDENCE_ROOT') else None
        if evidence:
            evidence.mkdir(mode=0o700)
        async def run(*args):
            commands.append(args)
            process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.PIPE)
            out, error = await asyncio.wait_for(process.communicate(), 4)
            if process.returncode:
                raise AssertionError((args, process.returncode, error.decode()))
            return out.decode().strip()
        try:
            verified = fixture.load()
            observed = fixture.root / 'observed.json'
            reader = fixture.root / 'read.py'
            reader.write_text('import json,os\nfrom pathlib import Path\nPath(' + repr(str(observed))
                              + ').write_text(json.dumps({"digest":os.environ.get('
                              + repr(DIGEST_VARIABLE) + ')}))\n')
            other = fixture.root / 'other.env'
            other.write_text(DIGEST_VARIABLE + '=' + '0' * 64 + '\n')
            variants = {
                'valid': 'EnvironmentFile=' + str(fixture.environment) + '\n',
                'direct-override': 'Environment=' + DIGEST_VARIABLE + '=' + '0'*64 + '\nEnvironmentFile=' + str(fixture.environment) + '\n',
                'later-file': 'EnvironmentFile=' + str(fixture.environment) + '\nEnvironmentFile=' + str(other) + '\n',
                'optional': 'EnvironmentFile=-' + str(fixture.environment) + '\n',
                'duplicate': ('EnvironmentFile=' + str(fixture.environment) + '\n')*2,
                'pass': 'EnvironmentFile=' + str(fixture.environment) + '\nPassEnvironment=' + DIGEST_VARIABLE + '\n',
                'unset': 'EnvironmentFile=' + str(fixture.environment) + '\nUnsetEnvironment=' + DIGEST_VARIABLE + '\n',
            }
            for label, environment in variants.items():
                name = prefix + '-' + label + '.service'
                path = runtime / name
                body = ('[Service]\nType=oneshot\nRestart=no\nRuntimeMaxSec=5\nTimeoutStartSec=5\n'
                        + 'ExecStart=' + sys.executable + ' -I ' + str(reader) + '\n' + environment)
                path.write_text(body)
                unit_paths.append(path)
                self.assertEqual(await run('/usr/bin/systemctl', '--user', 'show', name,
                                           '-p', 'FragmentPath', '--value'), str(path))
                try:
                    props = await read_unit_environment(name)
                except PermissionError:
                    self.assertIn(label, ['direct-override', 'later-file', 'duplicate'])
                    props = None
                observations[label] = {'properties': props, 'unit_bytes': body}
                if label == 'valid':
                    verified.check_unit_environment(props)
                else:
                    if props is not None:
                        with self.assertRaises(PermissionError, msg=label):
                            verified.check_unit_environment(props)
                    # Guard failure before ANY helper/unit start.
                    self.assertEqual(await run('/usr/bin/systemctl', '--user', 'show', name,
                                               '-p', 'MainPID', '--value'), '0')
                if label in ['valid', 'direct-override', 'later-file', 'unset']:
                    # Execute ONLY private reader to demonstrate actual systemd
                    # precedence, not an identity-helper admission after rejection.
                    await run('/usr/bin/systemctl', '--user', 'start', name)
                    value = json.loads(observed.read_text())['digest']
                    expected = None if label == 'unset' else '0'*64 if label == 'later-file' else verified.manifest.sha256
                    self.assertEqual(value, expected)
                    observations[label]['actual_digest'] = value
                    observed.unlink()
            # Replacement after asynchronous, actual manager observations.
            props = await read_unit_environment(prefix + '-valid.service')
            replacement = fixture.root / 'replacement.env'
            replacement.write_bytes(fixture.environment.read_bytes())
            replacement.chmod(0o400)
            os.replace(replacement, fixture.environment)
            with self.assertRaisesRegex(PermissionError, 'replaced'):
                verified.check_unit_environment(props)
        finally:
            if evidence:
                (evidence / 'commands.json').write_text(json.dumps(commands, indent=2))
                (evidence / 'observations.json').write_text(json.dumps(observations, indent=2))
                for file in fixture.root.iterdir():
                    if file.is_file():
                        shutil.copyfile(file, evidence / file.name)
            for path in unit_paths:
                subprocess.run(['/usr/bin/systemctl', '--user', 'stop', path.name],
                               check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
                state = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', path.name,
                                                 '-p', 'MainPID', '-p', 'Job', '-p', 'ControlGroup'],
                                                text=True, timeout=4)
                if evidence:
                    (evidence / (path.name + '.state')).write_text(state)
                self.assertIn('MainPID=0', state)
                self.assertIn('Job=\n', state)
                path.unlink()  # EXACT owned runtime fixture file; no reset/reload
            fixture.tearDown()
