# LIGHTHOUSE — Resume Source of Truth

> DAE AI Hackathon 2026 · Full-stack AI onboarding assistant
> All numbers verified against source code as of 2026-06-16.

---

## 1. Project Summary

LIGHTHOUSE is an AI-powered employee onboarding assistant built for the DAE AI Hackathon 2026. It aggregates institutional knowledge from four live sources — GitHub, Jira, Confluence, and meeting transcripts — into a unified PostgreSQL knowledge base and exposes it through a natural-language chatbot backed by Groq LLMs. A new hire can ask "Why did we choose React?" or "What is Marcus working on?" and receive a grounded answer with source citations rather than having to search across four disconnected tools. The system ships as three surfaces: a Django REST API, a Vite multi-page web app, and a Chrome side-panel extension.

---

## 2. Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend framework | Django 5.2 + Python 3.12 | Mature ORM, DRF, drf-spectacular OpenAPI generation |
| Database | PostgreSQL (Render free tier) | JSONB arrays, full-text search, SSL-required remote host |
| ORM strategy | `managed = False` on all models | Raw SQL owns schema; Django ORM handles queries only |
| LLM — response generation | Groq `llama-3.3-70b-versatile` | Fast inference, no GPU infra required |
| LLM — intent classification | Groq `llama-3.1-8b-instant` | ~120-token JSON parse; 8b is fast enough, saves cost vs. 70b |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, CPU-friendly, strong semantic similarity |
| API layer | Django REST Framework + drf-spectacular | Auto-generated OpenAPI 3 schema at `/api/docs/` |
| Frontend | Vite 6.2 + Vanilla JS | No framework overhead; 8 MPA entry points with HMR |
| Chrome extension | Manifest V3 side panel | Native browser panel; no popup size constraints |
| Auth (web app) | sessionStorage (no JWT) | Sufficient for hackathon scope; register creates Employee record |
| Dev proxy | Vite dev server port 3000 → Django 8000 | Avoids CORS in development |
| Dependency injection | `python-dotenv` | Single `.env` at project root for all secrets |

---

## 3. Data Ingestion Pipeline

Four independent ingest endpoints, each triggered via `POST /api/ingest/<source>/`. All use `update_or_create` — safe to re-run, no duplicates.

### Stage 1 — Connection & Authentication
- **GitHub**: `GITHUB_TOKEN` (personal access token, `repo` scope). Targets `GITHUB_OWNER/GITHUB_REPO`.
- **Jira**: Basic auth (`JIRA_EMAIL` + `JIRA_API_TOKEN`) against `JIRA_DOMAIN`.
- **Confluence**: Same Atlassian token as Jira; separate `CONFLUENCE_SPACE_ID`.
- **Meetings**: No external credentials — accepts a `.vtt` file upload via `multipart/form-data`.

### Stage 2 — Data Extraction
- **GitHub**: Paginated commit history; cap at `GITHUB_MAX_COMMITS` (default 100). Per-commit: SHA, message, author, date, changed files.
- **Jira**: JQL search with cursor-based `nextPageToken` pagination; cap at `JIRA_MAX_ISSUES` (default 500). Per-ticket: key, summary, description, status, priority, assignee, sprint links, comments, labels.
- **Confluence**: All pages in space; HTML content fetched per-page. Skips pages whose title starts with `'Template -'`. Converts HTML → Markdown server-side.
- **Meetings**: Parses `.vtt` WebVTT transcript; extracts speakers, cue-by-cue timestamps, duration. Uploading the same filename updates the existing record.

### Stage 3 — Normalization & Cleaning
- Commit messages stripped of noise; changed-files list serialised to `ArrayField`.
- Jira labels stored as `ArrayField`; `sprint_number` extracted via `re.search` on sprint name.
- Confluence page content stored as Markdown; word-count cached for drift heuristics.
- Meeting: speaker list deduped; `duration_seconds` computed from last cue timestamp.

### Stage 4 — Entity Reference Linking
Cross-source linkage is created at ingest time and stored in `EntityReference`:
- GitHub commits → Jira tickets: `re.findall(r'[A-Z]+-\d+', message)` on commit messages.
- Confluence pages → Jira tickets: same regex on page Markdown content.
- Meetings → Jira tickets: same regex on transcript text.
- Jira → Epics: `epic_link` field on each ticket.

### Stage 5 — Semantic Deduplication (Decisions only)
New `Decision` records are embedded with `all-MiniLM-L6-v2` (384 dimensions) before insertion. Cosine similarity computed against all existing decision embeddings:
- **Threshold 0.70** → duplicate suppressed, existing record updated instead.
- **Threshold 0.25** → potential conflict flagged; written to `DecisionConflict` with severity score.

### Stage 6 — Confluence Drift Detection
Each Confluence page receives a drift-risk score on ingest based on:
- Days since last edit vs. linked decision activity.
- Number of Jira tickets referencing the page that have closed since the last page update.
- Output: `drift_risk` ∈ {`high`, `medium`, `low`, `none`} stored on the `ConfluencePage` record.

**Ingest response shape (all sources):**
```json
{ "source": "jira", "project": "PAY", "created": 10, "updated": 45, "errors": 0, "total": 55 }
```

---

## 4. AI Chat Pipeline (6 Stages)

Triggered by `POST /api/chat/` (alias: `POST /api/query/`). Conversation state lives in the in-memory `_chat_sessions` dict keyed by `conversation_id` (UUID). Sessions survive server uptime only.

```
USER QUERY + conversation_id
    │
    ▼
Stage 1 — REFERENCE RESOLUTION  (ConversationHistory.resolve_references)
    • Pronouns/short refs ("it", "his", "that decision") expanded with current_entities
    • E.g. "his commits" → "his commits (regarding: Marcus Thompson)"
    │
    ▼
Stage 2 — INTENT CLASSIFICATION  (IntentClassifier v4)
    • Primary: single Groq call — llama-3.1-8b-instant, ~120 output tokens
    • Returns JSON: { intent, person, topic, sprint, ticket_id, confidence }
    • Fallback: keyword scorer (v3 rules) when LLM unavailable or rate-limited
    • 12 intent types resolved (see §5)
    │
    ▼
Stage 3 — SQL RETRIEVAL  (SQLRetriever)
    • Intent routed to 1 of 12 dedicated ORM methods
    • List-query intercept: "list all X" / "show all X" bypasses intent dispatch
    • Decision fallback: reads sync_docs/*.md when DB decisions sparse
    • Returns List[Document] with relevance_score
    │
    ▼
Stage 4 — CONTEXT ASSEMBLY  (ContextBuilder)
    • Documents sorted by relevance_score descending
    • Type-specific formatters: _format_decision, _format_meeting, _format_ticket, etc.
    • Cap: MAX_CONTEXT_CHARS = 8 000 chars total
    • History block: MAX_HISTORY_CHARS = 1 500 chars (last N turns)
    │
    ▼
Stage 5 — LLM GENERATION  (BytezLLM → Groq llama-3.3-70b-versatile)
    • Anti-hallucination system prompt; grounded response or "I don't know"
    • max_tokens = 2 000; temperature = 0.7
    │
    ▼
Stage 6 — HISTORY UPDATE  (ConversationHistory)
    • User message + assistant response appended
    • Entities extracted from response for follow-up tracking
    • History capped at MAX_HISTORY_TURNS = 10 (20 messages); trimmed oldest-first
```

**Response shape:**
```json
{
  "answer": "...",
  "intent": "decision_query",
  "confidence": 0.85,
  "sources": ["decision:Use React", "meeting:Sprint 1 Planning"],
  "conversation_id": "89d58088-...",
  "turn": 3
}
```

---

## 5. Decision Intelligence System (8 Changes)

All 8 changes are implemented and in production code.

| # | Change | Implementation | Key Parameter |
|---|--------|---------------|---------------|
| 1 | Semantic deduplication | `all-MiniLM-L6-v2` embeddings on Decision insert | Cosine threshold **0.70** |
| 2 | Drift detection | `drift_risk` field on ConfluencePage; scored at ingest | 4 levels: high/medium/low/none |
| 3 | Groq migration | `BytezLLM` class now wraps Groq; class name kept for call-site compat | `llama-3.3-70b-versatile` |
| 4 | Conflict detection | Cosine pre-filter against existing decisions | Pre-filter **0.25**; writes to `DecisionConflict` with severity |
| 5 | Provenance chain | `_retrieve_provenance()` assembles: origin → tickets → commits → conflicts | Queries 4 tables in one method |
| 6 | PeopleRegistry | DB-backed singleton; loaded from `Employee` table at import; no hardcoded names | Evidence scoring: commits=3, tickets=2, decisions=1 |
| 7 | Confluence drift query intent | `doc_drift_query` intent; returns pages ordered high→medium→low→none | 11th of 12 intents |
| 8 | LLM intent classifier (v4) | Groq `llama-3.1-8b-instant` replaces keyword-only v3; keyword as fallback | ~120 output tokens per classify call |

### 12 Intent Types

| Intent | Example Query | Primary Tables |
|--------|--------------|----------------|
| `decision_query` | "Why did we choose React?" | `decisions` |
| `person_query` | "What has Marcus been working on?" | `git_commits`, `jira_tickets`, `decisions` |
| `sprint_summary_query` | "Summary of Sprint 2" | `sprints`, `sprint_tickets`, `meetings`, `git_commits` |
| `status_query` | "What tickets are open?" | `jira_tickets`, `sprints` |
| `ticket_query` | "Tell me about ONBOARD-14" | `jira_tickets`, `git_commits`, `decisions` |
| `meeting_query` | "What was discussed in Sprint 1 planning?" | `meetings` |
| `howto_query` | "How do I set up the project?" | `confluence_pages` |
| `timeline_query` | "When was the auth decision made?" | `decisions`, `meetings` |
| `conflict_query` | "Are there conflicting decisions?" | `decision_conflicts`, `decisions` |
| `provenance_query` | "Trace the JWT decision" | `decisions`, `entity_references`, `git_commits`, `jira_tickets` |
| `doc_drift_query` | "Which docs are outdated?" | `confluence_pages` |
| `general_query` | Fallback | `decisions`, `confluence_pages`, `meetings` |

---

## 6. Database Architecture

10 Django models, all with `managed = False`. Schema is created by raw SQL scripts in `database/scripts/`; Django never runs `migrate` in production.

| Model | Key Fields | Notes |
|-------|-----------|-------|
| `GitCommit` | sha (PK), message, author_name, commit_date, changed_files (ArrayField) | ArrayField requires `django.contrib.postgres` |
| `JiraTicket` | issue_key (PK), summary, description, status, priority, assignee, labels (ArrayField) | issue_key e.g. `PAY-221` |
| `ConfluencePage` | id (UUID), title, content_markdown, drift_risk, word_count | drift_risk updated on each Confluence ingest |
| `Meeting` | id (UUID), title, transcript, participants (ArrayField), duration_seconds | Populated from .vtt files |
| `Project` | id (UUID), name, team_members (ArrayField), jira_project_key, github_repo | Links entities across sources |
| `Employee` | id (UUID), name, email, role, department, created_at | Source for PeopleRegistry |
| `Sprint` | sprint_number, name, start_date, end_date, goal, status | sprint_number is the lookup key |
| `Decision` | id (UUID), title, rationale, category, source_type, embedding (ArrayField) | embedding stored for cosine comparison |
| `DecisionConflict` | id (UUID), decision_a_id, decision_b_id, severity, similarity_score | Written by ingestion when cosine ≥ 0.25 |
| `EntityReference` | id (UUID), source_type, source_id, target_type, target_id | Cross-source link table |

**SSL:** Render PostgreSQL requires `sslmode=require`; set via `DB_HOST` env var pointing to the Render hostname.
**Free-tier note:** Render free PostgreSQL suspends after 90 days of inactivity.

---

## 7. REST API Layer

34 endpoints across 16 categories. All served by Django REST Framework. OpenAPI 3 schema auto-generated by `drf-spectacular` at `/api/docs/`.

| Category | Endpoints | Notes |
|----------|-----------|-------|
| Chat | `POST /api/chat/`, `POST /api/query/` | `/query/` is an alias used by the Chrome extension |
| Auth | `POST /api/register/` | Creates or updates Employee; returns 201 (new) or 200 (updated) |
| Commits | `GET /api/commits/`, `GET /api/commits/<sha>/` | `?project_id=<uuid>` filter |
| Tickets | `GET`, `GET /<key>/`, `GET /<key>/context/`, `PATCH /<key>/status/`, `POST /<key>/comments/`, `POST /create/` | 6 sub-routes |
| Pages | `GET /api/pages/`, `GET /api/pages/<uuid>/` | List = lightweight; detail = full Markdown |
| Meetings | `GET /api/meetings/`, `GET /api/meetings/<uuid>/` | `?date=` and `?project_id=` filters |
| Projects | `GET`, `GET /<uuid>/`, `POST /<uuid>/add-member/` | |
| Employees | `GET /api/employees/`, `GET /api/employees/<uuid>/` | |
| Sprints | `GET`, `GET /<num>/`, `GET /<num>/tickets/`, `GET /<num>/meetings/` | Lookup by sprint number (int) |
| Decisions | `GET /api/decisions/`, `GET /api/decisions/<uuid>/` | `?category=` and `?source_type=` filters |
| Search | `GET /api/search/?q=<query>` | Searches commits, tickets, pages, meetings |
| Activity | `GET /api/activity/` | Blended feed; `?limit=<n>` (default 20) |
| Teams | `GET /api/teams/messages/` | Placeholder — Teams integration not yet implemented |
| Ingest | `POST /api/ingest/{github,jira,confluence,meetings}/` | Synchronous; safe to re-run |
| Delete | `DELETE /api/delete/<entity_type>/<id>/` | 8 entity types; returns `{"deleted": true, ...}` |
| Test | `GET /api/test/` | Health check |

**Key implementation details:**
- `views.py`: ~1 238 lines; `ChatView` maintains `_chat_sessions` in-memory dict.
- `serializers.py`: 305 lines; `JiraTicketSerializer.get_labels()` handles nested label extraction.
- `ingestion.py`: 487 lines; 4 top-level functions called synchronously by ingest views.
- CORS: `localhost:3000` only (Vite dev server port).

---

## 8. Frontend

Vite 6.2 multi-page application (MPA). No framework — Vanilla JS + CSS custom properties. Dark sci-fi theme.

### Pages

| Page | JS Module(s) | Purpose |
|------|-------------|---------|
| `login.html` | inline only | Client-side form validation; sets sessionStorage, redirects |
| `register.html` | `auth.js` + inline | Calls `POST /api/register/`; then sets sessionStorage |
| `project_dashboard.html` | `project_dashboard.js` (~2 100 lines) + `solution_chat.js` (728 lines) | Sprints, tickets, decisions, people rail, activity feed |
| `integrations.html` | `integrations.js` + `solution_chat.js` | Jira/GitHub/Confluence data viewer + ingest triggers |
| `workspace.html` | `integrations.js` + `solution_chat.js` | Same as integrations (alternate route) |
| `employee_personal.html` | `employee_personal.js` (653 lines) | Personal task list, calendar, skills |
| `home.html` | inline only | Landing page |
| `detail.html` | inline only | Generic entity detail |

### Key Patterns

- **Auth model:** `sessionStorage.isLoggedIn` flag; each protected page checks on load and redirects to `login.html` if absent. No JWT, no tokens.
- **Data fetching:** Shared promise-singletons per resource (`fetchTicketsOnce`, `fetchDecisionsOnce`, `fetchEmployeesOnce`) prevent redundant API calls when multiple components need the same data. All data fetched in parallel via `Promise.all` on dashboard load.
- **AI chat panel (`solution_chat.js`):** Self-contained IIFE exported as `window.Solution`. Tracks `conversationId` across turns. Stores up to 20 conversation histories in `localStorage['solution_chat_history']`. Calls `POST /api/chat/`.
- **Member chips:** `buildMemberChip()` enriches each name with role, department, email (mailto link), and Microsoft Teams deep-link from the `/api/employees/` cache.

---

## 9. Chrome Extension

Manifest V3 Chrome side panel extension. Opens as a persistent side panel (not a popup window) via `chrome.sidePanel` API.

### Architecture

| File | Lines | Role |
|------|-------|------|
| `manifest.json` | 44 | MV3 config; side panel at `popup.html`; content script on `<all_urls>` |
| `popup.html` | 362 | 4-tab panel UI + persistent chat footer |
| `popup.js` | ~1 005 | All panel logic (tab switching, data fetching, modals, settings) |
| `popup.css` | — | Dark navy theme matching web app |
| `background.js` | 166 | Service worker: context menus, side panel toggle, `getBackendUrl` relay |
| `content.js` | 91 | Injects floating button (bottom-right) on every page |

### The 4 Tabs

| Tab | Data Source | Fallback |
|-----|------------|---------|
| **Overview** | `/api/activity/`, `/api/commits/`, `/api/sprints/` | Static placeholder HTML |
| **Tickets** | `/api/tickets/` + 3 write endpoints | 4 mock tickets |
| **Calendar** | `/api/meetings/` | 3 mock meetings |
| **Teams** | `/api/teams/messages/` | 3 mock messages (Teams not yet integrated) |

Persistent chat at the bottom of every tab calls `POST /api/query/`.

### API Endpoints Used (11 total)

`POST /api/query/` · `GET /api/tickets/` · `POST /api/tickets/create/` · `PATCH /api/tickets/<key>/status/` · `POST /api/tickets/<key>/comments/` · `GET /api/employees/` · `GET /api/meetings/` · `GET /api/teams/messages/` · `GET /api/activity/` · `GET /api/commits/` · `GET /api/sprints/`

### Other Features

- **Context menu:** Right-click any selected text → "Ask LightHouse about this text"; right-click page → "Ask LightHouse about this page". Side panel opens with query pre-filled.
- **Floating button:** `content.js` injects a fixed-position blue button on every page; click toggles the side panel via `chrome.runtime.sendMessage({ action: 'toggleSidePanel' })`.
- **Project selector:** Dropdown filters tickets/meetings by `?project_id=<value>`.
- **Backend URL:** Configurable in settings (default `http://localhost:8000`); stored in `chrome.storage.local`.

---

## 10. Key Engineering Decisions

| Decision | Chosen | Rejected | Reason |
|----------|--------|----------|--------|
| LLM provider | Groq (hosted inference) | OpenAI GPT-4o / self-hosted Ollama | Free tier sufficient; faster cold-start than self-hosted; no GPU needed |
| Intent classification model | llama-3.1-8b-instant (separate call) | Use same 70b model for classify + generate | 8b classify call is ~3× cheaper and faster; 70b reserved for generation quality |
| Embedding model | MiniLM-L6-v2 (384-dim) | OpenAI `text-embedding-3-small` | Runs on CPU; no API cost; 384-dim is sufficient for cosine dedup at hackathon scale |
| DB schema ownership | Raw SQL (`managed=False`) | Django `makemigrations` | Schema must be inspectable and version-controlled independently of Django; avoids migration drift |
| Session storage | In-memory `_chat_sessions` dict | Redis / DB-persisted sessions | Zero infra overhead for hackathon; acknowledged trade-off: history lost on server restart |
| Auth model (web app) | `sessionStorage` flag | JWT tokens / Django sessions | No need for refresh cycles at this scope; register call creates real Employee record |
| Frontend build | Vite MPA (8 entry points) | Single-page React app | No framework learning curve; each page is self-contained; Vite handles JS bundling |
| Chrome UI | Side panel (`chrome.sidePanel`) | Browser popup (400px wide) | Side panel has no size constraints; user keeps context on the page they're reading |
| Conflict detection trigger | Cosine pre-filter at 0.25 | LLM call per new decision | Pre-filter is O(n) dot products on 384-dim vectors — sub-millisecond; LLM call would add 1–2s per insert |
| Dedup threshold | 0.70 cosine similarity | Fixed keyword hashing | Semantic similarity handles paraphrase ("use React" vs "adopt React"); keyword hash would miss these |
| PeopleRegistry | DB-backed singleton at import | Hardcoded name→role dicts | Dict requires re-deploy per new hire; DB-backed singleton reloads from Employee table automatically |
| Cross-source linking | EntityReference join table | Foreign keys per pair | Generic `(source_type, source_id, target_type, target_id)` handles any future entity type without schema changes |

---

## 11. Known Limitations & Future Work

### Known Limitations

| Limitation | Impact | Root Cause |
|------------|--------|-----------|
| Chat history lost on server restart | Multi-turn context broken if Django restarts | `_chat_sessions` is an in-memory dict, not Redis/DB |
| Login is client-side only | Entering any email+password grants access | No credential check against DB; auth is `sessionStorage` flag only |
| Teams messages are placeholder | Teams tab shows static mock data | Microsoft Teams webhook integration not implemented |
| `employee_personal.js` calls non-existent endpoints | `/api/tasks/<id>/` and `/api/jira/tickets/<id>/complete/` return 404 | Endpoints were planned but not built; JS falls back gracefully |
| Render free PostgreSQL suspends after 90 days | DB connection errors after inactivity | Free-tier constraint; needs a keep-alive ping or paid tier |

### Future Work

- **Persistent chat sessions:** Move `_chat_sessions` to Redis or a `ChatSession` DB model; enables cross-restart history and horizontal scaling.
- **Real authentication:** Add Django `SimpleJWT` or session-backed login; gate all API endpoints; wire `login.html` to `POST /api/auth/login/`.
- **Microsoft Teams integration:** Implement the Teams webhook reader and populate `teams/messages/` with real data.
- **Streaming responses:** Switch `ChatView` to Server-Sent Events so the frontend can render tokens as they arrive rather than waiting for the full response.
- **Chrome Web Store deployment:** Add a privacy policy, prepare screenshots, and submit MV3 extension for review.
- **Semantic search endpoint:** Replace the current full-text `LIKE` search in `SearchView` with embedding-based cosine nearest-neighbour for better recall on paraphrased queries.
