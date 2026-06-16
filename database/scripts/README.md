# Database Scripts — Reference

All scripts run from `database/` using the project venv. Django settings are auto-loaded via `DJANGO_SETTINGS_MODULE=config.settings`.

```bash
cd /Users/Masters/Projects/Onboarding_AI/database
/Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 scripts/<script>.py [flags]
```

**Groq rate limit:** 100k tokens/day, resets midnight UTC. Scripts that call Groq are marked with `[LLM]`.

---

## Scripts

### `summarize_meetings.py` `[LLM]`
Reads raw VTT transcripts from the `meetings` table and fills in `summary`, `key_decisions`, and `action_items` using Groq Llama 70B.

```bash
python3.12 scripts/summarize_meetings.py --all              # summarize all meetings without a summary
python3.12 scripts/summarize_meetings.py --force            # re-summarize all (overwrites existing)
python3.12 scripts/summarize_meetings.py --meeting-id <uuid>
python3.12 scripts/summarize_meetings.py --dry-run          # print output, don't save
python3.12 scripts/summarize_meetings.py --model llama-3.3-70b-versatile
```

**Run before:** `extract_decisions.py` (decisions use meeting summaries as input)

---

### `extract_decisions.py` `[LLM]`
Reads meetings, Confluence pages, and Jira tickets and extracts architectural decisions using Groq Llama 70B. Applies semantic deduplication (MiniLM cosine similarity, threshold 0.70) and detects supersession chains.

```bash
python3.12 scripts/extract_decisions.py --all               # meetings + confluence + jira
python3.12 scripts/extract_decisions.py --meetings
python3.12 scripts/extract_decisions.py --confluence
python3.12 scripts/extract_decisions.py --jira
python3.12 scripts/extract_decisions.py --dry-run           # preview, don't save
python3.12 scripts/extract_decisions.py --clear             # delete all decisions first, then re-extract
python3.12 scripts/extract_decisions.py --model llama-3.3-70b-versatile
python3.12 scripts/extract_decisions.py --similarity 0.70   # dedup threshold (default: 0.70)
```

**Groq cost:** ~95k tokens for a full run. The last batch of Jira tickets may hit the daily limit and be skipped; re-run the next day. Runs are idempotent — duplicates are caught by the deduplicator.

---

### `check_drift.py`
Scans every active `Decision` and checks whether its tags (or title keywords) appear in recent commits or Jira tickets. Writes `last_reinforced_at` and `drift_risk` (`low` / `medium` / `high`) back to the DB.

```bash
python3.12 scripts/check_drift.py          # compute and save
python3.12 scripts/check_drift.py --dry-run
python3.12 scripts/check_drift.py --report  # print current saved values, no compute
```

**Drift thresholds:**
- `< 30 days` since last reinforcement → `low`
- `30–90 days` → `medium`
- `> 90 days` or never seen → `high`

**Run before any demo** to populate drift fields on all 44 decisions.

---

### `check_conflicts.py` `[LLM]`
Detects contradictions between pairs of active decisions. Uses a two-stage pipeline:
1. MiniLM cosine pre-filter (threshold 0.25) to narrow 903 pairs to ~87 candidates
2. Groq Llama 70B judges each candidate pair and returns `conflict_type` + `severity`

Results are saved to the `decision_conflicts` table.

```bash
python3.12 scripts/check_conflicts.py              # detect and save new pairs
python3.12 scripts/check_conflicts.py --report     # print saved conflicts
python3.12 scripts/check_conflicts.py --dry-run    # detect but don't save
python3.12 scripts/check_conflicts.py --force      # re-check already-seen pairs
python3.12 scripts/check_conflicts.py --min-sim 0.25  # cosine pre-filter threshold
```

**Idempotent:** existing pairs are skipped unless `--force`. Run nightly to catch new decisions.

---

### `check_confluence_drift.py` `[LLM on first run]`
Detects Confluence pages whose documentation has fallen behind the active codebase. Stores `drift_risk`, `last_activity_date`, and `confluence_topics` on each `ConfluencePage`.

```bash
python3.12 scripts/check_confluence_drift.py           # extract topics (LLM) + compute drift
python3.12 scripts/check_confluence_drift.py --report  # print current status (no LLM)
python3.12 scripts/check_confluence_drift.py --dry-run
python3.12 scripts/check_confluence_drift.py --refresh # re-extract topics via LLM (overwrites cache)
```

**LLM cost:** Called once per page at initial scan to extract topics; cached in `confluence_topics`. Subsequent `--report` runs are pure SQL, no LLM calls.

**Drift thresholds:**
- `< 14 days` gap between last code activity and last doc update → `low`
- `14–30 days` → `medium`
- `> 30 days` → `high`
- No code activity found for the page's topics → `none`

---

### `provenance.py`
Traces the full chain for a decision: origin source → linked tickets → commits that followed. Pure read — no LLM, no DB writes.

```bash
python3.12 scripts/provenance.py --decision "JWT"        # partial title match
python3.12 scripts/provenance.py --id <uuid>             # exact UUID
python3.12 scripts/provenance.py --all                   # summary for all decisions
python3.12 scripts/provenance.py --decision "JWT" --json # output raw JSON (used by chatbot)
```

---

### `extract_github.py`
Pulls commits from a GitHub repository via the API and upserts into `git_commits` and `git_commit_files`.

```bash
python3.12 scripts/extract_github.py
```

Requires: `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` in `.env`

---

### `extract_jira.py`
Pulls Jira issues via the Jira REST API and upserts into `jira_tickets`.

```bash
python3.12 scripts/extract_jira.py
```

Requires: `JIRA_DOMAIN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` in `.env`

---

### `extract_confluence.py`
Pulls Confluence pages via the Confluence REST API and upserts into `confluence_pages`.

```bash
python3.12 scripts/extract_confluence.py
```

Requires: `CONFLUENCE_DOMAIN`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_ID` in `.env`

---

## Full Pipeline (Reset DB from Scratch)

```bash
cd /Users/Masters/Projects/Onboarding_AI/database

# 1. Apply schema
psql $DATABASE_URL -f sql/001_create_schema.sql
psql $DATABASE_URL -f scripts/migrate_add_drift_fields.sql
psql $DATABASE_URL -f scripts/migrate_add_conflicts_table.sql
psql $DATABASE_URL -f scripts/migrate_add_confluence_drift_fields.sql

# 2. Ingest raw data (order matters)
python3.12 manage.py ingest_data --employees ../sync_docs/employees.csv
python3.12 manage.py ingest_data --projects  ../sync_docs/projects.csv
python3.12 manage.py ingest_data --jira      ../sync_docs/jira_tickets.csv
python3.12 manage.py ingest_data --sprints   ../sync_docs/sprints.csv
python3.12 manage.py ingest_data --sprint-tickets ../sync_docs/sprint_tickets.csv
python3.12 manage.py ingest_data --commits   ../sync_docs/git_commits.json
# Meetings — one VTT file at a time:
for f in ../sync_docs/*.vtt; do python3.12 manage.py ingest_data --meetings "$f"; done
# Confluence — one Markdown file at a time:
for f in ../sync_docs/0*.md; do python3.12 manage.py ingest_data --confluence "$f"; done

# 3. AI pipeline (requires GROQ_API_KEY; respect 100k/day limit)
python3.12 scripts/summarize_meetings.py --all
python3.12 scripts/extract_decisions.py --all
python3.12 scripts/check_drift.py
python3.12 scripts/check_conflicts.py
python3.12 scripts/check_confluence_drift.py
```

## Pre-Demo Checklist

```bash
# Wake the Render DB (if it may have been idle)
python3.12 -c "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup(); from knowledge_base.models import Decision; print(Decision.objects.count())"

# Refresh drift scores
python3.12 scripts/check_drift.py

# Verify state
python3.12 scripts/check_drift.py --report
python3.12 scripts/check_conflicts.py --report
python3.12 scripts/check_confluence_drift.py --report
```
