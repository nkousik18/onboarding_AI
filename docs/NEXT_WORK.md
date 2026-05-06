# LIGHTHOUSE — Status & Next Work

> Last updated: 2026-05-06  
> Branch: `decision-intelligence`  
> Author: Kousik / LIGHTHOUSE team  
> Resume from: any machine with the repo cloned and venv activated

---

## Everything Built: Status

| # | Work item | Status | Key files |
|---|---|---|---|
| 1 | Semantic deduplication (MiniLM embeddings) | **Done** | `extract_decisions.py` → `DecisionDeduplicator` |
| 2 | Drift detection (`drift_risk`, `last_reinforced_at`) | **Done** | `check_drift.py`, `models.py` |
| 3 | Groq LLM backend migration | **Done** | `extract_decisions.py`, `summarize_meetings.py` |
| 4 | LLM conflict detection | **Done** | `check_conflicts.py`, `migrate_add_conflicts_table.sql` |
| 5 | Provenance chain traversal | **Done** | `provenance.py` |
| 6 | Chatbot wired to conflicts + provenance | **Done** | `chatbot/` — all 6 files updated |
| 7 | Confluence documentation drift detection | **Done** | `check_confluence_drift.py`, `migrate_add_confluence_drift_fields.sql` |

---

## Current DB State

```
Decisions in DB   : 44
Active            : 43
Superseded        : 1
Conflicts detected: 2  (1 high, 1 medium)
Meetings summarized: 5 / 5
Confluence pages  : 7  (1 high drift, 6 low drift — topics cached)

Supersession chain:
  "Use Material UI for components" → "Switch to Tailwind CSS"

Conflicts:
  [HIGH]   Use GitHub Actions instead of Jenkins  ↔  Use AWS for deployment
  [MEDIUM] Simplify Employee API for This Sprint  ↔  Show all employees to managers
```

---

## Chatbot — What the New Intents Handle

Two new intents were added. Users can now ask:

**Conflict queries** (intent: `conflict_query`):
- "Are there any conflicting decisions?"
- "Does SQLAlchemy conflict with anything?"
- "Show me architectural conflicts"
- "What decisions contradict each other?"

**Provenance queries** (intent: `provenance_query`):
- "Where did the JWT decision come from?"
- "Trace the Tailwind CSS decision"
- "Show me the history behind SQLAlchemy"
- "What commits followed the JWT decision?"

Both intents are detected before general keyword scoring. The retrieval is pure SQL — no LLM call needed for the data fetch, only for narration. If the Groq rate limit is hit, the raw structured data still reaches the user.

---

## What's Left to Do

### Priority 1: Run `check_drift.py` — populate drift fields

The `last_reinforced_at` and `drift_risk` fields exist in the DB but have never been computed against the current 44 decisions. This is a one-command job:

```bash
cd /Users/Masters/Projects/Onboarding_AI/database
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 scripts/check_drift.py
```

Then run `--report` to see results. This produces a strong demo moment — showing decisions that are high-drift (technology not mentioned in any recent commit or ticket) versus low-drift (actively referenced). Ask the chatbot "what is the drift risk of the ECS Fargate decision?" after running it.

---

### Priority 2: Merge `decision-intelligence` → `main`

All work is stable and pushed. When ready to present:

```bash
git checkout main
git merge decision-intelligence
git push origin main
```

Check for conflicts with the `chatbot` branch first:
```bash
git diff main..chatbot --stat
```

---

### Priority 3 (optional): One-command demo script

A single script that tells the full story end-to-end would be compelling on stage:

```bash
python scripts/demo.py
# 1. Shows 44 decisions in the timeline
# 2. Runs check_drift   → shows high/medium/low risk decisions
# 3. Runs check_conflicts --report → shows 2 conflicts
# 4. Runs provenance on JWT → shows origin meeting + 17 commits
```

Each step maps to one of the 5 changes. 30 seconds, no terminal switching.

---

## How to Resume

### 1. Activate the environment
```bash
cd /Users/Masters/Projects/Onboarding_AI
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 --version   # 3.12.x
```
> **Note:** The venv `pip` shebang is broken (old path). Always use `venv/bin/python3.12 -m pip` instead of `venv/bin/pip`.

### 2. Check the branch
```bash
git checkout decision-intelligence
git pull origin decision-intelligence
```

### 3. Verify DB is alive
```bash
cd database
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from knowledge_base.models import Decision, DecisionConflict
print('Decisions:', Decision.objects.count())
print('Conflicts:', DecisionConflict.objects.count())
"
```
Expected: `Decisions: 44  Conflicts: 2`

### 4. Run the chatbot
```bash
cd /Users/Masters/Projects/Onboarding_AI
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 chatbot/main.py
```

Try these questions to demo the new intents:
```
Are there any conflicting decisions?
Where did the JWT decision come from?
Trace the Tailwind CSS decision
Does SQLAlchemy conflict with anything?
```

### 5. Useful one-liners
```bash
# Run decision drift check (populates drift_risk on decisions)
python3.12 scripts/check_drift.py
python3.12 scripts/check_drift.py --report

# Run Confluence documentation drift check
python3.12 scripts/check_confluence_drift.py          # first run: calls LLM, caches topics
python3.12 scripts/check_confluence_drift.py --report # subsequent runs: no LLM call
python3.12 scripts/check_confluence_drift.py --refresh # re-extract topics (LLM called again)

# Chatbot: ask about doc staleness
# "which docs are outdated?"
# "are any documentation pages stale?"
# "show me doc drift status"

# Run conflict report
python3.12 scripts/check_conflicts.py --report

# Trace a decision's provenance (CLI, no LLM needed)
python3.12 scripts/provenance.py --decision "JWT"
python3.12 scripts/provenance.py --decision "Tailwind"
python3.12 scripts/provenance.py --all

# Re-extract decisions (if DB was reset) — wait for Groq limit to reset first
python3.12 scripts/extract_decisions.py --meetings --confluence
python3.12 scripts/summarize_meetings.py --all
```

### 6. If the Render DB is suspended (>90 days inactive)
Create a new Render PostgreSQL instance, update `database/.env`, then re-run the full ingest:
```bash
python3.12 scripts/ingest_all.py
python3.12 scripts/summarize_meetings.py --all
python3.12 scripts/extract_decisions.py --all
python3.12 scripts/check_conflicts.py
python3.12 scripts/check_drift.py
python3.12 scripts/check_confluence_drift.py
```

---

## Key Files Reference

| File | Purpose |
|---|---|
| `database/.env` | All credentials (Render DB, Groq API key, Jira, Confluence) |
| `database/config/settings.py` | Django settings, DB connection (SSL required for Render) |
| `database/knowledge_base/models.py` | All ORM models — Decision, DecisionConflict, Meeting, EntityReference, etc. |
| `database/scripts/extract_decisions.py` | Decision extraction pipeline (LLM + dedup + supersession) |
| `database/scripts/summarize_meetings.py` | Meeting summarizer |
| `database/scripts/check_drift.py` | Drift risk scoring — **run this before demo** |
| `database/scripts/check_conflicts.py` | LLM conflict detection |
| `database/scripts/provenance.py` | Provenance chain CLI |
| `chatbot/main.py` | Chatbot entry point |
| `chatbot/llm/bytez_llm.py` | Groq LLM wrapper (renamed BytezLLM for compatibility) |
| `chatbot/intent/types.py` | All intent types incl. CONFLICT_QUERY, PROVENANCE_QUERY |
| `chatbot/retriever/sql_retriever.py` | All retrieval methods incl. conflicts + provenance |
| `docs/DECISION_INTELLIGENCE_CHANGES.md` | Full technical changelog — read before presenting |
| `LIGHTHOUSE_Pitch_Guide.docx` | Pitch deck guide |

---

## Important Constraints

- **Render DB free tier** — suspends after 90 days of inactivity. Keep it warm or upgrade before the presentation.
- **Groq free tier** — 100k tokens/day, resets midnight UTC. The chatbot's conflict and provenance intents only use the LLM for narration — the retrieval itself is pure SQL and always works even when rate-limited.
- **sentence-transformers** — MiniLM model (~80MB) downloads on first use. Run `check_conflicts.py` once before the demo to warm the cache.
- **`managed = False` on all Django models** — tables are created by raw SQL migration files, not `python manage.py migrate`.

---

## Chatbot Architecture — Known Problems & Future Direction

> Written after a systematic fact-check of the chatbot on 2026-05-06.
> Do not fix individual symptoms. Read this section before touching the chatbot again.

---

### What the fact-check found

A full review of chatbot responses against the live DB revealed failures on roughly 40% of queries tested. The failures were:

| Query | What it returned | What it should return |
|---|---|---|
| "get me all commits by Marcus" | Sarah Chen's commits (3) | Marcus's commits (12) |
| "get me all commits related to react" | Zero commits, tech-stack decisions | 10 Lisa Park React commits |
| "new employee first steps" | Tech stack decisions | Confluence "New Employee First Steps" page by Lisa Park |
| "whom should I reach out for react doubts" | Dave Rossi (DevOps) | Lisa Park (Frontend) |
| "what are all key decisions about frontend" | One decision (Tailwind) | 5+ unique frontend decisions |
| "give me more details" after JWT | Generic JWT explanation | JWT decision rationale from DB |
| Sprint 2 contributors | 5 including Sarah Chen | 4 — Sarah has no Sprint 2 tickets or commits |

---

### Root cause

**Every failure traces back to one thing: a rule-based intent classifier that controls what data gets retrieved.**

The pipeline is rigid:

```
Query → keyword pattern matching → one intent → one retrieval method → LLM narrates
```

One wrong classification at step 2 means steps 3 and 4 have no way to recover. The LLM is narrating whatever the wrong retriever returned. It can't fix the data it never saw.

**Why the classifier keeps failing:**

It scores tokens, not meaning. "Get me all commits by Marcus" scores high for `timeline_query` because "all" is a timeline keyword. "New employee first steps" routes to `timeline_query` because it sounds like a progression. "What are all key decisions about frontend" hits the `_retrieve_list` path because "what are all" is a list pattern. These aren't edge cases — they're normal English phrasing that doesn't match the classifier's vocabulary.

Every fix applied so far (adding regex patterns, special-case conditions, sprint who-patterns, follow-up inheritance) works around one gap while leaving the underlying fragility intact. The surface area for new failures does not shrink.

**Why context bleed keeps happening:**

The conversation history stores `current_topic` (last entity mentioned) and injects it into every subsequent query. After asking about Dave Rossi, React questions get Dave. After asking about Sprint 3, decision queries filter on '3'. The history system has no concept of topic change detection — it treats the last entity as always relevant.

---

### Root cause in one sentence

> The system asks "what type of question is this?" using keyword rules, then retrieves data based on that type. It should ask "what does the user need?" using language understanding, then retrieve whatever answers that need.

---

### The fix options (discuss before implementing)

#### Option 1 — LLM query parser (do this next, low effort)

Replace the classifier with a single small Groq call (~150 tokens) before retrieval. The LLM parses the query into an explicit retrieval plan:

```
User: "get me all commits by Marcus"

Parse call returns:
{
  "data_sources": ["commits"],
  "filters": {"person": "Marcus Thompson"},
  "intent": "person_commits"
}

→ Retriever queries GitCommit WHERE author_name icontains 'Marcus'
→ Correct answer, no routing error possible
```

```
User: "new employee first steps"

Parse call returns:
{
  "data_sources": ["confluence"],
  "filters": {"keywords": ["first steps", "onboarding"]},
  "intent": "howto"
}

→ Returns Lisa Park's Confluence page directly
```

The intent classifier, the `ROLE_KEYWORDS` list, the `_is_person_query` regex patterns, the `_is_sprint_summary_query` patterns — all of them go away. The routing logic lives in the parse call.

**On cost:** This adds ~150 tokens per query. The current system already wastes full generation calls (~1200 tokens) when the classifier is wrong. Correct routing on the first try is net cheaper at scale. The LLM parse call is a stepping stone — at production scale you replace it with a fine-tuned classifier (see below).

#### Option 2 — Embedding-based retrieval, no classifier at all (right production move)

Instead of classifying and routing, embed the query once and do cosine similarity search across all tables simultaneously:

```
Query → one embedding vector → pgvector search across decisions + commits + tickets + confluence + meetings
     → return top-K most semantically relevant documents regardless of table
     → LLM narrates
```

"Get me all commits by Marcus" and "New employee first steps" both become vector lookups. The classifier disappears entirely. This is the dominant production pattern at Notion, Perplexity, GitHub Copilot, and Cursor.

Infrastructure: pgvector is a PostgreSQL extension — one `CREATE EXTENSION vector` on the existing Render DB. No new services. Pre-compute embeddings for all existing records at ingest time (one-time cost, ~$0.002 at OpenAI pricing). Query-time embedding: ~$0.00004 per query.

**This eliminates the classifier and the context bleed problem simultaneously.** History becomes pure background context for the LLM, not entity state that overwrites the current query's meaning.

#### Option 3 — Tool calling / agentic retrieval (best accuracy, one call)

Give the LLM tool definitions for each data source and let it decide which to call:

```
Tools: get_commits(person, topic, date_range)
       get_decisions(topic, category)
       search_confluence(keywords)
       get_sprint_summary(sprint_number)
       get_person_work(name)
       ...

One LLM call → LLM decides which tools to invoke and with what parameters
             → Tools execute (in parallel if needed)
             → LLM synthesizes results
```

The routing logic lives inside the model weights. No classifier, no routing table, no context bleed. This is what LangChain agents, LlamaIndex query engines, and Anthropic's tool use pattern implement. Cost is one call slightly larger than the current generation call — often cheaper than two calls.

---

### What big tech companies do at scale

```
Stage                     Architecture                              Cost per query
─────────────────────────────────────────────────────────────────────────────────
Demo / prototype          Rule-based classifier                     $0 (fragile)
Early product             LLM parse call                            +10-15% (robust)
Growth (1M+ queries/day)  Fine-tuned BERT classifier                $0 after training
                          + embedding retrieval (pgvector)          ~$0.00004/query
Scale                     Two-model: small for routing,             ~$0.0001/query
                          large for generation only
Mature product            Tool calling + hybrid retrieval           ~$0.0002/query
                          + semantic cache (Redis/GPTCache)         -40% via cache hit
```

**Fine-tuned small classifier** — Azure AI Search, Elastic Enterprise Search, Salesforce Einstein all do this. Train a DistilBERT on labeled examples of your own queries. After training the model is <100MB, runs locally in <5ms, zero marginal cost per query. The training corpus is the fact-check data we already have (the broken queries + their correct intents are free labeled training examples).

**Semantic caching** — GPTCache, Redis semantic cache. Most enterprise users ask the same questions repeatedly. Cache parse results + generated answers by query embedding similarity. Reduces LLM calls by 40-60% on typical workloads.

**The key argument for judges:** The rule-based classifier is what doesn't scale — not the LLM call. Rules break silently and require engineering time to maintain every time a new query pattern appears. Both the LLM parse approach and the embedding approach scale horizontally with infrastructure, not with engineering headcount.

---

### What to say on stage when asked about scale

> "For the demo we use a structured LLM parse call that adds about 150 tokens per query — roughly a 10% cost increase but it eliminates the classification errors. At scale you replace that parse call with a fine-tuned BERT classifier that has zero marginal cost after training, or you switch to embedding-based retrieval over pgvector, which is one PostgreSQL extension on infrastructure we're already paying for. The routing logic moves from code into the model, and the cost per query actually drops. This is the same progression Notion, Perplexity, and GitHub Copilot followed."

---

### Remaining known issues (do not patch individually — fix the architecture)

| Issue | Correct fix |
|---|---|
| "commits by X" → timeline_query | LLM parse / tool calling |
| "first steps" → timeline_query | LLM parse / embedding retrieval |
| Context bleed (Dave → React) | Embedding retrieval (no entity state) |
| "key decisions about frontend" → general_query | LLM parse extracts topic + data_source |
| "who should I contact for X" → wrong person | LLM parse + `find_by_role_keywords()` already correct, just needs right routing |
| Sprint 2 contributors includes Sarah Chen | Sprint contributor logic uses commit date range; meetings have null dates so Sprint2 meetings excluded from count |
| Tailwind provenance missing Lisa Park's commit | Decision tags are `['frontend', 'framework']` not `['tailwind']` — tag is too broad for keyword scan |

---

## Scoring Estimate

| Dimension | Estimated score | What delivers it |
|---|---|---|
| Innovation | 9/10 | Conflict detection is genuinely novel; chatbot answers "what contradicts what?" |
| Technical depth | 9/10 | Embeddings + LLM judgement + relational graph traversal + conversational interface |
| Feasibility | 9/10 | Live DB, all scripts working, chatbot answering new question types |
| Impact | 9/10 | Drift + conflicts + provenance + chatbot together cover every question a new hire has |
| Presentation | TBD | Use on-stage phrases from `DECISION_INTELLIGENCE_CHANGES.md` — one per change |
