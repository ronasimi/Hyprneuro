"""Unit tests for the task-scoped permission broker (model-free)."""
import unittest

from hyprneuro.authorization import (
    PermissionBroker, PRIVILEGED_OPS, NORMAL_OPS, _path_within,
)


class AuthorizeTests(unittest.TestCase):
    def setUp(self):
        self.b = PermissionBroker()  # in-memory

    def test_authorize_normal_ops(self):
        r = self.b.authorize("t1", app_id="kitty", file_prefix="/tmp/work",
                             ops=("read", "write"))
        self.assertTrue(r["authorized"])
        self.assertEqual(r["ops"], ["read", "write"])
        self.assertFalse(r["approved"])

    def test_privileged_ops_require_approval(self):
        with self.assertRaises(PermissionError):
            self.b.authorize("t1", ops=("read", "desktop_control"))  # no approval
        r = self.b.authorize("t1", ops=("read", "desktop_control"), approved=True)
        self.assertTrue(r["approved"])

    def test_unknown_ops_rejected(self):
        with self.assertRaises(ValueError):
            self.b.authorize("t1", ops=("read", "teleport"))

    def test_file_prefix_must_be_safe(self):
        with self.assertRaises(ValueError):
            self.b.authorize("t1", file_prefix="relative/path")
        with self.assertRaises(ValueError):
            self.b.authorize("t1", file_prefix="/tmp/../etc")

    def test_approved_must_be_bool(self):
        with self.assertRaises(ValueError):
            self.b.authorize("t1", approved="yes")


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.b = PermissionBroker()

    def test_no_scope_denied(self):
        r = self.b.check("missing", "read")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["reason"], "no_authorization")

    def test_allowed_within_scope(self):
        self.b.authorize("t1", app_id="kitty", file_prefix="/tmp/work",
                         ops=("read", "write"))
        self.assertTrue(self.b.check("t1", "read", app_id="kitty", path="/tmp/work/a.txt")["allowed"])
        self.assertTrue(self.b.check("t1", "write", app_id="kitty", path="/tmp/work/sub/b.txt")["allowed"])

    def test_operation_not_authorized(self):
        self.b.authorize("t1", ops=("read",))
        self.assertEqual(self.b.check("t1", "write")["reason"], "operation_not_authorized")

    def test_privileged_requires_approval_even_if_in_ops(self):
        # A scope that includes a privileged op but was NOT approved still denies it.
        # (authorize() blocks creating such a scope, so build it directly via expand.)
        self.b.authorize("t1", ops=("read",))
        # expand without approval -> not expanded
        r = self.b.expand("t1", ops=("read", "delete"), approved=False)
        self.assertFalse(r["expanded"])
        self.assertEqual(self.b.check("t1", "delete")["reason"], "operation_not_authorized")
        # expand with approval -> granted
        self.b.expand("t1", ops=("read", "delete"), approved=True)
        self.assertTrue(self.b.check("t1", "delete")["allowed"])

    def test_app_out_of_scope(self):
        self.b.authorize("t1", app_id="kitty", ops=("read",))
        r = self.b.check("t1", "read", app_id="google-chrome")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["reason"], "app_out_of_scope")

    def test_path_out_of_scope(self):
        self.b.authorize("t1", file_prefix="/tmp/work", ops=("read",))
        r = self.b.check("t1", "read", path="/etc/passwd")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["reason"], "path_out_of_scope")

    def test_revoked_scope_denies(self):
        self.b.authorize("t1", ops=("read",))
        self.b.revoke("t1")
        self.assertEqual(self.b.check("t1", "read")["reason"], "scope_revoked")

    def test_unknown_op_raises(self):
        with self.assertRaises(ValueError):
            self.b.check("t1", "teleport")


class PathWithinTests(unittest.TestCase):
    def test_within(self):
        self.assertTrue(_path_within("/tmp/work", "/tmp/work/a/b.txt"))
        self.assertTrue(_path_within("/tmp/work", "/tmp/work"))
        self.assertFalse(_path_within("/tmp/work", "/tmp/workx/a.txt"))
        self.assertFalse(_path_within("/tmp/work", "/etc/passwd"))
        self.assertFalse(_path_within("/tmp/work", "/tmp/work/../../etc"))
        self.assertFalse(_path_within("/tmp/work", "relative/path"))


class StoreBackedBrokerTests(unittest.TestCase):
    def test_roundtrip_through_store(self):
        import json, tempfile
        from pathlib import Path
        from hyprneuro.sidecar_store import SidecarStore
        with tempfile.TemporaryDirectory() as d:
            store = SidecarStore(Path(d) / "auth.db")
            try:
                b = PermissionBroker(store)
                b.authorize("t1", app_id="kitty", file_prefix="/tmp/work",
                            ops=("read", "write"))
                b.authorize("t2", ops=("read", "delete"), approved=True)
                self.assertTrue(b.check("t1", "read", app_id="kitty", path="/tmp/work/x")["allowed"])
                self.assertTrue(b.check("t2", "delete")["allowed"])
                self.assertEqual(len(b.list()), 2)
                b.revoke("t2")
                self.assertEqual(b.check("t2", "delete")["reason"], "scope_revoked")
                # Persistence: a fresh broker over the same store sees the scopes.
                b2 = PermissionBroker(store)
                self.assertEqual(len(b2.list()), 2)
                self.assertTrue(b2.check("t1", "read", app_id="kitty", path="/tmp/work/x")["allowed"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
