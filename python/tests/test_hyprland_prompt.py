"""The desktop guidance is bounded advice, not tool/capture authorization."""
import unittest

from hyprneuro.agent import DEFAULT_SYSTEM


class HyprlandPromptTests(unittest.TestCase):
    def test_desktop_guidance_retains_safety_and_identity(self):
        for text in (
            "You are Hyprneuro", "running version", "untrusted data",
            "tools actually available and authorized", "grants no permissions",
            "never bypass locks", "running locker overrides",
            "independently permission-gated", "live application namespace",
            "Reload config only when authorized", "visual verification",
        ):
            with self.subTest(text=text):
                self.assertIn(text, DEFAULT_SYSTEM)

    def test_system_prompt_fits_existing_sidecar_bound(self):
        self.assertLess(len(DEFAULT_SYSTEM), 4000)
