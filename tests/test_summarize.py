"""scripts/summarize.py: merges every persona's findings.json into SUMMARY.md."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import summarize  # noqa: E402

FINDINGS = {
    "anna": {"score": 6, "issues": [
        {"title": "Send button cut at large text", "severity": "major", "screen": "Send"},
        {"title": "Icon buttons have no name", "severity": "minor", "screen": "Home"}]},
    "noah": {"score": 8, "issues": [
        {"title": "send button cut at large text", "severity": "minor", "screen": "Send"},
        {"title": "App crashes on rotate | landscape", "severity": "blocker", "screen": "Home"}]},
    "kenji": {"score": 7, "issues": [
        {"title": "Icon buttons have no name", "severity": "minor", "screen": "Settings"}]},
}


def write_run(base, findings):
    """Same layout as a decrypted run: <persona>/results/<persona>/findings.json"""
    for persona, data in findings.items():
        d = Path(base, persona, "results", persona)
        d.mkdir(parents=True)
        (d / "findings.json").write_text(json.dumps(data) if isinstance(data, dict) else data, encoding="utf-8")


class Summary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_run(self.tmp.name, FINDINGS)
        self.findings, self.scores = summarize.load(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_reads_every_persona(self):
        self.assertEqual(len(self.findings), 5)
        self.assertEqual(sorted(self.scores), [6, 7, 8])
        self.assertEqual({f["persona"] for f in self.findings}, {"anna", "noah", "kenji"})

    def test_broken_findings_file_is_skipped(self):
        write_run(self.tmp.name, {"olga": "{not json"})
        self.assertEqual(len(summarize.load(self.tmp.name)[0]), 5)

    def test_identical_titles_merge_whatever_the_case(self):
        groups = summarize.group_by_title(self.findings)
        self.assertEqual(sorted(len(g["ids"]) for g in groups), [1, 2, 2])

    def test_most_severe_first_then_most_personas(self):
        md = summarize.render(self.findings, self.scores, summarize.group_by_title(self.findings), False)
        table = [line for line in md.splitlines() if line.startswith("| ") and "Severity" not in line]
        self.assertTrue(table[0].startswith("| blocker | App crashes on rotate \\| landscape"))
        self.assertTrue(table[1].startswith("| major | Send button cut at large text | 2 (anna, noah)"))
        self.assertIn("5 reports from 3 personas, average score 7.0/10.", md)

    def test_no_claude_call_when_grouping_is_off(self):
        with mock.patch.dict(os.environ, {"SUMMARY_GROUPING": "0"}), mock.patch.object(summarize.subprocess, "run") as run:
            self.assertIsNone(summarize.group_with_claude(self.findings))
            run.assert_not_called()

    def test_claude_answer_is_checked_before_use(self):
        # ids follow persona order: anna 1-2, kenji 3, noah 4-5
        answer = {"groups": [
            {"title": "Send button cut", "class": "layout and text size", "ids": [1, "4", 99]},
            {"title": "Icon buttons with no name", "class": "made-up class", "ids": [4, 2, 3]},
            "not a group"]}
        reply = mock.Mock(stdout=json.dumps({"result": "Here:\n" + json.dumps(answer)}))
        with mock.patch.dict(os.environ, {"SUMMARY_GROUPING": "1"}), \
                mock.patch.object(summarize.shutil, "which", return_value="/usr/bin/claude"), \
                mock.patch.object(summarize.subprocess, "run", return_value=reply), \
                contextlib.redirect_stderr(io.StringIO()):
            groups = summarize.group_with_claude(self.findings)
        # unknown id dropped, an id used twice kept once, unknown class emptied
        self.assertEqual(groups[0], {"title": "Send button cut", "class": "layout and text size", "ids": [1, 4]})
        self.assertEqual(groups[1], {"title": "Icon buttons with no name", "class": "", "ids": [2, 3]})
        self.assertEqual([g["ids"] for g in groups[2:]], [[5]])  # a report Claude forgot stays, alone

    def test_unusable_claude_answer_falls_back_to_titles(self):
        with mock.patch.dict(os.environ, {"SUMMARY_GROUPING": "1"}), \
                mock.patch.object(summarize.shutil, "which", return_value="/usr/bin/claude"), \
                mock.patch.object(summarize.subprocess, "run", return_value=mock.Mock(stdout="usage limit")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(summarize.group_with_claude(self.findings))

    def test_command_line(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/summarize.py"), self.tmp.name],
                             env=dict(os.environ, SUMMARY_GROUPING="0"), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("# Agent test summary\n"))
        self.assertIn("install the claude CLI", out.stdout)


class Reproduction(unittest.TestCase):
    """A run with bug_report: each persona answers whether it reproduced the bug."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_run(self.tmp.name, {
            "anna": {"reproduced": "no", "evidence": ["09"], "note": "Every tab opens", "issues": []},
            "layla": {"reproduced": "YES", "evidence": ["04", "05"], "note": "Crash | on Send",
                      "issues": [{"title": "Arabic digits mixed", "severity": "minor", "screen": "Send"}]},
            "kenji": {"reproduced": "maybe", "evidence": "not a list", "issues": []},
        })
        Path(self.tmp.name, "layla", "results", "bug_report.md").write_text(
            "# bug: Clicking any of the tabs crashes\n\nReported in https://example.com/1\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_title_and_odd_answers(self):
        rows, title = summarize.load_reproduction(self.tmp.name)
        self.assertEqual(title, "bug: Clicking any of the tabs crashes")
        self.assertEqual({r["persona"]: r["result"] for r in rows}, {"anna": "no", "layla": "yes", "kenji": "unclear"})
        self.assertEqual([r["evidence"] for r in rows if r["persona"] == "kenji"], [[]])

    def test_table_comes_first_yes_then_unclear_then_no(self):
        findings, scores = summarize.load(self.tmp.name)
        md = summarize.render(findings, scores, summarize.group_by_title(findings), False,
                              summarize.load_reproduction(self.tmp.name))
        self.assertTrue(md.startswith("# Agent test summary\n\n## Reproduction\n"))
        self.assertIn("Reproduced on 1 of 3 devices, not reproduced on 1, unclear on 1.", md)
        rows = [line for line in md.splitlines() if line.startswith(("| yes", "| no", "| unclear"))]
        self.assertEqual([r.split(" | ")[1] for r in rows], ["layla", "kenji", "anna"])
        self.assertEqual(rows[0], "| yes | layla | Pixel 6, Android 13 | ar-EG | x1.15 | 04, 05 | Crash \\| on Send |")
        self.assertIn("## Everything else the agents reported", md)
        self.assertIn("| minor | Arabic digits mixed | 1 (layla) | Send |", md)

    def test_ios_persona_shows_simulator_and_text_size(self):
        self.assertEqual(summarize.phone(summarize.personas_by_id()["clara"]),
                         ("iPhone SE (3rd generation), iOS 18", "fr-FR", "large"))

    def test_a_normal_run_has_no_reproduction_table(self):
        with tempfile.TemporaryDirectory() as d:
            write_run(d, FINDINGS)
            rows, _ = summarize.load_reproduction(d)
            findings, scores = summarize.load(d)
            md = summarize.render(findings, scores, summarize.group_by_title(findings), False, (rows, ""))
        self.assertEqual(rows, [])
        self.assertNotIn("Reproduction", md)

    def test_command_line_with_nothing_else_reported(self):
        with tempfile.TemporaryDirectory() as d:
            write_run(d, {"olga": {"reproduced": "no", "evidence": ["03"], "issues": []}})
            out = subprocess.run([sys.executable, str(ROOT / "scripts/summarize.py"), d],
                                 env=dict(os.environ, SUMMARY_GROUPING="0"), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Reproduced on 0 of 1 devices", out.stdout)
        self.assertTrue(out.stdout.endswith("Nothing else.\n"))


if __name__ == "__main__":
    unittest.main()
