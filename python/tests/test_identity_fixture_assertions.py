"""Offline cleanup oracle negatives; no SQL, activation, SDK or helper spawn."""
import copy
from pathlib import Path
import unittest
from identity_fixture_assertions import require_clean_result

class CleanupOracleTests(unittest.TestCase):
    def setUp(self):
        self.root=Path('/private/fixture')
        self.result={'rows':[{'task_id':'source-observer-private','app_id':'hyprneuro-parent-read',
                              'file_prefix':str(self.root/'owner/home/workspace'),'ops':['read'],
                              'status':'revoked','approved':False,'created_ms':0}],
                     'live_registrations':0,'published':0,'observer_cleanup_confirmed':True,'failures':0}
    def test_retained_exact_revoked_row_is_clean(self):require_clean_result(self.result,self.root)
    def test_active_approved_foreign_extra_or_uncertain_never_passes(self):
        for field,value in [('status','active'),('approved',True),('task_id','foreign'),
                            ('app_id','foreign'),('file_prefix','/elsewhere'),('ops',['read','write']),('created_ms',1)]:
            result=copy.deepcopy(self.result);result['rows'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):require_clean_result(result,self.root)
        for field,value in [('rows',[]),('rows',self.result['rows']*2),('live_registrations',1),
                            ('published',1),('observer_cleanup_confirmed',False),('failures',1)]:
            result=copy.deepcopy(self.result);result[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):require_clean_result(result,self.root)

    def test_row_only_assertion_does_not_relabel_unknown_receipt(self):
        from identity_fixture_assertions import require_revoked_rows
        result=copy.deepcopy(self.result);result.update(observer_cleanup_confirmed=False,failures=2)
        before=copy.deepcopy(result)
        require_revoked_rows(result['rows'],self.root)
        self.assertEqual(result,before)
        with self.assertRaises(AssertionError):require_clean_result(result,self.root)


    def test_clean_child_exit_is_not_a_backend_cleanup_receipt(self):
        from identity_fixture_assertions import require_unknown_channel
        result=copy.deepcopy(self.result);result.update(observer_cleanup_confirmed=False,failures=1)
        for status in (0,1):require_unknown_channel(result,status)
        for status in (-9,2,True):
            with self.subTest(status=status),self.assertRaises(AssertionError):require_unknown_channel(result,status)
        for field,value in [('observer_cleanup_confirmed',True),('live_registrations',1),('published',1),('failures',0)]:
            changed=dict(result,**{field:value})
            with self.subTest(field=field),self.assertRaises(AssertionError):require_unknown_channel(changed,0)
