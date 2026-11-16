"""External MAIN launch-root serialization; never human/production approval."""
import json
import os
import unittest
from hyprneuro.identity_root import ROOT_SCHEMA,load_launch_root
from test_identity_bootstrap import BootstrapTests


class LaunchRootTests(BootstrapTests):
    def setUp(self):
        super().setUp()
        self.record=self.root/'launch-root.json'
        self.generation='a'*32
        self.document=dict(schema=ROOT_SCHEMA,generation=self.generation,context_path=str(self.context),context_sha256=self.literal)
        self.write(self.record,json.dumps(self.document))
        self.record_literal=self.sha(self.record)

    def root_load(self):return load_launch_root(self.record,self.record_literal,self.generation)

    def test_main_literal_not_current_hash_or_self_claim(self):
        root=self.root_load();root.revalidate()
        with self.assertRaises(PermissionError):load_launch_root(self.record,'0'*64,self.generation)
        with self.assertRaises(PermissionError):load_launch_root(self.record,self.record_literal,'b'*32)
        self.record.unlink()
        with self.assertRaises(OSError):self.root_load()

    def test_root_same_bytes_replacement_after_open_denies(self):
        root=self.root_load()
        replacement=self.root/'replace.json';self.write(replacement,self.record.read_text());os.replace(replacement,self.record)
        with self.assertRaises(PermissionError):root.revalidate()

    def test_root_extra_duplicate_alias_and_context_drift_deny(self):
        for text in [json.dumps(dict(self.document,command='arbitrary')),json.dumps(self.document)[:-1]+',"generation":"'+self.generation+'"}']:
            self.write(self.record,text)
            with self.assertRaises(PermissionError):load_launch_root(self.record,self.sha(self.record),self.generation)
        self.write(self.record,json.dumps(self.document))
        root=self.root_load()
        self.write(self.context,self.context.read_text()+' ')
        with self.assertRaises(PermissionError):root.revalidate()

    def test_root_cannot_be_recursive_manifest_overlay(self):
        document=json.loads(self.manifest.read_text());document['files'][str(self.record)]=self.record_literal
        self.write(self.manifest,json.dumps(document))
        # Do not invent a fresh valid context to make a recursive root acceptable.
        with self.assertRaises(PermissionError):self.root_load()

    def test_pinned_runtime_credential_replacement_and_wrong_literal_deny(self):
        # Credential copy is a private filesystem fixture, not proof of manager
        # delivery. Real delivery/origin is tested in the unique-unit run.
        from dataclasses import replace
        from hyprneuro.identity_root import _credential
        credentials=self.root/'credentials';credentials.mkdir(mode=0o700)
        credential=credentials/'main-root-sha';self.write(credential,self.record_literal+'\n');credentials.chmod(0o500)
        literal,identity=_credential(credential)
        self.assertEqual(literal,self.record_literal)
        source=self.root/'MAIN-root.sha256';self.write(source,literal+'\n')
        from hyprneuro.identity_bootstrap import FilePin
        pin=FilePin(source,self.sha(source),os.getuid(),0o400);_,source_identity=pin.read(limit=65)
        root=replace(self.root_load(),credential_path=credential,credential_identity=identity,source_identity=source_identity)
        root.revalidate()
        credentials.chmod(0o700)
        alternate=credentials/'new';self.write(alternate,literal+'\n');os.replace(alternate,credential);credentials.chmod(0o500)
        with self.assertRaises(PermissionError):root.revalidate()
        credentials.chmod(0o700)

    def test_all_credential_overrides_and_extra_sources_denied(self):
        from hyprneuro.identity_credentials import require_root_credential
        source=self.root/'MAIN-root.sha256'
        good=dict(LoadCredential=[['main-root-sha',str(source)]],LoadCredentialEncrypted=False,
                  SetCredential=False,SetCredentialEncrypted=False,ImportCredential=False,ImportCredentialEx=False)
        require_root_credential(good,source)
        for key in good:
            bad=dict(good)
            bad[key]=[['main-root-sha','/other']] if key=='LoadCredential' else True
            with self.subTest(key=key),self.assertRaises(PermissionError):require_root_credential(bad,source)
