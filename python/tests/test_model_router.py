"""Unit tests for the deterministic model router (no inference)."""
import unittest

from hyprneuro.model_router import ModelRouter, TASK_KINDS, ROLES


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.r = ModelRouter()

    def test_ordinary_tasks_go_to_text(self):
        for kind in ("chat", "code", "tool", "general"):
            self.assertEqual(self.r.route(kind), "text")

    def test_multimodal_goes_to_omni(self):
        self.assertEqual(self.r.route("vision"), "omni")
        self.assertEqual(self.r.route("chat", has_multimodal=True), "omni")

    def test_classification_goes_to_decision(self):
        self.assertEqual(self.r.route("classify"), "decision")
        self.assertEqual(self.r.route("chat", needs_classification=True), "decision")

    def test_classification_is_most_specific(self):
        # A multimodal classification still routes to decision (classification wins).
        self.assertEqual(self.r.route("vision", needs_classification=True), "decision")

    def test_no_unnecessary_d1(self):
        for kind in TASK_KINDS:
            if kind != "classify":
                self.assertFalse(self.r.decision_required(kind))
        self.assertTrue(self.r.decision_required("classify"))

    def test_invalid_kind_and_flags(self):
        with self.assertRaises(ValueError):
            self.r.route("warp")
        with self.assertRaises(ValueError):
            self.r.route("chat", has_multimodal="yes")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.r = ModelRouter()

    def test_same_role_no_handoff(self):
        r = self.r.handoff("text", "text", {"summary": "x"})
        self.assertFalse(r["handoff"])
        self.assertEqual(r["reason"], "same_role")

    def test_text_to_omni_handoff_is_bounded(self):
        r = self.r.handoff("text", "omni", {
            "task_id": "t1", "app_id": "google-chrome",
            "summary": "Need to read the focused tab", "focus": "tab text",
            "evidence": "E" * 5000})
        self.assertTrue(r["handoff"])
        self.assertEqual(r["from"], "text")
        self.assertEqual(r["to"], "omni")
        self.assertEqual(r["schema"], "hyprneuro.handoff/1")
        self.assertTrue(r["untrusted"])
        self.assertLessEqual(len(r["evidence"]), 1200)  # truncated to bound

    def test_invalid_roles(self):
        with self.assertRaises(ValueError):
            self.r.handoff("text", "bogus", {})
        with self.assertRaises(ValueError):
            self.r.handoff("text", "omni", "not-a-dict")

    def test_all_roles_valid(self):
        self.assertEqual(ROLES, {"text", "omni", "decision"})


if __name__ == "__main__":
    unittest.main()
