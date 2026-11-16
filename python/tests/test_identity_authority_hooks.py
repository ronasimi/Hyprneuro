"""Host hook ordering/state tests with explicitly SYNTHETIC transport proofs.

These mocks are not real identity, grant or human acceptance; actual private
manager/GTK/SDK mixed-role integration is a separate required checkpoint.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
from hyprneuro.trusted_control import GrantControlServer
from hyprneuro.sidecar import SidecarServer


class AuthorityHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_slot_pending_dead_or_foreign_gate_never_refreshes(self):
        gate=SimpleNamespace(enter_operation=Mock())
        boundary=SimpleNamespace(state='connected',gate=gate,snapshot=AsyncMock())
        core=SimpleNamespace(slots={},registrations={})
        server=GrantControlServer(core,None);server.identity_client=boundary
        await server.refresh_authority('task')
        core.slots['task']=SimpleNamespace(registration='reg',published=False)
        core.registrations['reg']=SimpleNamespace(live=True,verification=gate)
        await server.refresh_authority('task')
        core.slots['task'].published=True;core.registrations['reg'].live=False
        await server.refresh_authority('task')
        core.registrations['reg'].live=True;core.registrations['reg'].verification=object()
        await server.refresh_authority('task')
        boundary.snapshot.assert_not_awaited();gate.enter_operation.assert_not_called()

    async def test_only_published_owned_live_slot_gets_fresh_oneuse_cohort(self):
        calls=[]
        gate=SimpleNamespace(enter_operation=lambda op:calls.append(('consume',op)))
        async def snapshot(op):calls.append(('snapshot',op))
        boundary=SimpleNamespace(state='connected',gate=gate,snapshot=snapshot)
        core=SimpleNamespace(slots={'task':SimpleNamespace(registration='reg',published=True)},
                             registrations={'reg':SimpleNamespace(live=True,verification=gate)})
        server=GrantControlServer(core,None);server.identity_client=boundary
        await server.refresh_authority('task')
        self.assertEqual(calls,[('snapshot','authorize'),('consume','authorize')])

    async def test_actual_async_dispatch_refreshes_before_permission_not_revoke(self):
        # Exercise the real dispatch_async body without constructing persistence,
        # models or a broker; dispatch is an explicit spy, not permission proof.
        calls=[]
        server=object.__new__(SidecarServer);server.trusted_consent=None
        async def refresh(task):calls.append(('refresh',task))
        server.authority_refresh=refresh
        server.dispatch=lambda request:calls.append(('dispatch',request['action'])) or {'fixture':True}
        await server.dispatch_async(dict(action='auth_check',task_id='task'))
        self.assertEqual(calls,[('refresh','task'),('dispatch','auth_check')])
        calls.clear();await server.dispatch_async(dict(action='auth_revoke',task_id='task'))
        self.assertEqual(calls,[('dispatch','auth_revoke')])
