"""Offline report regressions only; NOT actual lifetime acceptance."""
import copy
import unittest
from identity_soak_fixture import soak_metrics

class SoakMetricsTests(unittest.TestCase):
    def test_service_metadata_without_process_start_stays_unknown(self):
        session=dict(started_ns=0,deadline_ns=7200000000000,observed_ns=1000000000,monotonic_ns=1000000000,helper={'pid':1})
        expiry=dict(observed_ns=7201000000000)
        seal=dict(boottime_ns=7200001000000)
        heartbeats=[dict(boottime_ns=1,monotonic_ns=1,ticks=1),dict(boottime_ns=60000000001,monotonic_ns=60000000001,ticks=1200)]
        original=copy.deepcopy(session);report=soak_metrics(session,expiry,seal,heartbeats,100)
        self.assertEqual(session,original)
        self.assertIsNone(report['active_helper_startup_gap_ns'])
        self.assertFalse(report['helper_process_start_recorded'])
        self.assertEqual(report['source_seal_delay_ns'],1000000)
        self.assertEqual(report['helper_verified_observation_span_ns'],7199001000000)
        self.assertFalse(report['real_suspend_acceptance'])
        self.assertEqual(report['monitor_ticks_at_last_heartbeat'],1200)
        self.assertNotIn('helper_termination_confirmed_before_fixture_cleanup',report)
        session['helper_start_ticks']=100
        report=soak_metrics(session,expiry,seal,heartbeats,100)
        self.assertTrue(report['helper_process_start_recorded'])
        self.assertEqual(report['active_helper_startup_gap_ns'],1000000000)
