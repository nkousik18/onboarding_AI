# LIGHTHOUSE — Next Work Handoff

> Written: 2026-05-06  
> Branch: `decision-intelligence`  
> Author: Kousik / LIGHTHOUSE team  
> Resume from: any machine with the repo cloned and venv activated

---

## Where Things Stand

### What is built and working

| Component | Status | Location |
|---|---|---|
| PostgreSQL on Render (cloud) | Live | `dpg-d7tm1p7avr4c73dhp22g-a.oregon-postgres.render.com` |
| All data ingested into DB | Done | `sync_docs/` → `database/scripts/ingest_*.py` |
| Meeting summarizer | Working | `database/scripts/summarize_meetings.py` |
| Decision extractor | Working | `database/scripts/extract_decisions.py` |
| Change 1: Semantic dedup (MiniLM embeddings) | Done | `extract_decisions.py` → `DecisionDeduplicator` |
| Change 2: Drift detection (`drift_risk`, `last_reinforced_at`) | Done | `check_drift.py`, `models.py` |
| Change 3: Groq LLM backend | Done | Both extraction scripts |
| Chatbot (v3.0.0) | Done | `chatbot/` |
| Technical changelog | Done | `docs/DECISION_INTELLIGENCE_CHANGES.md` |

### Current DB state (as of last run)

```
Decisions in DB : 44
Active          : 43
Superseded      : 1
Supersession chain: "Use Material UI for components" → "Switch to Tailwind CSS"
Meetings summarized: 5 / 5
```

### Groq rate limit note

The free Groq tier is **100k tokens/day**. A full `extract_decisions --all` run uses ~95k tokens.  
The last 9 Jira tickets were not processed (429 rate limit). This is fine — the important data (meetings + Confluence) is fully extracted. Re-run tomorrow or skip `--jira` flag.

---

## Next Work: Two Changes Remaining

---

### Change 4: LLM Conflict Detection

**What it does:**  
Scan all active decisions and use the LLM to flag pairs that contradict each other. Store the conflicts in a new `DecisionConflict` table. Expose them via the chatbot ("are there any conflicting decisions?") and as a `check_conflicts.py` script.

**Why it matters for the judges:**  
No existing onboarding tool detects architectural contradictions automatically. This is a genuine differentiator — the system doesn't just store decisions, it reasons about their consistency.

**What to build:**

1. New DB table `decision_conflicts`:
   ```sql
   CREATE TABLE decision_conflicts (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       decision_a_id UUID REFERENCES decisions(id),
       decision_b_id UUID REFERENCES decisions(id),
       conflict_type VARCHAR(50),   -- 'direct', 'indirect', 'potential'
       explanation TEXT,
       severity VARCHAR(10),        -- 'low', 'medium', 'high'
       detected_at TIMESTAMPTZ DEFAULT now(),
       UNIQUE(decision_a_id, decision_b_id)
   );
   ```

2. Django model `DecisionConflict` in `knowledge_base/models.py` (use `managed=False`).

3. New script `database/scripts/check_conflicts.py`:
   - Load all active decisions in batches of ~10
   - For each pair, ask the LLM: _"Do these two architectural decisions contradict each other? Decision A: [title + rationale]. Decision B: [title + rationale]. Reply JSON: {conflicts: bool, type: str, explanation: str, severity: str}"_
   - Only call LLM when cosine similarity > 0.30 (related topic area — reuse the MiniLM model already loaded)
   - Save conflicts to DB, skip if already exists (idempotent)
   - Add `--report` flag for dry-run output

4. Add `conflict_intent` to the chatbot (`chatbot/intent/`) so users can ask "what decisions are in conflict?" or "does using SQLAlchemy conflict with anything?"

**Files to create/modify:**
- `database/scripts/check_conflicts.py` (new)
- `database/scripts/migrate_add_conflicts_table.sql` (new)
- `database/knowledge_base/models.py` (add `DecisionConflict`)
- `chatbot/intent/conflict_intent.py` (new, optional)
- `docs/DECISION_INTELLIGENCE_CHANGES.md` (add Change 4 entry)

**Groq token budget:** ~2k tokens per conflict check. With 44 decisions there are ~946 pairs; the cosine pre-filter should reduce actual LLM calls to ~50–100.

---

### Change 5: Provenance Chain via EntityReference Traversal

**What it does:**  
For any decision, trace back the full chain of evidence: which meeting introduced it, which Jira ticket it was linked to, which commits followed it. Return a structured provenance graph that the chatbot can narrate.

**Why it matters for the judges:**  
This is the "show your work" feature. Most RAG systems return a text chunk. LIGHTHOUSE returns a structured chain: _meeting → decision → ticket → commits_. That's institutional memory with receipts.

**What to build:**

The `EntityReference` table already exists and is populated with links between meetings, tickets, commits, and Confluence pages. The work is building a traversal function that follows those links.

1. New utility `database/scripts/provenance.py` (or add to `extract_decisions.py`):
   ```python
   def get_provenance_chain(decision_id: UUID) -> dict:
       """
       Returns:
       {
         "decision": {...},
         "source": {meeting | confluence | jira},
         "referenced_tickets": [...],
         "commits_after": [...],    # commits after decision_date that mention decision tags
         "confluence_mentions": [...],
       }
       """
   ```

2. Query logic:
   - Start from `Decision.source_type` + `Decision.source_id` → fetch the originating record
   - Look up `EntityReference` where `source_id = decision.source_id` to find tickets linked to the source
   - For each ticket ID, find `EntityReference` where `reference_type = 'commit'` and `reference_id` matches
   - For each commit, fetch `GitCommit` records
   - Also scan `GitCommit.message` for decision tags (same logic as `check_drift.py`)

3. Add `provenance_intent` to the chatbot so users can ask:  
   _"Where did the decision to use ECS Fargate come from?"_  
   _"Show me the history behind the Tailwind CSS switch."_

4. Add `--provenance <decision_id>` flag to `check_drift.py` for CLI access.

**Files to create/modify:**
- `database/scripts/provenance.py` (new)
- `chatbot/intent/provenance_intent.py` (new)
- `chatbot/retriever/sql_retriever.py` (add provenance query method)
- `docs/DECISION_INTELLIGENCE_CHANGES.md` (add Change 5 entry)

**Key model relationships already in place:**
```
EntityReference.source_id   → Meeting.id / ConfluencePage.id / JiraTicket.id
EntityReference.reference_id → JiraTicket.ticket_key / GitCommit.commit_hash
Decision.source_id          → Meeting.id / ConfluencePage.id / JiraTicket.id
Decision.related_tickets     → [ticket_key, ...]
```

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

### 3. Verify DB connection
```bash
cd database
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from knowledge_base.models import Decision
print('Decisions in DB:', Decision.objects.count())
"
```
Expected output: `Decisions in DB: 44`

### 4. If Groq rate limit hits (100k/day)
Wait until midnight UTC, or re-run with source flags to limit scope:
```bash
python3.12 scripts/extract_decisions.py --meetings     # meetings only
python3.12 scripts/extract_decisions.py --confluence   # confluence only
```

### 5. Run drift check (optional, takes ~3 seconds)
```bash
cd database
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 scripts/check_drift.py --report
```

---

## Key Files Reference

| File | Purpose |
|---|---|
| `database/.env` | All credentials (Render DB, Groq API key, Jira, Confluence) |
| `database/config/settings.py` | Django settings, DB connection (SSL required for Render) |
| `database/knowledge_base/models.py` | All ORM models — Decision, Meeting, EntityReference, etc. |
| `database/scripts/extract_decisions.py` | Main decision extraction pipeline (LLM + dedup + supersession) |
| `database/scripts/summarize_meetings.py` | Meeting summarizer |
| `database/scripts/check_drift.py` | Drift risk scoring |
| `chatbot/main.py` | Chatbot entry point |
| `docs/DECISION_INTELLIGENCE_CHANGES.md` | Technical changelog for the decision intelligence work |
| `LIGHTHOUSE_Pitch_Guide.docx` | Pitch deck guide (home directory) |

---

## Important Constraints

- **Render DB is free tier** — suspends after 90 days of inactivity. If the DB is unreachable, create a new Render PostgreSQL instance and re-run the full ingest pipeline (`scripts/ingest_all.py`).
- **Groq free tier** — 100k tokens/day, resets at midnight UTC. The full extraction pipeline uses ~95k in one pass.
- **sentence-transformers** — MiniLM model (~80MB) downloads on first use and caches locally. Needs internet on first run.
- **`managed = False` on all Django models** — tables are created by raw SQL migration files, not `python manage.py migrate`. Any new table needs a corresponding `.sql` file in `database/scripts/`.

---

## Scoring Reminder

The hackathon panel judges on: Innovation, Technical Depth, Feasibility, Impact, Presentation.

| Dimension | Current score | What pushes it higher |
|---|---|---|
| Innovation | 8/10 | Conflict detection (Change 4) — no tool does this |
| Technical depth | 8/10 | Provenance traversal (Change 5) — graph reasoning over structured data |
| Feasibility | 9/10 | Live DB, working chatbot, all data populated |
| Impact | 8/10 | Drift detection already compelling; conflict detection closes it |
| Presentation | TBD | Use the on-stage phrases in `DECISION_INTELLIGENCE_CHANGES.md` |
