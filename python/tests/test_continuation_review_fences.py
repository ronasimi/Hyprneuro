"""Private real-preflight filesystem/systemd-state regressions; no live services."""
import hashlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import continue_app_acceptance as ctrl
import continuation_context as binding
import prepare_app_release as prep
import guard_app_release as guard
import apply_app_release as apply
import verify_app_release as verify

class EffectiveUnitTests(unittest.TestCase):
    def test_real_preflight_rejects_base_content_redirect_and_extra_loaded_dropin_before_effects(self):
        for fault in ['base-content','fragment-redirect','extra-dropin']:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as d:
                root=Path(d);bundle=root/'bundle';attempt=root/'attempt';bundle.mkdir();attempt.mkdir()
                source=bundle/'source';stage=bundle/'staged';source.mkdir();stage.mkdir()
                source_files={};staged={}
                for folder,count,items in [(source,301,source_files),(stage,11,staged)]:
                    for i in range(count):p=folder/str(i);p.write_text('fixture');items[str(i)]=binding.digest(p)
                base=root/'base.service';base.write_text('REVIEWED BASE');drop=root/'release.conf';drop.write_text('NEW RELEASE');backup=root/'archive';backup.write_text('backup')
                native=root/'native';native.mkdir();runtime=root/'runtime';runtime.mkdir();audit=root/'audit';audit.write_text('')
                (bundle/'backup').mkdir();(bundle/'backup/hyprneuro-ui').write_text('old UI')
                units=[dict(path=str(base),sha256=binding.digest(base)),dict(path=str(drop),sha256='OLD REPLACED HASH')]
                identity=dict(unit='hyprneuro.service',fragment=str(base),dropins=[str(drop)])
                m=dict(source_files=source_files,staged_files=staged,units=units,sidecar=identity,ui=dict(identity,unit='hyprneuro-ui.service'),database=dict(backup=str(backup),backup_sha256=binding.digest(backup)),installed_sha256=binding.digest(bundle/'backup/hyprneuro-ui'),models=[],owner=str(native),runtime=str(runtime),owner_unit='synthetic-owner',consent_journal=str(audit))
                (bundle/'manifest.json').write_text(json.dumps(m))
                context=dict(id='synthetic',installed_files={str(drop):binding.digest(drop)},installed_modes={str(drop):drop.stat().st_mode&0o777},preserved_files={},workspace=4)
                extra=root/'extra.conf';extra.write_text('loaded EXTRA')
                if fault=='base-content':base.write_text('CHANGED BASE')
                def manager(*args,**kwargs):
                    if 'list-units' in args:return '[]'
                    if 'NeedDaemonReload' in args:return 'no'
                    if 'FragmentPath' in args:
                        fragment=str(extra) if fault=='fragment-redirect' else str(base)
                        paths=str(drop)+(' '+str(extra) if fault=='extra-dropin' else '')
                        return 'FragmentPath='+fragment+'\nDropInPaths='+paths
                    if args[:3]==('hyprctl','-j','activeworkspace'):return '{"id":4,"windows":0}'
                    return '{}'
                health=Mock();health.__enter__=lambda self:io.StringIO('{"status":"ok"}');health.__exit__=lambda *args:None
                with patch.object(ctrl,'load_context',return_value=context),patch.object(apply,'desktop_safe'),patch.object(verify,'check_unit_backups'),patch.object(prep,'run',side_effect=manager),patch.object(prep,'check_moe_inert'),patch.object(prep,'check_owner_inert'),patch.object(guard,'unit_state',return_value=dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',ControlGroup='')),patch.object(ctrl.urllib.request,'urlopen',return_value=health),patch.object(ctrl.subprocess,'run') as effects:
                    with self.assertRaisesRegex(RuntimeError,'unit|Unit|baseline|Baseline|fragment|Fragment'):
                        ctrl.preflight(bundle,attempt,'synthetic',**({'context_sha256':'a'*64} if 'context_sha256' in ctrl.preflight.__code__.co_varnames else {}))
                    effects.assert_not_called()
                self.assertEqual(list(attempt.iterdir()),[])

class ContextPinTests(unittest.TestCase):
    def test_same_mode_replacement_cannot_reset_failed_file_or_workspace_baseline(self):
        for field,value in [('original_failed_files',{}),('workspace',99)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                base=Path(d);bundle=base/'bundle';attempt=base/'attempt';bundle.mkdir(mode=0o700);attempt.mkdir(mode=0o700)
                manifest=bundle/'manifest.json';manifest.write_text('SYNTHETIC');pin=binding.digest(manifest)
                old=bundle/'operation.started';old.write_text('FAILED ORIGINAL');entry=base/'entry';entry.write_text('CODE')
                data=dict(version=1,id=attempt.name,bundle=str(bundle),manifest_sha256=pin,entry=str(entry),driver=str(entry),external_files={str(entry):binding.digest(entry)},original_failed_files={str(old):binding.digest(old)},workspace=4)
                file=attempt/'continuation-context.json';file.write_text(json.dumps(data));file.chmod(0o400);approved=binding.digest(file)
                def load():
                    # Old-code adapter only to retain meaningful FAIL-before proof.
                    if 'expected_sha' in binding.load_context.__code__.co_varnames:return binding.load_context(bundle,attempt,approved)
                    return binding.load_context(bundle,attempt)
                with patch.object(binding,'MANIFEST',pin):
                    load();(attempt/'operation.started').write_text(json.dumps(dict(context_sha256=approved)))
                    replacement=attempt/'replacement';data[field]=value;replacement.write_text(json.dumps(data));replacement.chmod(0o400);replacement.replace(file)
                    with self.assertRaisesRegex(RuntimeError,'context|Context'):load()

    def test_postmarker_controller_watcher_and_result_reloads_keep_the_launch_pin(self):
        import time
        import watch_app_acceptance as watcher
        import ordinary_app_acceptance as driver
        import wait_app_acceptance as waiter
        for actor in ['controller','watcher','coordinator']:
            with self.subTest(actor=actor),tempfile.TemporaryDirectory() as d:
                base=Path(d);bundle=base/'bundle';attempt=base/'attempt';bundle.mkdir(mode=0o700);attempt.mkdir(mode=0o700)
                manifest=bundle/'manifest.json';manifest.write_text('{"owner_descriptor_sha256":"synthetic"}');manifest.chmod(0o600);pin=binding.digest(manifest)
                old=bundle/'operation.started';old.write_text('FAILED ORIGINAL');entry=base/'entry';entry.write_text('CODE')
                data=dict(version=1,id=attempt.name,bundle=str(bundle),manifest_sha256=pin,entry=str(entry),driver=str(entry),external_files={str(entry):binding.digest(entry)},original_failed_files={str(old):binding.digest(old)},workspace=4)
                file=attempt/'continuation-context.json';file.write_text(json.dumps(data));file.chmod(0o400);approved=binding.digest(file)
                def replace():
                    changed=dict(data,original_failed_files={},workspace=99);tmp=attempt/'replacement';tmp.write_text(json.dumps(changed));tmp.chmod(0o400);tmp.replace(file)
                with patch.object(binding,'MANIFEST',pin):
                    if actor=='controller':
                        writer=ctrl.write_state
                        def record(*args):writer(*args);replace()
                        with patch.object(ctrl,'preflight',return_value=(data,{})),patch.object(ctrl,'write_state',side_effect=record),patch.object(apply,'desktop_safe'),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}),patch.object(ctrl.subprocess,'run') as effects:
                            self.assertEqual(ctrl.execute(bundle,attempt,'synthetic',True,True,approved),1)
                            effects.assert_not_called()
                    elif actor=='watcher':
                        marker=attempt/'operation.started';marker.write_text('NEW');marker.chmod(0o600)
                        select_real=watcher.select.select
                        def edge(*args):replace();return select_real(*args)
                        with patch.object(watcher.select,'select',side_effect=edge):
                            with self.assertRaisesRegex(RuntimeError,'context'):watcher.watch(bundle,0,1,pin,attempt,approved)
                    else:
                        result=attempt/'acceptance-result.json';result.write_text('present')
                        def wait(*args,**kwargs):replace();return 0
                        with patch.object(waiter,'wait',side_effect=wait):
                            with self.assertRaisesRegex(RuntimeError,'context'):driver.coordinator(attempt,time.monotonic()+1,True,lambda:binding.load_context(bundle,attempt,approved))
                self.assertEqual(old.read_text(),'FAILED ORIGINAL')
