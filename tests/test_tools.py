"""Tests for the article loader, the linter and the eval. Run: python -m unittest discover tests"""

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import kb_eval  # noqa: E402
from kb_lint import lint_text  # noqa: E402
from kbmd import load_dir, load_legacy, parse_front_matter  # noqa: E402

TODAY = dt.date(2026, 11, 18)


class FrontMatter(unittest.TestCase):
    def test_parses_scalars_inline_lists_and_item_lists(self):
        fields, rest = parse_front_matter(
            '---\nid: 7\ntitle: "No sound"\nerror_codes: ["E-1", "E-2"]\nsymptoms:\n  - "muted"\n  - "silent"\n---\nbody')
        self.assertEqual(fields["id"], "7")
        self.assertEqual(fields["title"], "No sound")
        self.assertEqual(fields["error_codes"], ["E-1", "E-2"])
        self.assertEqual(fields["symptoms"], ["muted", "silent"])
        self.assertEqual(rest, "body")

    def test_empty_inline_list(self):
        fields, _ = parse_front_matter("---\nerror_codes: []\n---\n")
        self.assertEqual(fields["error_codes"], [])


class Loader(unittest.TestCase):
    def test_legacy_markers_are_stripped_from_indexed_text(self):
        for doc in load_dir(ROOT / "kb" / "before"):
            self.assertNotIn("issue:", doc.article.body)
            self.assertNotIn("<!--", doc.article.body)

    def test_legacy_segments_track_current_and_stale(self):
        page = load_legacy(ROOT / "kb" / "before" / "firmware-update-faq-2025.md", 9001)
        self.assertFalse(page.covers("1007"))
        self.assertTrue(page.stale_for("1007"))
        notes = load_legacy(ROOT / "kb" / "before" / "x1-player-notes.md", 9002)
        self.assertTrue(notes.covers("1007") and notes.covers("1004") and notes.covers("1002"))

    def test_related_section_is_not_indexed(self):
        for doc in load_dir(ROOT / "kb" / "after"):
            self.assertNotIn("## Related", doc.article.body)

    def test_ablation_drops_only_metadata(self):
        full = load_dir(ROOT / "kb" / "after")
        bare = load_dir(ROOT / "kb" / "after", keep_metadata=False)
        for a, b in zip(full, bare):
            self.assertEqual(a.article.body, b.article.body)
            self.assertEqual("", b.article.symptoms + b.article.error_code + b.article.product)


class Lint(unittest.TestCase):
    def test_every_restructured_article_passes(self):
        for path in sorted((ROOT / "kb" / "after").glob("*.md")):
            self.assertEqual([], lint_text(path.read_text(encoding="utf-8"), TODAY, 180), path.name)

    def test_every_legacy_page_fails_structure_rules(self):
        for path in sorted((ROOT / "kb" / "before").glob("*.md")):
            rules = {r for r, _ in lint_text(path.read_text(encoding="utf-8"), TODAY, 180)}
            self.assertTrue({"fields", "steps", "escalation"} <= rules, path.name)

    def test_back_reference_and_staleness(self):
        good = (ROOT / "kb" / "after" / "display-shows-no-signal.md").read_text(encoding="utf-8")
        broken = good.replace("1. Confirm the HDMI", "1. As mentioned, confirm the HDMI")
        rules = {r for r, _ in lint_text(broken, TODAY, 180)}
        self.assertIn("self-contained", rules)
        rules = {r for r, _ in lint_text(good, dt.date(2027, 9, 1), 180)}
        self.assertEqual({"stale"}, rules)


class Eval(unittest.TestCase):
    def test_eval_is_deterministic_and_counts_every_question(self):
        import csv
        with open(ROOT / "eval" / "questions.csv", encoding="utf-8") as fh:
            questions = list(csv.DictReader(fh))
        docs = load_dir(ROOT / "kb" / "after")
        first = kb_eval.run_condition(docs, questions)
        second = kb_eval.run_condition(docs, questions)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(questions))

    def test_chance_baseline_for_one_issue_articles(self):
        docs = load_dir(ROOT / "kb" / "after")
        row = kb_eval.score({"id": "x", "style": "plain", "issue_id": "1004", "question": ""}, docs[:1], docs)
        self.assertAlmostEqual(row["chance1"], 1 / len(docs))


if __name__ == "__main__":
    unittest.main()
