# Decision Intelligence — Technical Changelog

> Tracks architectural upgrades to the Decision Timeline engine.
> Branch: `decision-intelligence`

---

## Change 1: Semantic Deduplication via Dense Embeddings

### What changed

`DecisionDeduplicator.calculate_similarity()` in `database/scripts/extract_decisions.py`

---

### Before — Lexical String Matching

```python
from difflib import SequenceMatcher

def calculate_similarity(self, title1, title2):
    t1 = self.normalize_title(title1)
    t2 = self.normalize_title(title2)
    return SequenceMatcher(None, t1, t2).ratio()
```

**How it worked:** Computes the longest common subsequence ratio between two strings as character sequences. A score of 0.70 means 70% of characters overlap when aligned optimally.

**Failure mode:** Two decisions can be semantically identical but lexically distant.

| Title A | Title B | SequenceMatcher | Verdict |
|---|---|---|---|
| `JWT authentication` | `Token-based auth with JWT` | ~0.42 | missed duplicate |
| `React for frontend` | `Use React as UI framework` | ~0.48 | missed duplicate |
| `PostgreSQL for database` | `Use Postgres as primary DB` | ~0.38 | missed duplicate |

The algorithm has no model of meaning — it sees bytes, not concepts.

---

### After — Semantic Similarity on Dense Vector Embeddings

```python
from sentence_transformers import SentenceTransformer
import numpy as np

EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

def calculate_similarity(self, title1, title2):
    t1 = self.normalize_title(title1)
    t2 = self.normalize_title(title2)
    emb1 = self._get_embedding(t1)   # 384-dim vector
    emb2 = self._get_embedding(t2)   # 384-dim vector
    return float(np.dot(emb1, emb2)) # cosine similarity (vectors are L2-normalized)
```

**How it works:** Each decision title is encoded into a 384-dimensional dense vector by a transformer model trained on 1B+ sentence pairs. Vectors are L2-normalized at encode time, so the dot product equals cosine similarity — measuring the angle between meaning vectors in embedding space, not character overlap.

| Title A | Title B | Cosine Similarity | Verdict |
|---|---|---|---|
| `JWT authentication` | `Token-based auth with JWT` | 0.848 | caught duplicate ✓ |
| `React for frontend` | `Django for backend` | 0.354 | correctly distinct ✓ |
| `PostgreSQL database` | `Switch from Material UI to Tailwind` | -0.063 | correctly unrelated ✓ |

---

### Model: `all-MiniLM-L6-v2`

| Property | Value |
|---|---|
| Architecture | MiniLM-L6 (distilled from BERT) |
| Embedding dimensions | 384 |
| Max sequence length | 256 tokens |
| Training data | 1B+ sentence pairs (SNLI, MS-MARCO, etc.) |
| Size on disk | ~80MB |
| Inference (CPU) | ~5ms per title |
| API cost | $0 — runs locally |

The model is downloaded once on first use and cached. All inference happens locally — no external API calls, no latency, no cost.

---

### Engineering decisions in the implementation

**Prefix normalization before embedding**

Action prefixes (`use`, `adopt`, `implement`, `switch to`) are stripped before encoding. This ensures "use React for frontend" and "adopt React as UI framework" both encode to vectors near "react for frontend / react as ui framework" — the decision content, not the framing verb.

**Embedding cache**

Each unique normalized title is embedded once and stored in `_embedding_cache` (a dict). Subsequent similarity checks against the same title hit the cache. For 15 decisions with ~3 source passes, this reduces encode calls from ~45 to ~15.

**Lazy model loading**

The transformer model is not loaded at import or `__init__`. It loads on the first `calculate_similarity` call. This avoids an 80MB load penalty when running scripts that don't exercise the deduplicator.

**Graceful fallback**

```python
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
```

If `sentence-transformers` is not installed, every similarity call falls back to `SequenceMatcher`. The pipeline never hard-crashes on a missing dependency.

**Supersession threshold is lower than deduplication threshold**

| Operation | Threshold | Reason |
|---|---|---|
| Duplicate detection | 0.70 | High confidence — same decision, different source |
| Supersession detection | 0.60 | Looser — "Material UI" and "Tailwind CSS" are different words but one replaces the other |

---

### How to phrase this on stage

**One-liner (15 seconds):**
> "We represent every decision as a 384-dimensional meaning vector using a transformer model trained on a billion sentence pairs. Deduplication is cosine similarity in that vector space — not string matching. The system catches decisions that say the same thing in completely different words."

**If a technical judge asks how you handle near-duplicates across sources:**
> "Each title is normalized to strip action framing — 'use', 'adopt', 'implement' — so the encoding captures the subject of the decision, not how it was phrased. We then compute cosine similarity on L2-normalized embeddings, which measures the angle between meaning vectors rather than character overlap. Two titles within 0.70 cosine distance get linked as duplicates; below 0.60 they're treated as distinct decisions."

**If asked why not use the LLM for deduplication:**
> "We considered it. The issue is latency and cost — every new decision would require an LLM call against all existing decisions, which is O(n) API calls per insertion. The embedding approach is O(1) per insertion with a local model at near-zero marginal cost. For a system that needs to run nightly or on webhook triggers, that matters."

**If asked about the model choice:**
> "all-MiniLM-L6-v2 is a distilled transformer — six layers, 384 dimensions. It's a deliberate trade-off: a larger model like MPNet gives marginally better semantic precision, but MiniLM runs in under 5ms per title on CPU with an 80MB footprint. For short decision titles, the quality ceiling on a larger model doesn't justify the inference cost."

---

---

## Change 2: Decision Drift Detection

### What changed

- `database/knowledge_base/models.py` — two new fields on `Decision`
- `database/scripts/migrate_add_drift_fields.sql` — column migration for live DB
- `database/scripts/check_drift.py` — new standalone script

---

### The problem it solves

A decision recorded in a meeting six months ago does not automatically stay valid. The team may have quietly changed direction — new commits reference a different library, tickets use different terminology — but the decision record still shows `status: active`. There is no signal that the decision has silently aged out of the codebase.

---

### New fields on `Decision`

```python
last_reinforced_at = models.DateTimeField(blank=True, null=True)
drift_risk = models.CharField(
    max_length=10,
    choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
    blank=True, null=True
)
```

**`last_reinforced_at`** — the most recent date any of the decision's `tags` (or title keywords, as fallback) appeared in a commit message or Jira ticket summary. Updated by `check_drift.py`.

**`drift_risk`** — computed from days elapsed since `last_reinforced_at`:

| Days since last reinforcement | `drift_risk` |
|---|---|
| < 30 days | `low` |
| 30 – 90 days | `medium` |
| > 90 days | `high` |
| never seen in commits/tickets | `high` |

---

### How `check_drift.py` works

```
For each active decision:
  1. Collect search terms
       → decision.tags if present
       → else: meaningful words from decision.title (len > 3, not stop words)

  2. Scan for the most recent reinforcement
       → GitCommit.objects.filter(message__icontains=term).order_by('-commit_date')
       → JiraTicket.objects.filter(summary__icontains=term).order_by('-updated_date')
       → Take the latest date across all terms and both tables

  3. Compute drift_risk from days elapsed

  4. Write last_reinforced_at + drift_risk back to the Decision record
```

Output example:

```
══════════════════════════════════════════════════════════════════════
DRIFT CHECK   (computing and saving, 15 active decisions)
══════════════════════════════════════════════════════════════════════

  ── TECHNOLOGY ──
  [LOW   ]  Use React for frontend                    last seen: 2026-01-28  (8d ago)
  [LOW   ]  Use JWT for authentication                last seen: 2026-01-25  (11d ago)
  [HIGH  ]  Use Material UI component library         last seen: never

  ── ARCHITECTURE ──
  [MEDIUM]  PostgreSQL as primary database            last seen: 2025-11-20  (71d ago)
  [HIGH  ]  ECS Fargate for deployment                last seen: never

──────────────────────────────────────────────────────────────────────
  Low risk    : 6
  Medium risk : 4
  High risk   : 5
```

---

### SQL migration

```sql
ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS last_reinforced_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS drift_risk         VARCHAR(10);

CREATE INDEX IF NOT EXISTS idx_decisions_drift_risk
    ON decisions (drift_risk)
    WHERE drift_risk IS NOT NULL;
```

Run once against the live DB:
```bash
psql $DATABASE_URL -f scripts/migrate_add_drift_fields.sql
```

---

### How to phrase this on stage

**One-liner (15 seconds):**
> "Every decision has a freshness signal. We scan incoming commits and tickets for the decision's keywords. If nothing in the codebase has referenced that decision's technology in 90 days, we flag it as high-drift — the architecture may have moved on without the decision record catching up."

**If a technical judge asks how reinforcement is determined:**
> "We use the decision's tag array as the search vocabulary. For each tag, we query commit messages and ticket summaries for the most recent occurrence. The latest match across all tags becomes the reinforcement timestamp. If no tags are set, we fall back to extracting content words from the decision title — terms longer than three characters that aren't stop words."

**If asked about false positives (a tag like 'database' appearing in unrelated commits):**
> "That's a real trade-off. Broad tags like 'database' will get reinforced by almost any data-related commit, which biases toward low-risk. The counter is specificity in tagging — 'postgresql' or 'jwt' are much cleaner signals than 'auth' or 'database'. In a production version we'd score reinforcement by term specificity, essentially an IDF weighting. For the demo, the tags in our synthetic data are specific enough that this isn't a visible issue."

**The non-technical hook:**
> "Imagine you hired a senior engineer two years ago. They made twenty architectural decisions. Then they left. Every one of those decisions is in LIGHTHOUSE — and LIGHTHOUSE tells you which ones the team is still actively building on, and which ones the codebase has quietly walked away from. That's institutional memory with a health check."

---

## Upcoming Changes (this branch)

| # | Change | Status |
|---|---|---|
| 3 | LLM conflict detection across active decisions | planned |
| 4 | Provenance chain via `EntityReference` traversal | planned |
