"""Check knowledge-base articles against the AI-ready article standard (ARTICLE-TEMPLATE.md).

usage: python tools/kb_lint.py kb/after [kb/before ...] [--today YYYY-MM-DD] [--max-age-days 180]

Each rule is one property that makes an article safe for AI retrieval. Exit code 1 if any article
breaks a rule, so the check can run in CI or before a sync to the vector index.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbmd import COMMENT_RE, parse_front_matter, sections, words  # noqa: E402

REQUIRED = ["id", "title", "product", "category", "symptoms", "last_reviewed", "owner"]
CATEGORIES = {"connectivity", "playback", "hardware", "content", "account"}
NON_SYMPTOM_TITLE = re.compile(r"\b(notes?|faq|misc|updated|general|info|v\d+(\.\d+)*|\d{4})\b", re.I)
BACK_REFERENCE = re.compile(r"\b(see above|see below|as mentioned|as above|re:)", re.I)
ERROR_CODE = re.compile(r"\b[Ee]-?\d{3}\b")
MAX_WORDS = 250


def lint_text(text: str, today: dt.date, max_age_days: int) -> list[tuple[str, str]]:
    """Return (rule, message) for every rule the article breaks."""
    text = COMMENT_RE.sub("", text).lstrip()
    fields, rest = parse_front_matter(text)
    secs = sections(rest)
    problems: list[tuple[str, str]] = []

    missing = [f for f in REQUIRED if not fields.get(f)]
    if missing:
        problems.append(("fields", "missing front-matter fields: " + ", ".join(missing)))
    if fields.get("category") and fields["category"] not in CATEGORIES:
        problems.append(("category", f"unknown category '{fields['category']}'"))

    title = fields.get("title") or (re.search(r"^# +(.+)$", rest, re.M) or [None, ""])[1]
    if NON_SYMPTOM_TITLE.search(title or ""):
        problems.append(("title", f"title is not symptom-led: '{title}'"))

    steps = [l for l in secs.get("Steps", "").splitlines() if re.match(r"^\s*\d+\.\s+\S", l)]
    if len(steps) < 2:
        problems.append(("steps", "needs a '## Steps' section with at least 2 numbered steps"))
    if not [l for l in secs.get("Escalate if", "").splitlines() if l.strip()]:
        problems.append(("escalation", "needs a '## Escalate if' section with a concrete condition"))

    if not secs.get("Summary"):
        problems.append(("summary", "needs a '## Summary' that makes sense on its own"))
    body_no_related = "\n".join(t for h, t in secs.items() if h != "Related") or rest
    if BACK_REFERENCE.search(body_no_related):
        problems.append(("self-contained", "refers to other text ('see above', 're:'); name the article instead"))

    codes = {c.upper().replace("-", "") for c in ERROR_CODE.findall(body_no_related)}
    codes |= {c.upper().replace("-", "") for c in fields.get("error_codes", []) if c}
    if len(codes) > 1 or words(body_no_related) > MAX_WORDS:
        problems.append(("one-issue", "looks like it covers several issues (several error codes or over "
                         f"{MAX_WORDS} words); split it"))

    reviewed = fields.get("last_reviewed")
    if reviewed:
        try:
            age = (today - dt.date.fromisoformat(reviewed)).days
            if age > max_age_days:
                problems.append(("stale", f"last reviewed {age} days ago (limit {max_age_days})"))
        except ValueError:
            problems.append(("stale", f"last_reviewed '{reviewed}' is not a YYYY-MM-DD date"))
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", type=Path, help="article files or folders of .md files")
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--max-age-days", type=int, default=180)
    args = ap.parse_args(argv)

    files = [f for p in args.paths for f in (sorted(p.glob("*.md")) if p.is_dir() else [p])]
    failing = 0
    by_rule: dict[str, int] = {}
    for f in files:
        problems = lint_text(f.read_text(encoding="utf-8"), args.today, args.max_age_days)
        if problems:
            failing += 1
            print(f"FAIL {f.as_posix()}")
            for rule, msg in problems:
                by_rule[rule] = by_rule.get(rule, 0) + 1
                print(f"     [{rule}] {msg}")
        else:
            print(f"ok   {f.as_posix()}")
    print(f"\n{len(files) - failing}/{len(files)} articles pass")
    for rule, n in sorted(by_rule.items(), key=lambda kv: -kv[1]):
        print(f"  {rule}: {n}")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
