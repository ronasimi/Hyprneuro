"""Independently pinned bootstrap bytes, never model/consent authority fixtures."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from hyprneuro.identity_bootstrap import (CONTEXT_SCHEMA, DIGEST_VARIABLE, MANIFEST_SCHEMA,
                                          load_reviewed_bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hn-bootstrap-')
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.environment = self.root / 'bootstrap.env'
        self.manifest = self.root / 'manifest.json'
        self.context = self.root / 'context.json'
        # Freeze unit -> manifest -> bootstrap -> externally reviewed context.
        self.unit = self.root / 'private.service'
        self.unit.write_text('[Service]\nEnvironmentFile=' + str(self.environment) + '\n')
        self.write(self.manifest, json.dumps({'schema': MANIFEST_SCHEMA,
                                            'files': {str(self.unit): self.sha(self.unit)}}))
        self.write(self.environment, DIGEST_VARIABLE + '=' + self.sha(self.manifest) + '\n')
        for p in [self.manifest, self.environment]:
            p.chmod(0o400)
        self.write_context()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def write(path, text):
        if path.exists():
            path.chmod(0o600)  # ONLY this owned mutation fixture
        path.write_text(text)
        path.chmod(0o400)

    def write_context(self):
        def pin(p):
            return dict(path=str(p), sha256=self.sha(p), uid=os.getuid(), mode=0o400)
        self.write(self.context, json.dumps(dict(schema=CONTEXT_SCHEMA,
                                               bootstrap=pin(self.environment), manifest=pin(self.manifest))))
        self.context.chmod(0o400)
        self.literal = self.sha(self.context)

    def load(self):
        return load_reviewed_bootstrap(self.context, self.literal)

    def properties(self):
        return dict(EnvironmentFiles=[[str(self.environment), False]], Environment=[],
                    PassEnvironment=[], UnsetEnvironment=[])

    def test_cycle_free_generation_and_exact_fixed_digest(self):
        original_unit = self.unit.read_bytes()
        original_manifest = self.manifest.read_bytes()
        verified = self.load()
        verified.check_unit_environment(self.properties())
        verified.check_process_environment({DIGEST_VARIABLE: self.sha(self.manifest)})
        self.assertEqual(self.unit.read_bytes(), original_unit)
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertNotIn(verified.manifest.sha256.encode(), original_unit)
        self.assertEqual(verified.manifest_bytes, original_manifest)

    def test_environment_value_cannot_authenticate_wrong_context(self):
        with self.assertRaises(PermissionError):
            load_reviewed_bootstrap(self.context, '0' * 64)
        with self.assertRaises(PermissionError):
            self.load().check_process_environment({DIGEST_VARIABLE: '0' * 64})
        with self.assertRaises(PermissionError):
            self.load().check_process_environment({})

    def test_unit_precedence_optional_extra_duplicates_and_overrides_reject(self):
        for key, wrong in [('EnvironmentFiles', []),
                           ('EnvironmentFiles', [[str(self.environment), True]]),
                           ('EnvironmentFiles', [[str(self.environment), False]] * 2),
                           ('EnvironmentFiles', [[str(self.root / 'other.env'), False]]),
                           ('Environment', [DIGEST_VARIABLE + '=' + self.sha(self.manifest)]),
                           ('PassEnvironment', [DIGEST_VARIABLE]),
                           ('UnsetEnvironment', [DIGEST_VARIABLE])]:
            with self.subTest(key=key, wrong=wrong):
                props = self.properties()
                props[key] = wrong
                with self.assertRaises(PermissionError):
                    self.load().check_unit_environment(props)

    def test_same_bytes_atomic_replacement_after_observation_rejects(self):
        for target in [self.context, self.environment, self.manifest]:
            with self.subTest(target=target):
                verified = self.load()
                replacement = self.root / 'replacement'
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o400)
                os.replace(replacement, target)
                with self.assertRaises(PermissionError):
                    verified.revalidate()

    def test_mutation_missing_symlink_and_hardlink_alias_reject(self):
        for kind in ['missing', 'mutated', 'symlink', 'hardlink', 'mode']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as sub:
                p = Path(sub) / 'environment'
                if kind == 'missing':
                    self.environment.unlink()
                elif kind == 'mutated':
                    self.write(self.environment, DIGEST_VARIABLE + '=' + '0' * 64 + '\n')
                elif kind == 'symlink':
                    p.write_bytes(self.environment.read_bytes())
                    self.environment.unlink()
                    self.environment.symlink_to(p)
                elif kind == 'hardlink':
                    os.link(self.environment, p)
                else:
                    self.environment.chmod(0o644)
                try:
                    with self.assertRaises((PermissionError, OSError)):
                        self.load()
                finally:
                    if self.environment.is_symlink() or not self.environment.exists():
                        self.environment.unlink(missing_ok=True)
                    self.write(self.environment, DIGEST_VARIABLE + '=' + self.sha(self.manifest) + '\n')
                    self.environment.chmod(0o400)
                    self.write_context()

    def test_extra_lines_quotes_or_endpoint_selectors_never_become_digest(self):
        for raw in [DIGEST_VARIABLE + '="' + self.sha(self.manifest) + '"\n',
                    DIGEST_VARIABLE + '=' + self.sha(self.manifest) + '\nENDPOINT=/arbitrary\n',
                    DIGEST_VARIABLE + '=' + self.sha(self.manifest) + '\n' + DIGEST_VARIABLE + '=' + '0'*64 + '\n']:
            self.write(self.environment, raw)
            self.write_context()  # Even independently pinned bad syntax is rejected.
            with self.assertRaises(PermissionError):
                self.load()

    def test_bootstrap_is_excluded_from_manifest_self_catalog(self):
        self.write(self.manifest, json.dumps({'schema': MANIFEST_SCHEMA,
                                            'files': {str(self.environment): '0' * 64}}))
        self.write(self.environment, DIGEST_VARIABLE + '=' + self.sha(self.manifest) + '\n')
        self.write_context()
        with self.assertRaisesRegex(PermissionError, 'Recursive'):
            self.load()

    def test_duplicate_context_keys_cannot_shadow_independent_pin(self):
        raw = self.context.read_text()
        self.write(self.context, '{"schema":"WRONG",' + raw[1:])
        self.literal = self.sha(self.context)
        with self.assertRaisesRegex(PermissionError, 'Duplicate'):
            self.load()
