import unittest
from unittest.mock import AsyncMock
from hyprneuro.escalation import EscalationRouter
from hyprneuro.event_stream import MonitorEvent
from hyprneuro.models import Models
from hyprneuro.sidecar_store import SidecarStore
from test_alerting import _FakeModels, _FakeNotifier


class ExplanationTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_actual_text_separate_from_score_gate_and_unavailable(self):
        for enabled, fails in ((False,False), (True,False), (True,True)):
            with self.subTest(enabled=enabled, fails=fails):
                models = _FakeModels(score=.1)
                models.explain_alert = AsyncMock(side_effect=RuntimeError('classifier only') if fails else None,
                                                return_value='Actual model output about supplied evidence')
                store = SidecarStore(':memory:')
                notifier = _FakeNotifier()
                try:
                    result = await EscalationRouter(models,store,notifier=notifier,explanation_enabled=enabled).escalate(
                        MonitorEvent('resource','resource_alert','sustained pressure','warning','now'))
                    self.assertEqual(result['d1_score'],.1)
                    self.assertFalse(result['notify_recommended'])
                    self.assertEqual(notifier.sent,[])
                    if not enabled:
                        models.explain_alert.assert_not_awaited()
                        self.assertNotIn('model_explanation',result)
                    elif fails:
                        self.assertEqual(result['model_explanation_status'],'unavailable')
                        self.assertNotIn('model_explanation',result)
                    else:
                        self.assertEqual(result['model_explanation_status'],'generated')
                        self.assertIn('Actual D1',result['model_explanation_label'])
                        self.assertEqual(len(store.search(query='supplied')),1)
                finally:
                    store.close()

    async def test_model_text_endpoint_is_not_invented_from_score(self):
        models = Models.__new__(Models)
        calls = []
        def call(*args):
            calls.append(args)
            return {'choices':[{'message':{'content':'Real response'},'finish_reason':'stop'}]}
        models._call = call
        self.assertEqual(await models.explain_alert({'message':'data'}),'Real response')
        self.assertEqual(calls[0][0:2],('decision','/v1/chat/completions'))
        self.assertEqual(calls[0][-1],10)
