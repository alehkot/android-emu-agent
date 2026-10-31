"""Offline contract tests; never send a real GitHub comment."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "GH_TOKEN": "github_pat_test_secret_value",
                "CI_REPO": "owner/repo",
                "CI_COMMIT_SHA": "a" * 40,
                "CI_PIPELINE_NUMBER": "42",
                "CI_PIPELINE_STATUS": "failure",
                "CI_WORKFLOW_NAME": "build",
                "CI_PIPELINE_URL": "https://ci.example.test/repos/1/pipeline/42",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_failure_excerpt_redacts_and_keeps_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "build.log"
            path.write_text(
                "noise\nsource.swift:7\n"
                "\x1b[31merror: github_pat_test_secret_value\x1b[0m\nexpected X\n"
            )
            text = report.failure_excerpt(path)
            self.assertIn("source.swift:7", text)
            self.assertIn("expected X", text)
            self.assertIn("[REDACTED]", text)
            self.assertNotIn("github_pat_", text)
            self.assertNotIn("\x1b", text)

    def test_missing_log_and_bounded_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "build.log"
            self.assertIn("No build log", report.failure_excerpt(path))
            path.write_text("x" * 200_000 + "last line")
            text = report.failure_excerpt(path)
            self.assertLessEqual(len(text), 12_000)
            self.assertTrue(text.endswith("last line"))

    def test_exact_sha_and_success_without_failure_log(self):
        os.environ["CI_PIPELINE_STATUS"] = "success"
        with patch.object(report, "failure_excerpt", side_effect=AssertionError):
            repo, sha, marker, body = report.make_report()
        self.assertEqual(repo, "owner/repo")
        self.assertEqual(sha, "a" * 40)
        self.assertIn(sha, body)
        self.assertIn("PASS", body)
        self.assertIn(marker, body)

    def test_invalid_metadata_fails_before_network(self):
        for key, value in [
            ("CI_COMMIT_SHA", "development"),
            ("CI_REPO", "../escape"),
            ("CI_PIPELINE_STATUS", "running"),
            ("CI_PIPELINE_URL", "file:///tmp/x"),
        ]:
            with (
                self.subTest(key=key),
                patch.dict(os.environ, {key: value}),
                patch.object(report, "api") as api,
            ):
                with self.assertRaises(ValueError):
                    report.main()
                api.assert_not_called()

    def test_create_and_update_only_own_matching_comment(self):
        marker = report.make_report()[2]
        other = {"id": 1, "user": {"id": 99}, "body": marker}
        own = {"id": 2, "user": {"id": 7}, "body": marker}
        for comments, expected in [([other], "POST"), ([other, own], "PATCH")]:
            with (
                self.subTest(expected=expected),
                patch.object(report, "api", side_effect=[{"id": 7}, comments, {}]) as api,
            ):
                report.main()
                self.assertEqual(api.call_args.args[0], expected)
                if expected == "POST":
                    self.assertIn("a" * 40, api.call_args.args[1])
                else:
                    self.assertTrue(api.call_args.args[1].endswith("/comments/2"))

    def test_pagination_and_api_failure(self):
        filler = [{"id": 1, "user": {"id": 99}, "body": "unrelated"}] * 100
        with patch.object(report, "api", side_effect=[{"id": 7}, filler, [], {}]) as api:
            report.main()
            self.assertIn("page=2", api.call_args_list[2].args[1])
        with (
            patch.object(report, "api", side_effect=OSError("offline")),
            self.assertRaises(OSError),
        ):
            report.main()

    def test_missing_token(self):
        os.environ.pop("GH_TOKEN")
        with patch.object(report, "api") as api:
            with self.assertRaises(ValueError):
                report.main()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
