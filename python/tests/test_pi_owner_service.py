import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest

from hyprneuro.pi_owner_service import SCHEMA, load_config, environment, service_lock, unit_template


class ServiceDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'home/workspace').mkdir(parents=True, mode=0o700)
        (self.root/'home').chmod(0o700)
        self.config = dict(schema=SCHEMA,root=str(self.root),source='/reviewed/source',node='/usr/bin/node',sdk='/installed/sdk.mjs',durable='/installed/durable',pi='/installed/pi',read_paths=['fixture.txt'],task_id='private-read')
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root/'owner.json').write_text(json.dumps(self.config))
        (self.root/'owner.json').chmod(0o600)

    def test_private_explicit_descriptor_env_has_no_ambient_grants(self):
        config=load_config(self.root)
        env=environment(config,self.root)
        self.assertEqual(env['HYPRNEURO_PI_PARENT_ONLY'],'1')
        self.assertEqual(env['HYPRNEURO_PI_PERSISTENT'],'1')
        self.assertEqual(env['HYPRNEURO_PI_CHILD_READ'],'0')
        self.assertNotIn('HYPRNEURO_RESIDENCY_DIR',env)
        self.assertNotIn('DSA_HOME',env)
        self.assertEqual(env['HOME'],str(self.root/'home'))
        self.assertNotIn('API_KEY',env)
        self.assertEqual(env['HYPRNEURO_PI_READ_PATHS'],'["fixture.txt"]')

    def test_scope_cannot_come_from_settings_or_expand_to_parent_absolute_directory(self):
        for paths in [[],['..'],['../private'],['/etc/passwd'],['.'],['a/../b'],['a/'],['a','a'],[{}],['\x00']]:
            self.config['read_paths']=paths;self.save()
            with self.assertRaises(ValueError):load_config(self.root)
        self.config['read_paths']=['fixture.txt'];self.config['approved']=True;self.save()
        with self.assertRaises(ValueError):load_config(self.root)

    def test_links_permissions_and_wrong_root_refused(self):
        (self.root/'owner.json').chmod(0o644)
        with self.assertRaises(ValueError):load_config(self.root)
        self.save();os.link(self.root/'owner.json',self.root/'alias')
        with self.assertRaises(ValueError):load_config(self.root)
        (self.root/'alias').unlink();(self.root/'owner.json').rename(self.root/'real')
        (self.root/'owner.json').symlink_to(self.root/'real')
        with self.assertRaises(OSError):load_config(self.root)

    def test_single_service_lock_across_owner_roots_and_kernel_release(self):
        one=service_lock(self.root)
        try:
            with self.assertRaises(BlockingIOError):service_lock(self.root)
            self.assertTrue(os.get_inheritable(one))
        finally:os.close(one)
        two=service_lock(self.root);os.close(two)
        self.assertEqual((self.root/'hyprneuro/pi-owner-service.lock').stat().st_mode&0o077,0)

    def test_unit_is_explicit_no_autostart_or_restart_and_pins_source(self):
        text=unit_template('/private/python','/reviewed/source')
        for token in ['Type=exec','Restart=no','UMask=0077','TimeoutStopSec=30','KillMode=control-group','ExecStart=:"/private/python"','PYTHONPATH=/reviewed/source/python/src',' %f']:
            self.assertIn(token,text)
        self.assertNotIn('[Install]',text);self.assertNotIn('WantedBy',text)
        with self.assertRaises(ValueError):unit_template('/bad\npath','/source')
        self.assertIn('%%',unit_template('/python%value','/source'))
