# LIGHTHOUSE Chatbot — Technical Documentation

The onboarding AI chatbot that powers the `/api/chat/` endpoint. Answers natural-language questions about decisions, people, sprints, tickets, meetings, and documentation by classifying intent, retrieving records from PostgreSQL, and generating a grounded response via Groq.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Module Structure](#module-structure)
3. [Core Components](#core-components)
4. [Intent Types](#intent-types)
5. [Data Flow](#data-flow)
6. [Configuration](#configuration)
7. [Running the CLI](#running-the-cli)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

```
USER QUERY
    │
    ▼
0. CONVERSATION HISTORY
   • Resolve references ("it", "that", "who wrote it")
   • Track current topic and entities across turns
    │
    ▼
1. INTENT CLASSIFIER  (intent/classifier.py)
   • LLM-first: single Groq call (llama-3.1-8b-instant, ~120 tokens)
   • Fallback: keyword rules if LLM is unavailable
   • Output: IntentType + entities (names, ticket IDs, topics)
    │
    ▼
2. SQL RETRIEVER  (retriever/sql_retriever.py)
   • Routes to intent-specific retrieval method
   • Executes Django ORM queries against PostgreSQL
   • Returns List[Document] — universal format for all source types
    │
    ▼
3. CONTEXT BUILDER  (context/builder.py)
   • Formats documents by type (decision, meeting, ticket, page, commit)
   • Assembles conversation history + last response for follow-ups
   • Caps total context at 8 000 chars
    │
    ▼
4. LLM — RESPONSE GENERATION  (llm/bytez_llm.py)
   • Groq / llama-3.3-70b-versatile
   • Prompt includes anti-hallucination rules
   • Falls back to a canned "I don't know" response when no docs found
    │
    ▼
5. HISTORY UPDATE
   • Store user query + assistant response
   • Extract entities from response for follow-up tracking
   • Update current topic
```

---

## Module Structure

```
chatbot/
├── main.py                  # Orchestrator: OnboardingChatbot + ConversationHistory
├── django_setup.py          # Bootstraps Django so ORM works outside manage.py
├── README.md                # This file
│
├── intent/
│   ├── types.py             # IntentType enum + IntentConfig + TECH_TERMS
│   └── classifier.py        # LLM-first classifier (v4) with keyword fallback
│
├── retriever/
│   ├── base.py              # Document dataclass + BaseRetriever ABC
│   ├── sql_retriever.py     # All intent-specific ORM retrieval methods
│   └── people.py            # PeopleRegistry: DB-backed name/role lookup
│
├── context/
│   ├── builder.py           # ContextBuilder: formats docs + assembles prompt context
│   └── templates.py         # PromptTemplates: intent-specific prompt skeletons
│
└── llm/
    └── bytez_llm.py         # Groq wrapper (class kept as BytezLLM for compatibility)
```

---

## Core Components

### `main.py` — `OnboardingChatbot`

The main class that wires everything together. One instance is created per conversation session in the API layer (`api/views.py::_chat_sessions`).

**Key classes:**

| Class | Purpose |
|-------|---------|
| `Message` | Single message: role, content, entities, topic, timestamp |
| `ConversationHistory` | Multi-turn memory, reference resolution, topic tracking |
| `ChatResponse` | Structured output: answer, intent, confidence, sources, turn |
| `OnboardingChatbot` | Orchestrates all 5 pipeline steps |

**Key methods on `OnboardingChatbot`:**

```python
chat(query: str) -> ChatResponse       # Full pipeline with history
chat_simple(query: str) -> str         # Just the answer string
clear_history()                         # Reset conversation
get_current_topic() -> str             # What topic is being discussed
get_current_entities() -> List[str]    # Active entity list
health_check() -> dict                 # Component status
```

**`ConversationHistory` — reference resolution:**

Pronouns and short follow-ups are automatically expanded before classification:

```python
# Turn 1: "Why did we use React?" → entities=['react']
# Turn 2: "Who made that decision?"
#   resolve_references() → "Who made that decision? (regarding: react)"
```

History is capped at 10 turns (20 messages) and trimmed oldest-first.

---

### `intent/classifier.py` — `IntentClassifier` (v4)

**Primary path:** Calls Groq `llama-3.1-8b-instant` with a ~280-token prompt that returns structured JSON:

```json
{
  "intent": "person_query",
  "person": "Marcus Thompson",
  "topic": null,
  "sprint": null,
  "ticket_id": null,
  "confidence": 0.9
}
```

**Fallback:** Rule-based keyword scorer from v3, used when the LLM is unavailable (rate-limited, no key, network error).

The `prev_context` argument (one line like `"person_query about Marcus Thompson"`) is included so follow-ups like `"his commits"` resolve correctly without needing the full history.

---

### `retriever/sql_retriever.py` — `SQLRetriever`

Routes each intent to a dedicated method:

| Intent | Method | Primary tables |
|--------|--------|----------------|
| `decision_query` | `_retrieve_decisions()` | `decisions` |
| `person_query` | `_retrieve_person_info()` | `git_commits`, `jira_tickets`, `decisions` |
| `sprint_summary_query` | `_retrieve_sprint_summary()` | `sprints`, `sprint_tickets`, `jira_tickets`, `meetings`, `git_commits`, `decisions` |
| `status_query` | `_retrieve_status()` | `jira_tickets`, `sprints` |
| `ticket_query` | `_retrieve_ticket_info()` | `jira_tickets`, `git_commits`, `decisions` |
| `meeting_query` | `_retrieve_meetings()` | `meetings` |
| `howto_query` | `_retrieve_documentation()` | `confluence_pages` |
| `timeline_query` | `_retrieve_timeline()` | `decisions`, `meetings` |
| `conflict_query` | `_retrieve_conflicts()` | `decision_conflicts`, `decisions` |
| `provenance_query` | `_retrieve_provenance()` | `decisions`, `entity_references`, `git_commits`, `jira_tickets` |
| `doc_drift_query` | `_retrieve_doc_drift()` | `confluence_pages` |
| `general_query` | `_retrieve_general()` | `decisions`, `confluence_pages`, `meetings` |

**List query intercept:** Any query matching patterns like `"list all X"`, `"what decisions..."`, `"show all..."` is routed to `_retrieve_list()` before the intent dispatch, unless it's a superseded-decisions query.

**Decision fallback:** If no `Decision` rows match, `_retrieve_decision_fallback_from_sync_docs()` reads `sync_docs/*.md` files for overlap with query terms — useful when the DB is sparsely populated.

---

### `retriever/people.py` — `PeopleRegistry`

Singleton (`registry`) loaded once at import time from the `Employee` table. All name/role lookups derive from real DB data — nothing hardcoded.

| Method | Purpose |
|--------|---------|
| `normalize_name(text)` | `"marcus"` → `"Marcus Thompson"` |
| `find_employees(text)` | Match text against name/role/dept |
| `get_all_names()` | For classifier patterns |
| `get_topic_contributors(topic)` | Who worked on X? Ranked by evidence (commits > tickets > decisions) |
| `get_person_work(name)` | All commits, tickets, decisions for a person |
| `find_by_role_keywords(text)` | `"who does frontend?"` → Employee lookup by role |

---

### `context/builder.py` — `ContextBuilder`

`build_context(documents, intent_type)` is the method used by `main.py`. It:
1. Sorts documents by `relevance_score` descending
2. Calls a type-specific formatter (`_format_decision`, `_format_meeting`, etc.)
3. Concatenates with `---` separators, capping at `MAX_CONTEXT_CHARS = 8000`

---

### `llm/bytez_llm.py` — `BytezLLM`

Groq backend. The class name `BytezLLM` is kept for call-site compatibility (it replaced the old Bytez wrapper without renaming). Uses `llama-3.3-70b-versatile` for response generation.

Accepts either `GROQ_API_KEY` (preferred) or `BYTEZ_API_KEY` (legacy fallback) from `.env`.

---

## Intent Types

12 intent types are defined in `intent/types.py`:

| Intent | Example queries |
|--------|----------------|
| `decision_query` | "Why did we choose React?", "What was the rationale for JWT?" |
| `person_query` | "What has Marcus been working on?", "Who did the frontend?" |
| `sprint_summary_query` | "Summary of Sprint 2", "What happened in Sprint 1?" |
| `timeline_query` | "When was the auth decision made?", "Project timeline" |
| `howto_query` | "How do I set up the project?", "New employee first steps" |
| `status_query` | "What's the status of ONBOARD-15?", "What tickets are open?" |
| `ticket_query` | "Tell me about ONBOARD-14" |
| `meeting_query` | "What was discussed in Sprint 1 planning?" |
| `conflict_query` | "Are there any conflicting decisions?", "Does SQLAlchemy conflict with anything?" |
| `provenance_query` | "Where did the JWT decision come from?", "Trace the Tailwind decision" |
| `doc_drift_query` | "Which docs are outdated?", "Are any pages stale?" |
| `general_query` | Fallback for anything else |

---

## Data Flow

**Example: multi-turn conversation**

**Turn 1:** "What has Marcus been working on?"
```
1. resolve_references() → no change (first turn)
2. classify() → person_query, entities=['Marcus Thompson']
3. retrieve() → PeopleRegistry.get_person_work('Marcus Thompson')
             → [person_summary, commits, tickets, decisions]
4. build_context() → formatted person document block
5. llm.generate() → "Marcus has worked on..."
6. history.add_user_message() + history.add_assistant_message()
```

**Turn 2:** "Show me his recent commits"
```
1. resolve_references("his") → "Show me his recent commits (regarding: Marcus Thompson)"
2. classify() → person_query, entities=['Marcus Thompson'] (from prev_context hint)
3. retrieve() → commits for Marcus
4. generate() → lists commits
```

---

## Configuration

**Required in `.env` (project root):**

```env
GROQ_API_KEY=your_groq_api_key
DB_NAME=project_knowledge
DB_USER=your_username
DB_PASSWORD=your_password
DB_HOST=your_host.render.com
DB_PORT=5432
```

**Tuneable constants:**

| Constant | File | Default | Purpose |
|----------|------|---------|---------|
| `MAX_HISTORY_TURNS` | `main.py` | 10 | Turns kept in memory per session |
| `MAX_CONTEXT_CHARS` | `context/builder.py` | 8000 | Context string cap before LLM call |
| `MAX_HISTORY_CHARS` | `context/builder.py` | 1500 | History block cap inside context |

**Models:**

| Component | Model |
|-----------|-------|
| Response generation (`BytezLLM`) | `llama-3.3-70b-versatile` |
| Intent classification (`IntentClassifier`) | `llama-3.1-8b-instant` |

---

## Running the CLI

The chatbot includes an interactive CLI for testing without the API server:

```bash
cd /Users/Masters/Projects/Onboarding_AI
source venv/bin/activate
python -m chatbot.main
```

Or from inside the chatbot directory:

```bash
cd /Users/Masters/Projects/Onboarding_AI/chatbot
python main.py
```

**CLI commands:**

| Command | Description |
|---------|-------------|
| `quit` | Exit |
| `help` | Show example questions |
| `clear` | Clear conversation history |
| `debug` | Toggle verbose step-by-step logging |
| `topic` | Show current topic, entities, turn count |
| `status` | Show component health (DB, Groq) |

**Run the classifier test suite:**

```bash
python -m chatbot.intent.classifier
```

---

## Troubleshooting

| Issue | Likely cause | Fix |
|-------|-------------|-----|
| `503 Failed to initialize chatbot` from API | `GROQ_API_KEY` missing or wrong | Add/fix key in `.env`, restart server |
| Intent always `general_query` | Groq rate-limited → fell back to keyword rules | Wait for rate limit reset (midnight UTC); keyword fallback still works |
| Person query returns empty | Name not in `employees` table | Check `Employee.objects.all()` — name must be in DB for registry to find it |
| "I don't have information about..." | No matching docs in DB | Run the ingestion pipeline to populate data |
| `django.core.exceptions.ImproperlyConfigured` | Django not bootstrapped | Make sure you're using `venv/bin/python3.12` and running from project root |
| Follow-up returns wrong topic | Previous entities bleed into unrelated query | Type `clear` in CLI; or `bot.clear_history()` programmatically |
