# Onboarding AI — Backend Architecture

**Version:** 1.0  
**Last Updated:** May 2026  
**Stack:** Python 3.11 · Django 5.2 · PostgreSQL (Render) · Groq LLaMA · Django REST Framework

---

## Table of Contents

1. [What We Are Building](#1-what-we-are-building)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Technology Stack — Choices and Rationale](#3-technology-stack--choices-and-rationale)
4. [Repository Structure](#4-repository-structure)
5. [Database Layer](#5-database-layer)
6. [Data Ingestion Pipeline](#6-data-ingestion-pipeline)
7. [REST API Layer](#7-rest-api-layer)
8. [AI Chatbot Pipeline](#8-ai-chatbot-pipeline)
9. [Decision Intelligence System](#9-decision-intelligence-system)
10. [People Registry](#10-people-registry)
11. [API Reference](#11-api-reference)
12. [Request Lifecycle — End to End](#12-request-lifecycle--end-to-end)
13. [Scalability Analysis](#13-scalability-analysis)
14. [Security Considerations](#14-security-considerations)
15. [Configuration and Environment](#15-configuration-and-environment)
16. [Known Limitations and Future Work](#16-known-limitations-and-future-work)

---

## 1. What We Are Building

**Onboarding AI** is an internal knowledge-base platform designed to answer the question every new engineer asks on their first week: *"Why does this codebase work the way it does?"*

The system ingests data from four engineering sources — GitHub commits, Jira tickets, Confluence documentation, and meeting transcripts — normalises it into a unified PostgreSQL schema, and exposes it in two ways:

1. **A REST API** that the vanilla JS frontend consumes to display project dashboards, sprints, decisions, and team members.
2. **An AI chatbot endpoint** (`POST /api/chat/`) where a new employee can ask natural-language questions and receive grounded, context-aware answers drawn exclusively from the project's own data — not generic hallucinations.

The key differentiator is that the chatbot maintains **conversation memory**, understands follow-up questions ("who made that decision?", "tell me more"), and performs **intent-driven retrieval** — routing different question types to different database query strategies before calling the LLM.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Data Sources                            │
│   GitHub API    Jira API    Confluence API    Meeting VTT       │
└──────┬───────────┬──────────────┬───────────────┬─────────────┘
       │           │              │               │
       ▼           ▼              ▼               ▼
┌────────────────────────────────────────────────────────────────┐
│                  Ingestion Layer                                │
│  database/scripts/extract_*.py  (standalone extraction)        │
│  api/ingestion.py               (API-triggered ingestion)      │
└───────────────────────────┬────────────────────────────────────┘
                            │  upsert via Django ORM
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                  PostgreSQL (Render)                           │
│                                                                │
│  git_commits   jira_tickets   confluence_pages   meetings      │
│  decisions     decision_conflicts   entity_references          │
│  employees     sprints   sprint_tickets   projects             │
└───────────────────────────┬────────────────────────────────────┘
                            │
          ┌─────────────────┴───────────────────────┐
          │                                         │
          ▼                                         ▼
┌──────────────────────┐               ┌───────────────────────────────┐
│   Django REST API    │               │     AI Chatbot Pipeline        │
│   (api/ app)         │               │     (chatbot/ module)          │
│                      │               │                               │
│  DRF ModelSerializers│               │  IntentClassifier (Groq LLM)  │
│  26 endpoints        │               │  → SQLRetriever               │
│  OpenAPI schema      │               │  → ContextBuilder             │
│  Ingestion views     │               │  → BytezLLM (Groq)            │
│  Chat proxy view     │               │  → ConversationHistory        │
└──────────┬───────────┘               └───────────────────────────────┘
           │                                         │
           └─────────────────┬───────────────────────┘
                             │  JSON over HTTP
                             ▼
              ┌──────────────────────────────┐
              │   Frontend (Vite / Vanilla JS)│
              │   localhost:3001              │
              └──────────────────────────────┘
```

### Two Django Projects

There are two separate Django setups in the same repository:

| Directory | Purpose | `manage.py` | Database |
|-----------|---------|------------|---------|
| `database/` | Legacy extraction scripts, admin panel, intelligence pipeline scripts | `database/manage.py` | Render PostgreSQL (SSL) |
| `/` (root) | REST API server, chatbot endpoint, frontend serving | `manage.py` | Same Render PostgreSQL |

Both point at the same Render-hosted PostgreSQL instance. The root Django project is what the frontend and chatbot hit at runtime. The `database/` project is used for running extraction scripts and batch intelligence jobs.

---

## 3. Technology Stack — Choices and Rationale

### Python 3.11 + Django 5.2

**What:** Django as the backend framework.  
**Why:** Django's ORM, migrations, admin panel, and strong ecosystem cut down boilerplate. Django REST Framework (DRF) adds serialisation and view generics that keep the API layer thin. Python 3.11 gives a meaningful performance improvement (~10–60% faster CPython) over 3.9/3.10.  
**Trade-off:** Django is heavier than Flask/FastAPI for pure API work. We accept that cost for the ORM, admin panel (useful for manually browsing ingested data), and the `django.contrib.postgres` extension that gives us `ArrayField` natively.

### PostgreSQL (Render hosted)

**What:** A single cloud-hosted PostgreSQL 14 instance on Render.  
**Why:** The data model has genuine relational structure — entity references join commits to tickets, sprint_tickets join sprints to tickets, decisions reference meetings and Jira issues. A relational database with foreign keys and proper indexes is the right choice here. Render provides managed backups, connection pooling, and SSL without operational overhead.  
**Why not a vector database?** We deliberately chose SQL-based retrieval over a vector/embedding store. The queries are structured and intent-typed ("who worked on auth", "what happened in sprint 2") — SQL can answer these precisely and deterministically. Vector search would add a costly embedding step, an external service dependency, and probabilistic recall for queries where exact match is better.  
**Trade-off:** No full-text search index (tsvector) yet. Current search is `icontains` which does sequential scans at scale.

### Django REST Framework + drf-spectacular

**What:** DRF for serialisation and class-based views; drf-spectacular for auto-generating OpenAPI 3.0 schema.  
**Why:** DRF's `ModelSerializer` reduces field-mapping boilerplate. `drf-spectacular` decorators (`@extend_schema`) let us annotate views inline and auto-generate Swagger documentation without maintaining a separate spec file.  
**Trade-off:** DRF serialisation is slower than hand-written SQL dumps for high-throughput reads. At our current scale (thousands of records, not millions) this is imperceptible.

### Groq API — LLaMA 3.1-8B-Instant

**What:** Two separate Groq calls per chat turn — one for intent classification (`llama-3.1-8b-instant`, max 120 tokens) and one for answer generation (`llama-3.1-8b-instant`, max 2000 tokens).  
**Why Groq:** Groq's LPU hardware gives sub-second token generation latency, which is critical for a chat interface. LLaMA-3.1-8B is sufficiently capable for structured JSON intent parsing and short-form question answering over provided context. The OpenAI-compatible API means the client code required zero changes beyond swapping the `base_url`.  
**Why not OpenAI GPT-4o:** Cost and latency. GPT-4o at 2000 tokens per response would be ~10× more expensive and 2–3× slower for our use case.  
**Trade-off:** LLaMA-8B is less capable than GPT-4o for complex multi-step reasoning. We compensate with careful prompt engineering, intent-specific instructions, and strict "only use provided context" constraints.

### Vite + Vanilla JS Frontend

**What:** No framework. Plain HTML/CSS/JS, bundled by Vite, running on `localhost:3001`.  
**Why:** The frontend was built by a separate team. Vite provides fast HMR and ES module bundling without forcing a React/Vue dependency. Vanilla JS keeps the bundle small and the interface predictable.

---

## 4. Repository Structure

```
ex-cdi/
│
├── manage.py                    ← Django CLI (root project — API server)
├── requirements.txt             ← All Python dependencies
├── .env                         ← Symlink → database/.env (DB credentials, API keys)
│
├── config/                      ← Root Django project settings
│   ├── settings.py              ← INSTALLED_APPS, DB config, CORS, DRF, drf-spectacular
│   ├── urls.py                  ← Mounts /api/ → api.urls, /admin/ → admin
│   └── wsgi.py
│
├── knowledge_base/              ← Django app — ORM models only (no views)
│   └── models.py                ← 13 models, all managed=False (map to existing tables)
│
├── api/                         ← Django REST Framework API layer
│   ├── views.py                 ← 26 view classes (list, detail, ingest, chat, delete)
│   ├── serializers.py           ← 14+ ModelSerializer classes
│   ├── urls.py                  ← All 26 URL patterns
│   └── ingestion.py             ← Pull from GitHub / Jira / Confluence / VTT
│
├── chatbot/                     ← AI chatbot module (imported by api/views.py)
│   ├── main.py                  ← OnboardingChatbot orchestrator + ConversationHistory
│   ├── django_setup.py          ← Bootstraps Django for chatbot module imports
│   ├── intent/
│   │   ├── classifier.py        ← LLM-first intent classifier (v4) + keyword fallback
│   │   └── types.py             ← IntentType enum, INTENT_CONFIGS, TECH_TERMS
│   ├── retriever/
│   │   ├── sql_retriever.py     ← Intent-routed SQL queries → Document objects
│   │   ├── people.py            ← PeopleRegistry — DB-backed person lookup singleton
│   │   └── base.py              ← BaseRetriever + Document dataclass
│   ├── context/
│   │   ├── builder.py           ← Formats Documents into structured LLM context
│   │   └── templates.py         ← Per-intent prompt templates
│   └── llm/
│       └── bytez_llm.py         ← Groq wrapper (named BytezLLM for historical compat.)
│
├── database/                    ← Legacy extraction + intelligence pipeline
│   ├── manage.py                ← Django CLI for database/ project
│   ├── knowledge_base/models.py ← Full model definitions (source of truth for schema)
│   └── scripts/
│       ├── extract_github.py    ← Fetch commits from GitHub API
│       ├── extract_jira.py      ← Fetch tickets from Jira API
│       ├── extract_confluence.py← Fetch pages from Confluence API
│       ├── extract_decisions.py ← LLM-powered decision extraction from all sources
│       ├── summarize_meetings.py← LLM meeting summarisation → key_decisions, action_items
│       ├── check_drift.py       ← Flag decisions not reinforced recently
│       ├── check_confluence_drift.py ← Flag stale documentation pages
│       ├── check_conflicts.py   ← Detect contradictions between active decisions
│       └── provenance.py        ← Trace a decision's full origin chain
│
├── frontend/                    ← Vanilla JS frontend (Vite 6)
│   ├── workspace.html           ← Main app shell
│   ├── project_dashboard.html   ← Sprint/ticket dashboard
│   ├── vite.config.js           ← Proxies /api/* → localhost:8000
│   └── static/js/               ← Feature scripts
│
└── docs/                        ← Project documentation
```

---

## 5. Database Layer

### Schema Philosophy

All tables are defined with `managed = False` in Django. This means Django's migration system does **not** create or alter these tables — they were created via raw SQL (`database/sql/001_create_schema.sql`) and subsequent `ALTER TABLE` statements run directly in PostgreSQL. Django's ORM is used purely as a query layer.

This approach was chosen because the database schema was established before the Django project existed, and it avoids Django migrations clobbering a shared production database.

### Models and Tables

#### Core Data Models

**`git_commits` (`GitCommit`)**  
Stores every commit fetched from the GitHub repository. Keyed on the 40-character SHA. `related_tickets` is a plain text field with comma-separated Jira keys extracted from the commit message. Files changed per commit are stored in the separate `git_commit_files` table with a FK relationship.

```
id UUID PK | sha VARCHAR(40) UNIQUE | author_name | author_email
commit_date | message TEXT | related_tickets TEXT | created_at | updated_at
```

**`jira_tickets` (`JiraTicket`)**  
Flat representation of a Jira issue. ADF (Atlassian Document Format) rich-text descriptions are stripped to plain text at ingestion time. `sprint` and `story_points` are extracted from Jira custom fields (`customfield_10020`, `customfield_10016`). `is_completed` is a computed property based on whether `resolved_date` is non-null.

**`confluence_pages` (`ConfluencePage`)**  
Stores page content converted from Confluence HTML/XML storage format to Markdown. Labels are a PostgreSQL `TEXT[]` array. Three drift-tracking columns were added later: `drift_risk` (low/medium/high), `last_activity_date`, and `confluence_topics TEXT[]`.

**`meetings` (`Meeting`)**  
Stores raw WebVTT transcript content alongside LLM-generated `summary`, `key_decisions`, and `action_items` fields. Speaker names are extracted from VTT lines using the pattern `SpeakerName:` and stored as a JSON array in `participants`.

**`decisions` (`Decision`)**  
The most important model. Stores architectural and technical decisions extracted from all four sources. Key fields:

- `source_type` / `source_id` / `source_title` — tracks which meeting, ticket, page, or commit this decision came from
- `rationale` / `alternatives_considered` / `impact` — the "why" of a decision, not just the what
- `decided_by TEXT[]` — array of names involved in the decision
- `superseded_by` / `supersedes` — self-referential FKs to track when a decision is replaced
- `status` — active | superseded | reversed | proposed | duplicate
- `confidence_score` — float set by the extraction LLM (0.0–1.0)
- `drift_risk` / `last_reinforced_at` — set by `check_drift.py` when a decision hasn't been mentioned in recent activity

**`decision_conflicts` (`DecisionConflict`)**  
Records pairs of active decisions that contradict each other. Populated by `check_conflicts.py`. Columns: `decision_a_id`, `decision_b_id`, `conflict_type` (direct/indirect/potential), `severity` (low/medium/high), `explanation TEXT`.

#### Cross-Linking Models

**`entity_references` (`EntityReference`)**  
The backbone of cross-source linking. Every time a Jira ticket key appears in a commit message, Confluence page, or meeting transcript, a row is inserted here. Structure: `source_type` + `source_id` + `reference_type` + `reference_id`. The `TicketContextView` API uses this to return a ticket with all its linked commits, pages, and meetings.

**`employees` (`Employee`)**  
Team member records. Populated by ingestion scripts and/or via the `POST /api/register/` endpoint. Used by `PeopleRegistry` to resolve names and map roles to contributors without hardcoding.

**`sprints` + `sprint_tickets`**  
Sprint definitions (number, dates, goal, status) linked many-to-many to Jira tickets.

**`projects` + `project_entities`**  
Groups the entire body of work. Currently one project record exists. `project_entities` links the project to individual entity IDs.

### Schema Diagram (simplified)

```
projects ──────────── project_entities ──────────── (entity_id)
    │
    └──── sprints ──── sprint_tickets ──── jira_tickets
                                                │
git_commits ──────────────────────────── entity_references
confluence_pages ─────────────────────── (cross-references)
meetings ─────────────────────────────── │
                                          │
decisions ──────── decision_conflicts ───┘
    │ (self-ref)
    └── superseded_by / supersedes
```

---

## 6. Data Ingestion Pipeline

There are two ingestion paths:

### 6.1 Batch Scripts (Offline)

Located in `database/scripts/`. Run manually or on a schedule. Connect directly to the database using the `database/manage.py` Django setup.

| Script | Source | What it does |
|--------|--------|-------------|
| `extract_github.py` | GitHub API | Fetches commits + file diffs, creates `entity_references` for ticket mentions in commit messages |
| `extract_jira.py` | Jira REST API v3 | Fetches issues using JQL, strips ADF descriptions to plain text, links epics via `entity_references` |
| `extract_confluence.py` | Confluence API v2 | Fetches pages by space ID, converts HTML/XML → Markdown, extracts ticket references from content |
| `extract_decisions.py` | All DB sources | LLM-powered extraction: reads meetings, Confluence pages, Jira tickets and produces `Decision` rows |
| `summarize_meetings.py` | `meetings` table | For each meeting, calls LLM to populate `summary`, `key_decisions`, `action_items` |
| `check_drift.py` | `decisions` table | Computes `drift_risk` per decision based on recency of last mention across all data sources |
| `check_confluence_drift.py` | `confluence_pages` + `git_commits` | Compares page `page_updated_date` to the date of the last commit touching related files |
| `check_conflicts.py` | `decisions` table | Pairwise LLM comparison of active decisions to detect contradictions → writes `decision_conflicts` |
| `provenance.py` | All tables | For a given decision, traces origin → linked tickets → implementing commits |

All scripts use `update_or_create` so they are safe to re-run — no duplicates are created.

### 6.2 API-Triggered Ingestion (Online)

Located in `api/ingestion.py`. Called by `POST /api/ingest/github/`, `/jira/`, `/confluence/`, `/meetings/`. Uses the same upsert logic but runs synchronously in the HTTP request cycle.

The HTML-to-Markdown converter for Confluence (`_html_to_markdown`) handles:
- Confluence `<ac:structured-macro>` code blocks → fenced Markdown code blocks
- `<h1>–<h3>` → `#` headings
- `<strong>` / `<em>` → bold/italic
- `<li>` → `- ` list items
- Strips all remaining tags, HTML-unescapes entities, collapses whitespace

---

## 7. REST API Layer

### Architecture Pattern

The API uses DRF's class-based views. All list endpoints extend `generics.ListAPIView` with a `queryset` and `serializer_class`. Detail endpoints extend `generics.RetrieveAPIView`. Custom logic (search, chat, ingest, ticket context) uses `views.APIView` with manual serialisation.

All views are annotated with `@extend_schema` / `@extend_schema_view` from `drf-spectacular`, which auto-generates the OpenAPI spec at `/api/schema/` and Swagger UI at `/api/docs/`.

### Serializer Design

Two serialiser patterns are used:

1. **List vs Detail split** — `ConfluencePageListSerializer` omits the `content` field (can be thousands of characters) on list views. `ConfluencePageSerializer` includes it on detail. Same pattern for `MeetingListSerializer` vs `MeetingDetailSerializer` (omits `raw_vtt_content` on list).

2. **Nested serialisers** — `GitCommitSerializer` nests `GitCommitFileSerializer` so file changes always come with a commit. `ProjectSerializer` nests `ProjectEntitySerializer`.

### Session Management for Chat

Chat sessions are stored in a module-level dictionary `_chat_sessions: dict` keyed by `conversation_id`:

```python
_chat_sessions: dict = {}   # conversation_id → OnboardingChatbot instance
```

Each `OnboardingChatbot` instance holds its own `ConversationHistory`. The `conversation_id` is a UUID returned on the first request; the client sends it back on subsequent turns to continue the conversation. New sessions are created lazily on first use. There is no eviction — sessions accumulate in memory until the process restarts.

**Scalability implication:** This in-memory session store means chat sessions are **not** shared between processes. If the Django process is restarted or a load balancer routes the client to a different worker, history is lost. For current single-process development use, this is acceptable. See section 13 for the production path.

---

## 8. AI Chatbot Pipeline

Every call to `POST /api/chat/` runs through a 6-step pipeline inside `OnboardingChatbot.chat()`:

```
User Query
    │
    ▼
Step 0: Reference Resolution
    resolve_references(query) → enriched query + inferred entities
    (e.g., "who wrote it?" → "who wrote it? (regarding: React decision)")
    │
    ▼
Step 1: Intent Classification   [Groq LLaMA-3.1-8B, max 120 tokens]
    IntentClassifier.classify(resolved_query, prev_context)
    → ClassifiedIntent { intent_type, confidence, entities }
    │
    ▼
Step 2: SQL Retrieval
    SQLRetriever.retrieve(query, intent_type, entities, limit=5)
    → List[Document]
    │
    ▼
Step 3: Context Building
    ContextBuilder.build_context(documents, intent_type)
    + ConversationHistory.get_context_summary()
    + last assistant response (if follow-up)
    → full_context: str (max 8000 chars)
    │
    ▼
Step 4: Answer Generation   [Groq LLaMA-3.1-8B, max 2000 tokens]
    BytezLLM.generate(conversational_prompt)
    → answer: str
    │
    ▼
Steps 5–6: Entity Extraction + History Update
    Extract names/ticket IDs from the answer for follow-up tracking
    Add user message + assistant response to ConversationHistory
    │
    ▼
ChatResponse { answer, intent, confidence, sources, conversation_turn }
```

### Step 0: Reference Resolution

Before classification, the query is scanned for pronouns and reference patterns (`it`, `that`, `this`, `who made`, `tell me more`, etc.). If a reference is found and the conversation has a `current_topic`, the topic is appended to the query: `"who wrote it?" → "who wrote it? (regarding: Marcus Thompson)"`. This allows the classifier to correctly classify follow-up questions that would otherwise be ambiguous.

### Step 1: Intent Classification (v4 LLM-First)

The classifier sends a single Groq call with a structured prompt listing all 12 intent types with descriptions, the team member roster, and the previous turn context. The model returns JSON:

```json
{
  "intent": "person_query",
  "person": "Marcus Thompson",
  "topic": "react",
  "sprint": null,
  "ticket_id": null,
  "confidence": 0.92
}
```

The classifier then converts this to a `ClassifiedIntent` object, normalising the `person` field through `PeopleRegistry` (so "marcus" → "Marcus Thompson"), and assembling the `entities` list in priority order: ticket ID → sprint number → person → topic.

**Fallback:** If the Groq API is unavailable or returns malformed JSON, a keyword-scoring fallback (`_keyword_classify`) activates. It checks hard patterns first (ticket regex, sprint regex, conflict keywords) then scores keyword matches across intent categories.

### Step 2: SQL Retrieval

`SQLRetriever` routes to 12 specialised retrieval methods based on `intent_type`. Each method issues optimised SQL queries and returns `Document` objects.

Key retrieval strategies:

| Intent | Primary Query Strategy |
|--------|----------------------|
| `decision_query` | `Decision.objects.filter(status='active')` with topic/keyword filters; includes superseded decisions if query mentions "superseded" |
| `person_query` | Queries `GitCommit` (by author_name), `JiraTicket` (by assignee), `Decision` (by decided_by array) for the resolved person name |
| `sprint_summary_query` | Fetches the Sprint record + all `SprintTicket` links + meetings within sprint date range |
| `ticket_query` | Exact `issue_key` match on `JiraTicket` + `EntityReference` lookup for linked commits |
| `conflict_query` | `DecisionConflict.objects.select_related('decision_a', 'decision_b')` |
| `provenance_query` | Finds matching Decision by title similarity + traverses `entity_references` for linked commits and tickets |
| `doc_drift_query` | Queries `ConfluencePage` filtered by `drift_risk IN ('high', 'medium')`, ordered by risk |
| `howto_query` | Full-text search on `ConfluencePage.content` |
| `list_query` | Intercepted before routing — returns all records of the requested entity type (min 15) |

### Step 3: Context Building

`ContextBuilder` formats each `Document` into a structured text block tailored to its type:

- **Decision:** Title, date, status (with `⚠️ SUPERSEDED` warning if applicable), decided-by, related tickets, rationale
- **Meeting:** Title, date, participants, transcript content
- **Ticket:** Issue key, status, priority, assignee, sprint, description
- **Confluence:** Title, author, content (truncated at 2000 chars)
- **Commit:** SHA, author, date, related tickets

Documents are sorted by `relevance_score` (set by the retriever) and assembled until the 8000-character limit is reached. The full context passed to the LLM also includes:

1. `CURRENT TOPIC:` hint (the conversation's current entity focus)
2. `PREVIOUS CONVERSATION:` (last 6 messages, truncated to 1500 chars)
3. `MY LAST RESPONSE:` (injected only when the query is a follow-up — ≤8 words, or same intent as previous turn, or contains "more/explain/elaborate")
4. `RELEVANT INFORMATION:` (the formatted documents)

### Step 4: Answer Generation

The `BytezLLM` wrapper calls Groq with the assembled prompt. The system prompt is embedded in the user message (not in a separate `system` role call) so all context and instructions travel in one payload. Temperature is set to `0.7` for natural language generation.

The prompt includes critical constraints:
- Answer **only** from the provided context
- Never invent commit SHAs, ticket IDs, dates, or names
- If something was mentioned in the previous response and the user asks about it, reference it

### Conversation Memory

`ConversationHistory` maintains a rolling window of 10 turns (20 messages: 10 user + 10 assistant). It tracks:

- `current_topic` — the main entity discussed (updated whenever new entities appear)
- `topic_stack` — last 5 topics for backtracking
- `last_response_entities` — people and ticket IDs extracted from the last assistant response, enabling follow-ups like "what else did he work on?"

---

## 9. Decision Intelligence System

This is the system's most sophisticated feature — a pipeline that treats architectural decisions as first-class citizens with full lifecycle tracking.

### Extraction

`database/scripts/extract_decisions.py` reads all meetings, Confluence pages, Jira tickets, and commits, then calls the LLM to identify decisions and populate the `decisions` table. For each source, it extracts:

- The decision title and description
- The rationale and alternatives considered
- Who was involved
- Category (architecture / technology / process / design / infrastructure / security)
- Confidence score (how certain the LLM is this is a real decision, not a passing mention)

### Drift Detection

`check_drift.py` periodically scans all active decisions and checks how recently each one was mentioned across commits, Jira tickets, Confluence pages, and meetings. If a decision hasn't been reinforced in a configurable number of days, its `drift_risk` is set to `high`. This powers the `doc_drift_query` intent in the chatbot.

`check_confluence_drift.py` does the same for documentation pages: it compares the page's `page_updated_date` against the date of the most recent commit that touches files related to that page's topics, computing a staleness gap in days.

### Conflict Detection

`check_conflicts.py` performs a pairwise comparison of all active decisions. For each pair, it calls the LLM with both decision descriptions and asks it to classify the relationship as:

- **Direct conflict** — mutually exclusive choices (e.g., "use Material UI" vs. "use Tailwind CSS")
- **Indirect conflict** — tension that could cause problems (e.g., two different database access patterns)
- **Potential conflict** — flagged for human review; LLM uncertain

Results are written to `decision_conflicts` with a severity rating. The chatbot's `conflict_query` intent surfaces these.

### Provenance Tracing

`provenance.py` builds a decision's full history chain:

1. The decision record itself (source_type, source_id links back to the original meeting/ticket/page)
2. Jira tickets created after the decision that reference the same topic
3. Git commits that followed and implemented the decision
4. Known conflicts with other decisions

This powers the `provenance_query` intent: "trace the JWT decision" → "Where did the JWT decision come from, what Jira work followed, and which commits implemented it?"

### Supersession Tracking

When a decision is superseded (e.g., "use Material UI" → "use Tailwind CSS"), the `superseded_by` FK is set. The retriever's `_retrieve_decisions` method follows this chain and marks older decisions with `is_superseded = True` in the Document metadata. The context builder then prepends `⚠️ NOTE: This decision has been SUPERSEDED by a newer decision` to keep the LLM from presenting stale information as current.

---

## 10. People Registry

`chatbot/retriever/people.py` defines `PeopleRegistry` — a module-level singleton (`registry = PeopleRegistry()`) loaded once at import time from the `employees` table.

It replaces what was previously a hardcoded dict of names and roles. The registry provides:

- **`normalize_name(text)`** — resolves partial names to canonical: "marcus" → "Marcus Thompson"
- **`find_employees(text)`** — returns all employees matching a text against name, role, department, or GitHub username
- **`get_topic_contributors(topic)`** — queries commits, tickets, and decisions to rank contributors by evidence count (commits weighted 3×, tickets 2×, decisions 1×)
- **`find_by_role_keywords(text)`** — maps colloquial terms ("frontend", "aws", "ci/cd") to searchable role/department keywords through `TERM_ALIASES`, then queries the Employee table

This means the chatbot can answer "who should I contact for React questions?" without any hardcoded name-to-role mapping — it looks up employees with "frontend" or "ui" in their role, then finds which of them has the most commit/ticket/decision evidence for React.

---

## 11. API Reference

All endpoints are prefixed with `/api/`. Base URL in development: `http://localhost:8000`.

### Data Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/commits/` | All commits ordered by date (nested files included) |
| `GET` | `/api/commits/<sha>/` | Single commit by full SHA |
| `GET` | `/api/tickets/` | All Jira tickets |
| `GET` | `/api/tickets/<issue_key>/` | Single ticket (e.g. `ONBOARD-14`) |
| `GET` | `/api/tickets/<issue_key>/context/` | Ticket + linked commits, pages, meetings via entity_references |
| `GET` | `/api/pages/` | All Confluence pages (no content body on list) |
| `GET` | `/api/pages/<uuid>/` | Single page with full Markdown content |
| `GET` | `/api/meetings/` | All meetings with full transcript; filterable by `?date=YYYY-MM-DD` |
| `GET` | `/api/meetings/<uuid>/` | Single meeting detail |
| `GET` | `/api/projects/` | All projects with linked entities |
| `GET` | `/api/projects/<uuid>/` | Single project |
| `POST` | `/api/projects/<uuid>/add-member/` | Append a name to the project team_members list |
| `GET` | `/api/employees/` | All employees |
| `GET` | `/api/employees/<uuid>/` | Single employee |
| `POST` | `/api/register/` | Create or update an employee record |
| `GET` | `/api/sprints/` | All sprints with linked tickets |
| `GET` | `/api/sprints/<number>/` | Single sprint by sprint number |
| `GET` | `/api/sprints/<number>/tickets/` | Sprint tickets with completion status + summary counts |
| `GET` | `/api/sprints/<number>/meetings/` | Meetings that occurred during a sprint |
| `GET` | `/api/decisions/` | Full decision timeline; filterable by `?category=` and `?source_type=` |
| `GET` | `/api/decisions/<uuid>/` | Single decision |
| `GET` | `/api/search/?q=<query>` | Full-text search across commits, tickets, pages, meetings |

### Action Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/` | Send a natural-language query to the AI chatbot |
| `POST` | `/api/ingest/github/` | Trigger GitHub commit ingestion |
| `POST` | `/api/ingest/jira/` | Trigger Jira ticket ingestion |
| `POST` | `/api/ingest/confluence/` | Trigger Confluence page ingestion |
| `POST` | `/api/ingest/meetings/` | Upload a `.vtt` file to ingest a meeting transcript |
| `DELETE` | `/api/delete/<entity_type>/<id>/` | Delete any entity by type and ID |

### Chat Request/Response

**Request:**
```json
{
  "query": "Why did we choose React?",
  "conversation_id": "2d3c9397-c7a5-4f83-8427-b899f731ecc2"  // optional
}
```

**Response:**
```json
{
  "answer": "We chose React because it is component-based...",
  "intent": "decision_query",
  "confidence": 0.95,
  "sources": ["decision:Use React for frontend", "decision:Use React with Tailwind CSS"],
  "conversation_id": "2d3c9397-c7a5-4f83-8427-b899f731ecc2",
  "turn": 1
}
```

---

## 12. Request Lifecycle — End to End

Here is the complete path of a chat request from browser to database and back:

```
1. Browser (localhost:3001)
   POST /api/chat/ { "query": "Who worked on authentication?" }
   Proxied by Vite to localhost:8000
   │
2. Django Middleware Stack
   SecurityMiddleware → CorsMiddleware → CsrfViewMiddleware → ...
   │
3. api/urls.py
   Matches "chat/" → ChatView.as_view()
   │
4. ChatView.post() [api/views.py:735]
   Extracts query + conversation_id
   Looks up or creates OnboardingChatbot in _chat_sessions dict
   Calls bot.chat(query)
   │
5. OnboardingChatbot.chat() [chatbot/main.py:274]
   │
   ├─ 5.0 Reference Resolution
   │   history.resolve_references("Who worked on authentication?")
   │   → No pronouns found, query unchanged
   │
   ├─ 5.1 Intent Classification [chatbot/intent/classifier.py]
   │   Groq API call (llama-3.1-8b-instant, max 120 tokens)
   │   Returns: { "intent": "person_query", "topic": "authentication", ... }
   │   ClassifiedIntent { PERSON_QUERY, 0.88, ["authentication"] }
   │
   ├─ 5.2 SQL Retrieval [chatbot/retriever/sql_retriever.py]
   │   _retrieve_person_info(query, ["authentication"], limit=5)
   │   PeopleRegistry.get_topic_contributors("authentication")
   │     → GitCommit.filter(message__icontains="authentication") → scores
   │     → JiraTicket.filter(description__icontains="authentication") → scores
   │     → Decision.filter(title__icontains="authentication") → scores
   │   Returns top contributors as Document objects
   │   + JiraTicket records about authentication
   │   → [Document(commit), Document(ticket), Document(decision), ...]
   │
   ├─ 5.3 Context Building [chatbot/context/builder.py]
   │   Formats each Document into structured text block
   │   Appends conversation history (empty on turn 1)
   │   full_context: ~3200 chars
   │
   ├─ 5.4 Answer Generation [chatbot/llm/bytez_llm.py]
   │   Groq API call (llama-3.1-8b-instant, max 2000 tokens)
   │   Sends conversational prompt with context + query
   │   Returns: "Sarah Chen and Marcus Thompson worked on authentication..."
   │
   └─ 5.5-5.6 History Update
       Extract entities from response ("Sarah Chen", "Marcus Thompson", "ONBOARD-14")
       history.add_user_message(...) + history.add_assistant_message(...)
   │
6. ChatView.post() returns Response
   {
     "answer": "Sarah Chen and Marcus Thompson worked on authentication...",
     "intent": "person_query",
     "confidence": 0.88,
     "sources": ["commit:Add JWT middleware", "ticket:ONBOARD-14 Authentication"],
     "conversation_id": "abc-123",
     "turn": 1
   }
   │
7. Browser receives JSON, renders answer in chat UI
   Stores conversation_id for next turn
```

---

## 13. Scalability Analysis

### Current Architecture — What Works at Scale

| Component | Current Approach | Scales to |
|-----------|-----------------|-----------|
| PostgreSQL on Render | Managed cloud instance | ~10M rows per table with proper indexing |
| DRF serialisation | In-process Python | ~200 concurrent requests on a single Gunicorn worker |
| `icontains` search | Sequential scan | ~50K rows before latency degrades |
| Groq API | External calls, ~200ms P50 | Rate limited; see below |

### Current Bottlenecks

**1. In-memory chat sessions**  
`_chat_sessions` is a process-level dict. Each session holds a live `OnboardingChatbot` object (~5MB for full conversation history). With 1000 concurrent users, this is ~5GB of memory. More importantly, sessions are lost on process restart and cannot be shared across workers.

*Production fix:* Serialise `ConversationHistory` to Redis. Each turn, load the history at request start and persist it at request end. `OnboardingChatbot` instances are then stateless and can be created fresh per request from cached history.

**2. Full-text search — no index**  
`icontains` does `LIKE '%query%'` which forces PostgreSQL to sequential-scan every row. At current scale (30 commits, 21 tickets, 7 pages) this is imperceptible. At 10K+ rows, this will degrade.

*Production fix:* Add PostgreSQL `tsvector` GIN indexes on `message`, `description`, `content`, and `summary`. Switch `icontains` to `search=` (PostgreSQL full-text search). DRF + Django ORM support this natively.

**3. Synchronous Groq calls**  
Each chat turn makes two sequential Groq API calls (intent + answer). Each call is ~150–400ms. At high concurrency, these HTTP calls block Django worker threads.

*Production fix:* Django runs synchronously by default. For high throughput: switch to `ASGI` mode with `uvicorn` + `channels`, use `httpx` async client for Groq calls, and mark the ChatView as `async def post(...)`. This lets a single process handle many concurrent chat requests without blocking.

**4. Ingestion is synchronous and blocking**  
`POST /api/ingest/github/` fetches potentially hundreds of commits via synchronous `requests` calls inside a Django view. This can time out on slow connections or large repos.

*Production fix:* Move ingestion to a Celery task queue (Redis broker). The API returns a `task_id` immediately; the client polls a `/api/ingest/status/<task_id>/` endpoint.

### Horizontal Scaling Path

The current single-process setup can be scaled horizontally with these changes:

```
Current:
  Render Web Service (single Gunicorn process)
  └── in-memory _chat_sessions

Target:
  Load Balancer
  ├── Gunicorn worker 1 (stateless)
  ├── Gunicorn worker 2 (stateless)
  └── Gunicorn worker N (stateless)
         │
         ├── Redis (chat session store + Celery broker)
         └── PostgreSQL (unchanged — already external)
```

Adding Redis and making the chat view session-aware is the single highest-leverage scaling change.

### Data Volume Projections

| Table | Current | 1-year estimate | Risk |
|-------|---------|----------------|------|
| `git_commits` | 30 | ~5,000 | Low — indexed on SHA |
| `jira_tickets` | 21 | ~500 | Low |
| `confluence_pages` | 7 | ~200 | Low |
| `meetings` | 5 | ~200 | Low — VTT content is large TEXT |
| `decisions` | 44 | ~2,000 | Low |
| `decision_conflicts` | <10 | ~500 | Low |
| `entity_references` | ~200 | ~50,000 | Medium — scan on reference_id |

The `entity_references` table is the highest-risk for search performance. An index on `(reference_type, reference_id)` should be added before reaching 10K rows.

---

## 14. Security Considerations

### Current State (Development)

- `DEBUG=True` is read from `.env`. This must be `False` in production.
- `ALLOWED_HOSTS = ['*']` when `DEBUG=True`. This must be locked down.
- `CORS_ALLOWED_ORIGINS` is correctly restricted to `localhost:3000/3001` — not wildcard.
- No authentication on any API endpoint. All endpoints are publicly accessible.
- The `.env` file contains API tokens and the database password. It is gitignored correctly. A `.env` symlink at project root was created to share credentials between the two Django setups.

### API Keys Handled

| Key | Where used | How stored |
|-----|-----------|-----------|
| `SECRET_KEY` | Django session signing | `.env` file (gitignored) |
| `DB_PASSWORD` | PostgreSQL connection | `.env` file |
| `GROQ_API_KEY` | Groq LLM calls | `.env` file, loaded via `load_dotenv()` |
| `GITHUB_TOKEN` | GitHub API ingestion | `.env` file |
| `JIRA_API_TOKEN` | Jira API ingestion | `.env` file |
| `CONFLUENCE_API_TOKEN` | Confluence API ingestion | `.env` file |

### Production Hardening Checklist

- [ ] Set `DEBUG=False`
- [ ] Set `ALLOWED_HOSTS` to the Render domain
- [ ] Add Django token-based auth (`djangorestframework-simplejwt`) to protect all `/api/` routes
- [ ] Enable `SECURE_SSL_REDIRECT=True` (Render handles TLS termination)
- [ ] Set `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- [ ] Add `whitenoise` for static file serving
- [ ] Rotate all API keys before public deployment
- [ ] Add rate limiting to `POST /api/chat/` (e.g., `django-ratelimit`)

---

## 15. Configuration and Environment

All configuration is loaded from a single `.env` file via `python-dotenv`'s `load_dotenv()`. The root `.env` is a symlink to `database/.env` so both Django projects share the same credentials.

### Required Variables

```bash
# Django
SECRET_KEY=django-insecure-...   # Required in all environments
DEBUG=True                         # Set False in production

# PostgreSQL (Render)
DB_NAME=project_knowledge_xxxx
DB_USER=onboarding_user
DB_PASSWORD=<secret>
DB_HOST=dpg-xxxxx.oregon-postgres.render.com
DB_PORT=5432

# AI
GROQ_API_KEY=gsk_xxxx             # Used by both intent classifier and answer generator

# Ingestion (optional — only needed if running ingest endpoints)
GITHUB_TOKEN=ghp_xxxx
GITHUB_OWNER=nkousik18
GITHUB_REPO=LoanQA-MLOps
GITHUB_MAX_COMMITS=100

JIRA_DOMAIN=onboardingaii.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=<atlassian-token>
JIRA_PROJECT_KEY=ONBOARD
JIRA_MAX_ISSUES=500

CONFLUENCE_DOMAIN=onboardingaii.atlassian.net
CONFLUENCE_EMAIL=your@email.com
CONFLUENCE_API_TOKEN=<atlassian-token>
CONFLUENCE_SPACE_KEY=ONBOARD
CONFLUENCE_SPACE_ID=1474564
```

### Starting All Services

```bash
# 1. Django REST API (port 8000)
cd /path/to/project
source venv/bin/activate
python manage.py runserver 8000

# 2. Vite Frontend (port 3001 — 3000 if free)
cd frontend
npm run dev

# 3. Streamlit Chatbot UI (port 8501) — optional developer tool
cd ..
streamlit run test_ui.py --server.port 8501
```

---

## 16. Known Limitations and Future Work

### Current Limitations

1. **No authentication.** All API endpoints are open. The `POST /api/register/` endpoint creates employee records with no email verification.

2. **Synchronous Groq calls block workers.** Two sequential HTTP calls to Groq per chat turn. Under load, Django workers will queue up.

3. **In-memory chat sessions.** Lost on server restart; not shareable across processes.

4. **No full-text index.** `icontains` search degrades at scale.

5. **`decision_conflicts` populated by a batch script.** Conflicts are not detected in real time. A newly added decision won't appear in conflict results until `check_conflicts.py` runs.

6. **Confluence ingestion is idempotent by title+space.** If a page is renamed on Confluence, the old record remains and a new one is created rather than updating in place.

7. **Meeting summarisation is offline only.** `summarize_meetings.py` populates `summary`, `key_decisions`, and `action_items` on the Meeting model. Meetings ingested via `POST /api/ingest/meetings/` are stored raw and not automatically summarised.

### Near-Term Work

- **Authentication:** Add JWT via `djangorestframework-simplejwt`. Protect all write endpoints. Add user-to-employee linking so the frontend knows who is logged in.
- **Async chat view:** Switch `ChatView.post` to async, use `httpx.AsyncClient` for Groq, move session storage to Redis.
- **Celery for ingestion:** Background job queue for long-running ingest operations.
- **Automatic meeting summarisation:** Trigger `summarize_meetings.py` logic inline when a VTT is uploaded.
- **Full-text search index:** Add GIN tsvector indexes to `git_commits.message`, `jira_tickets.description`, `confluence_pages.content`.
- **Deployment to Render:** `Procfile` with Gunicorn, `whitenoise` for statics, `DEBUG=False`.
