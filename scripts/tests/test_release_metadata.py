import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_metadata import release_plan


class ReleasePolicyTests(unittest.TestCase):
    def test_main_publishes_development_images(self):
        plan = release_plan("Remi-Z/Release-Holic", "push", "refs/heads/main")
        self.assertEqual(plan["backend_image"], "ghcr.io/remi-z/release-holic-backend")
        self.assertEqual(plan["publish"], "true")
        self.assertEqual(plan["release"], "false")

    def test_pull_requests_cannot_publish(self):
        self.assertEqual(release_plan("Remi-Z/Release-Holic", "pull_request", "refs/heads/main")["publish"], "false")

    def test_non_main_branches_cannot_publish(self):
        self.assertEqual(release_plan("Remi-Z/Release-Holic", "push", "refs/heads/feature")["publish"], "false")

    def test_manual_main_build_can_publish(self):
        self.assertEqual(release_plan("Remi-Z/Release-Holic", "workflow_dispatch", "refs/heads/main")["publish"], "true")

    def test_stable_release_can_promote_latest(self):
        plan = release_plan("Remi-Z/Release-Holic", "push", "refs/tags/v0.1.0")
        self.assertEqual((plan["publish"], plan["release"], plan["prerelease"]), ("true", "true", "false"))

    def test_prerelease_cannot_promote_latest(self):
        plan = release_plan("Remi-Z/Release-Holic", "push", "refs/tags/v0.1.0-rc.1")
        self.assertEqual((plan["release"], plan["prerelease"]), ("true", "true"))

    def test_invalid_release_tags_fail_before_publication(self):
        for tag in ["v1", "v1.2", "v01.2.3", "v1.2.3-01", "v1.2.3+build.1", "vbad", "v1.2.3-" + "x" * 128]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release_plan("Remi-Z/Release-Holic", "push", "refs/tags/" + tag)

    def test_output_cannot_contain_injected_lines(self):
        with self.assertRaises(ValueError):
            release_plan("Remi-Z/Release-Holic\npublish=true", "push", "refs/heads/main")


if __name__ == "__main__":
    unittest.main()
