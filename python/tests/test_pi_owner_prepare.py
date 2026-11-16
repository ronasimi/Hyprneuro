"""Fresh preparation only: no service, SDK, helper, models or permissions."""
import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from hyprneuro import pi_owner_service as service

class FreshLayoutTests(unittest.TestCase):
    def test_reserves_native_directories_before_freeze_without_adoption(self):
        with tempfile.TemporaryDirectory(prefix='hn-prepare-') as directory:
            root=Path(directory)/'owner'
            argv=['prepare',str(root),'--prepare','--read-path','fixture.txt']
            for key in ['source','node','sdk','durable','pi']:
                argv+=['--'+key,'/fixture/'+key]
            mask=os.umask(0o077)
            try:
                with patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()),patch.object(service.os,'execve') as execute:
                    self.assertEqual(service.main(),0)
                    config=service.load_config(root)
                    self.assertEqual(config['read_paths'],['fixture.txt'])
                    for name in ['home','agent','durable','sessions']:
                        self.assertEqual(stat.S_IMODE((root/name).stat().st_mode),0o700)
                    before=root.stat().st_nlink
                    # Native creates runtime files/subdirectories under these
                    # pre-reserved dirs; never rebaseline root identity later.
                    (root/'sessions/session.jsonl').write_text('fixture\n')
                    (root/'agent/nested').mkdir(mode=0o700)
                    self.assertEqual(root.stat().st_nlink,before)
                    descriptor=(root/'owner.json').read_bytes()
                    with self.assertRaises(FileExistsError):service.main()
                    self.assertEqual((root/'owner.json').read_bytes(),descriptor)
                    execute.assert_not_called()
            finally:os.umask(mask)
