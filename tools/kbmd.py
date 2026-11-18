"""Load knowledge-base articles from markdown into the shapes the linter and the eval need.

Two formats:

* Structured articles (kb/after/): YAML-style front matter (see ARTICLE-TEMPLATE.md), then
  Summary / Before you start / Steps / Escalate if / Related sections. One issue per article.
* Legacy pages (kb/before/): a title and free prose. Hidden markers such as
  `<!-- issue:1007 -->` or `<!-- issue:1007 stale -->` say which issue each passage covers,
  so the eval can measure how much of a returned page is about the question. Markers are
  stripped before anything is indexed, so retrieval never sees them.

Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from kb import Article

MARKER_RE = re.compile(r"<!--\s*issue:(\w+)(\s+stale)?\s*-->")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def words(text: str) -> int:
    return len(WORD_RE.findall(text))


# ---------------------------------------------------------------- front matter

def parse_front_matter(text: str) -> tuple[dict, str]:
    """Return (fields, rest). Supports `key: value`, `key: ["a", "b"]` and indented `- item` lists."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fields: dict = {}
    current = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current is not None:
            fields[current].append(_unquote(item.group(1)))
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            fields[key] = []
            current = key
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fields[key] = [_unquote(v) for v in inner.split(",")] if inner else []
            current = None
        else:
            fields[key] = _unquote(value)
            current = None
    return fields, text[end + 5:]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def sections(body: str) -> dict[str, str]:
    """Map each `## Heading` to its text."""
    out: dict[str, str] = {}
    parts = re.split(r"^## +(.+)$", body, flags=re.M)
    for heading, text in zip(parts[1::2], parts[2::2]):
        out[heading.strip()] = text.strip()
    return out


# ---------------------------------------------------------------- documents

@dataclass
class Segment:
    issue: str | None   # issue id, or None for text about no particular issue
    stale: bool
    text: str


@dataclass
class Doc:
    path: Path
    article: Article                       # what gets indexed
    segments: list[Segment] = field(default_factory=list)
    fields: dict = field(default_factory=dict)
    raw: str = ""

    def issue_words(self, issue: str, stale: bool = False) -> int:
        return sum(words(s.text) for s in self.segments if s.issue == issue and s.stale == stale)

    def covers(self, issue: str) -> bool:
        return self.issue_words(issue) > 0

    def stale_for(self, issue: str) -> bool:
        return self.issue_words(issue, stale=True) > 0 and not self.covers(issue)

    @property
    def total_words(self) -> int:
        return words(self.article.title) + words(self.article.body)


def load_structured(path: Path, keep_metadata: bool = True) -> Doc:
    raw = path.read_text(encoding="utf-8")
    fields, rest = parse_front_matter(raw)
    secs = sections(rest)
    # Related lists other articles' titles; it helps people navigate but would pull
    # retrieval towards the wrong issue, so it is not indexed.
    body = "\n\n".join(f"## {h}\n\n{t}" for h, t in secs.items() if h != "Related")
    codes = fields.get("error_codes", [])
    art = Article(
        article_id=int(fields["id"]), title=fields.get("title", ""),
        product=fields.get("product", "") if keep_metadata else "",
        category=fields.get("category", "") if keep_metadata else "",
        symptoms=", ".join(fields.get("symptoms", [])) if keep_metadata else "",
        error_code=(codes[0].upper() if codes else "") if keep_metadata else "",
        body=body, updated_at=fields.get("last_reviewed", ""))
    return Doc(path, art, [Segment(str(art.article_id), False, art.title + " " + body)], fields, raw)


def load_legacy(path: Path, article_id: int) -> Doc:
    raw = path.read_text(encoding="utf-8")
    segments: list[Segment] = []
    issue, stale, pos = None, False, 0
    for m in MARKER_RE.finditer(raw):
        segments.append(Segment(issue, stale, COMMENT_RE.sub("", raw[pos:m.start()])))
        issue = None if m.group(1) == "none" else m.group(1)
        stale, pos = bool(m.group(2)), m.end()
    segments.append(Segment(issue, stale, COMMENT_RE.sub("", raw[pos:])))
    clean = COMMENT_RE.sub("", raw).strip()
    title_m = re.search(r"^# +(.+)$", clean, flags=re.M)
    title = title_m.group(1).strip() if title_m else path.stem
    body = clean[title_m.end():].strip() if title_m else clean
    # the title line sits in the first segment; it is about no single issue
    art = Article(article_id, title, "", "", "", "", body, "")
    return Doc(path, art, segments, {}, raw)


def load_dir(folder: Path, keep_metadata: bool = True) -> list[Doc]:
    """Structured articles if the files have front matter, otherwise legacy pages (ids 9001+)."""
    docs = []
    for i, path in enumerate(sorted(folder.glob("*.md"))):
        if path.read_text(encoding="utf-8").startswith("---\n"):
            docs.append(load_structured(path, keep_metadata))
        else:
            docs.append(load_legacy(path, 9001 + i))
    return docs
