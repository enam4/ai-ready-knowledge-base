"""Builds the README figures in assets/ from eval/results_per_question.csv and the knowledge base.
Needs matplotlib, numpy and pillow (the tools themselves stay standard-library only)."""
import csv
import re
import numpy as np
from figstyle import *

P = theme("lime")
ROWS = list(csv.DictReader(open("eval/results_per_question.csv", encoding="utf8")))
CONDS = [("before", "before", 0.3, "fg"), ("after", "after", 1.0, "acc"),
         ("after, no metadata", "after, no\nmetadata", 0.45, "acc")]
STYLES = ["plain", "vague", "typo", "code"]


def rate(cond, key, style=None):
    rr = [r for r in ROWS if r["condition"] == cond and (style is None or r["style"] == style)]
    return sum(int(r[key]) for r in rr), len(rr)


# 0. banner: a tangled paragraph on the left resolving into ordered article rows on the right
rng = np.random.default_rng(9)
field = np.full((100, 400), 0.05)
for r in range(6, 96, 5):                       # legacy prose: ragged, overlapping, uneven density
    for _ in range(4):
        c0 = int(rng.integers(0, 170)); L = int(rng.integers(20, 90))
        field[r:r + 2, c0:c0 + L] = np.maximum(field[r:r + 2, c0:c0 + L], rng.uniform(0.3, 0.8))
xx = np.linspace(0, 1, 400)[None, :]
field = np.where(rng.random(field.shape) < np.clip((xx - 0.35) / 0.25, 0, 1), 0.05, field)
for k, top in enumerate(range(8, 92, 14)):      # restructured articles: one block per problem
    c0 = 255
    field[top:top + 2, c0:c0 + 120] = 1.0                       # title
    for j in range(3):
        field[top + 4 + 3 * j:top + 5 + 3 * j, c0 + 6:c0 + 6 + int(rng.integers(55, 105))] = 0.55   # numbered steps
    field[top:top + 12, c0 - 6:c0 - 3] = 0.8                     # left rule
banner("banner.png", "ai-ready-knowledge-base",
       "restructuring a support knowledge base so ai retrieval returns the right article.",
       field, meta="> python · retrieval eval · github.com/enam4")

# 1. hero: right article first, with the chance level for each set
f, ax = fig(6.0, bottom_in=1.25)
x = np.arange(len(CONDS))
chance = {"before": 25, "after": 10, "after, no metadata": 10}
for i, (c, lab, lv, ramp) in enumerate(CONDS):
    k, n = rate(c, "hit1")
    v = 100 * k / n
    dbar(ax, x[i], v, lv, ramp, width=0.58)
    label(ax, i, v + 3, f"{v:.0f}%", color=getattr(P, ramp), ha="center", va="bottom", fontsize=17)
    label(ax, i, v + 11.5, f"{k}/{n}", color=P.dim, ha="center", va="bottom", fontsize=12, fontweight="normal")
    ax.plot([i - 0.29, i + 0.29], [chance[c]] * 2, color=P.bg if lv == 1.0 else P.fg, lw=2.5, ls=(0, (2, 2)))
ax.set_xticks(x); ax.set_xticklabels([c[1] for c in CONDS])
ax.set_ylim(0, 115); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_ylabel("% of 40 questions")
ax.grid(axis="x", visible=False)
title(ax, "right article first: 50% before, 85% after restructuring",
      "hit@1 on 40 questions · dashed line = a random pick (25% before, 10% after)")
save(f, "hit-at-1.png")

# 2. by question style
f, ax = fig(5.8, bottom_in=1.4)
x = np.arange(len(STYLES)); w = 0.26
for k, (c, lab, lv, ramp) in enumerate(CONDS):
    for i, s in enumerate(STYLES):
        h, n = rate(c, "hit1", s)
        xi = x[i] + (k - 1) * w
        dbar(ax, xi, 100 * h / n, lv, ramp, width=w * 0.88)
        label(ax, xi, 100 * h / n + 3, f"{h}/{n}", color=getattr(P, ramp), ha="center", va="bottom", fontsize=11)
ax.set_xticks(x); ax.set_xticklabels([f"{s}\n(n={rate('before', 'hit1', s)[1]})" for s in STYLES])
ax.set_ylim(0, 118); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_ylabel("hit@1 (%)")
ax.grid(axis="x", visible=False)
ax.legend(handles=[swatch(lv, ramp, lab.replace("\n", " ")) for _, lab, lv, ramp in CONDS],
          loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
title(ax, "error-code questions depend on the structured fields",
      "code questions: 5/5 with the error_codes field, 2/5 without it")
save(f, "hit-by-style.png")

# 3. before vs after, as a terminal transcript
before = open("kb/before/x1-player-notes.md", encoding="utf8").read()
before = re.sub(r"<!--.*?-->", "", before, flags=re.S)
para = next(p for p in re.split(r"\n\s*\n", before) if "E104" in p)
para = re.sub(r"\s+", " ", para).strip()
after = open("kb/after/black-screen-after-update.md", encoding="utf8").read()
steps = re.findall(r"^\d+\. (.+)$", after, flags=re.M)
esc = re.search(r"## Escalate if\s+- (.+)", after)
rows = [("[before]", (para[:230].rstrip() + " …") if len(para) > 230 else para),
        ("[after]", 'title: "Black screen after a firmware update" · product: Media Player X1 · error_codes: E-104')]
rows += [(f"  {i + 1}.", s[:150]) for i, s in enumerate(steps[:3])]
if esc:
    rows.append(("  escalate", esc.group(1)[:150]))
terminal("before-after.png", "the same fix, before and after restructuring",
         "legacy: four problems in one paragraph · restructured: one problem, numbered steps",
         rows, label_w=11, levels=[0.3, 1.0] + [0.55] * (len(rows) - 2),
         foot="verbatim from kb/before/x1-player-notes.md and kb/after/black-screen-after-update.md (fictional)")
