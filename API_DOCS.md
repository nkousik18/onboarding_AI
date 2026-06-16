# API Documentation

Base URL: `http://127.0.0.1:8000/api`

Interactive docs (Swagger): `http://127.0.0.1:8000/api/docs/`

---

## Starting the Server

```bash
cd /Users/Masters/Projects/Onboarding_AI
source venv/bin/activate
python manage.py runserver
```

---

## Environment Variables (.env)

There are two `.env` files in this project — only edit the one at the **project root**:

| File | Used by | Edit this? |
|------|---------|-----------|
| `/Onboarding_AI/.env` | Django API server (`manage.py runserver`) | YES — add all tokens here |
| `/Onboarding_AI/database/.env` | Database scripts (`database/scripts/`) | Only if running scripts directly |

Restart the server after any changes to `.env`.

```env
# Django
SECRET_KEY=your_django_secret_key
DEBUG=True

# Database (Render PostgreSQL)
DB_NAME=project_knowledge
DB_USER=onboarding_user
DB_PASSWORD=your_db_password
DB_HOST=your_render_host.render.com
DB_PORT=5432

# Chatbot AI (Groq)
# Get key: console.groq.com → API Keys
GROQ_API_KEY=your_groq_api_key

# GitHub
# Get token: GitHub → Settings → Developer Settings → Personal Access Tokens → Generate new token (needs repo scope)
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_OWNER=org_or_username           # e.g. mycompany
GITHUB_REPO=repository_name           # e.g. backend-api
GITHUB_MAX_COMMITS=100                 # how many commits to pull per sync

# Jira
# Get token: Atlassian Account → Security → Create and manage API tokens
JIRA_DOMAIN=yourcompany.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=PAY                   # your Jira project key
JIRA_MAX_ISSUES=500                    # how many tickets to pull per sync

# Confluence
# Uses same Atlassian API token as Jira
CONFLUENCE_DOMAIN=yourcompany.atlassian.net
CONFLUENCE_EMAIL=your@email.com
CONFLUENCE_API_TOKEN=your_confluence_api_token
CONFLUENCE_SPACE_ID=your_space_id      # numeric ID of the Confluence space
CONFLUENCE_SPACE_KEY=ONBOARD           # key shown in the Confluence URL
```

---

## API Overview

| Category | What it does |
|----------|-------------|
| **Chat** | Send a natural-language question to the AI chatbot |
| **Read** | Fetch data already stored in the database |
| **Ingest** | Pull data from external sources into the database |
| **Delete** | Remove any record from the database |

---

## Chat API

The AI chatbot endpoint. Sends a natural-language question to the onboarding assistant and gets a structured response.

### POST `/api/chat/`

**Request body — first message:**
```json
{
    "query": "Why did we choose React?"
}
```

**Request body — follow-up (continue the conversation):**
```json
{
    "query": "Who made that decision?",
    "conversation_id": "89d58088-e5fe-4020-9e90-10cd4375bece"
}
```

Pass the `conversation_id` from the previous response to keep the bot in the same conversation. Omit it to start fresh.

**Response:**
```json
{
    "answer": "React was chosen because of the team's existing expertise...",
    "intent": "decision_query",
    "confidence": 0.85,
    "sources": ["decision:Use React for frontend", "meeting:Sprint 1 Planning"],
    "conversation_id": "89d58088-e5fe-4020-9e90-10cd4375bece",
    "turn": 1
}
```

| Field | Description |
|-------|-------------|
| `answer` | The AI's response text |
| `intent` | What the bot understood (decision_query, person_query, ticket_query, etc.) |
| `confidence` | Intent classifier confidence (0–1) |
| `sources` | Which database records were used to generate the answer |
| `conversation_id` | Copy this into your next request to continue the conversation |
| `turn` | Which turn number this is in the conversation |

**Requires in `.env`:** `GROQ_API_KEY`

**Note:** Conversation history is stored in memory only. If the server restarts, all conversation history is lost and a new `conversation_id` must be used.

### POST `/api/query/`

Alias for `/api/chat/` — same request/response shape. Used by the Chrome extension for compatibility.

---

## Auth

### POST `/api/register/`

Creates or updates an Employee record.

**Request body:**
```json
{
    "name": "Alice Chen",
    "email": "alice@company.com",
    "role": "Backend Engineer",
    "department": "Engineering"
}
```

- If an employee with the same email already exists, their record is updated and status 200 is returned.
- If the email is new, a new record is created and status 201 is returned.

**Response:** Employee object.

---

## Read APIs

All are GET requests, no body needed.

---

### Commits

#### `GET /api/commits/`
Returns every git commit, newest first. Includes changed files.

**Optional query param:** `?project_id=<uuid>` — filter to commits linked to a project.

#### `GET /api/commits/<sha>/`
Returns a single commit and its changed files by full SHA.

---

### Jira Tickets

#### `GET /api/tickets/`
Returns every Jira ticket.

**Optional query param:** `?project_id=<uuid>` — filter to tickets linked to a project.

#### `GET /api/tickets/<issue_key>/`
Returns a single ticket (e.g. `PAY-221`).

#### `GET /api/tickets/<issue_key>/context/`
Returns the ticket plus all linked commits, Confluence pages, and meetings via entity references.

**Response:**
```json
{
    "ticket": {...},
    "linked_commits": [...],
    "linked_pages": [...],
    "linked_meetings": [...]
}
```

#### `PATCH /api/tickets/<issue_key>/status/`
Update the status and/or assignee of a ticket.

**Request body:**
```json
{
    "status": "In Progress",
    "assignee": "Bob Smith"
}
```

Both fields are optional — send only what you want to change.

#### `POST /api/tickets/<issue_key>/comments/`
Add a comment to a ticket. Appended to the ticket's `comments` field with a timestamp.

**Request body:**
```json
{
    "text": "Blocked on the auth PR.",
    "author": "Alice Chen"
}
```

#### `POST /api/tickets/create/`
Create a new Jira ticket locally. Issue key is auto-generated as `TASK-1001`, `TASK-1002`, etc.

**Request body:**
```json
{
    "summary": "Add dark mode toggle",
    "description": "Optional longer description",
    "assignee": "Alice Chen",
    "priority": "Medium",
    "issue_type": "Task"
}
```

---

### Confluence Pages

#### `GET /api/pages/`
Returns a lightweight list of all Confluence pages (no full content).

#### `GET /api/pages/<uuid>/`
Returns a single page with full Markdown content.

---

### Meetings

#### `GET /api/meetings/`
Returns meetings with metadata and cleaned transcript.

**Optional query params:**
- `?date=YYYY-MM-DD` — filter by exact meeting date
- `?project_id=<uuid>` — filter to meetings linked to a project

#### `GET /api/meetings/<uuid>/`
Returns full meeting details.

---

### Projects

#### `GET /api/projects/`
Returns all projects with linked entities.

#### `GET /api/projects/<uuid>/`
Returns a single project.

#### `POST /api/projects/<uuid>/add-member/`
Append a name to the project's `team_members` list (no-op if already present).

**Request body:**
```json
{ "name": "Alice Chen" }
```

---

### Employees

#### `GET /api/employees/`
Returns all employees.

#### `GET /api/employees/<uuid>/`
Returns a single employee record.

---

### Sprints

#### `GET /api/sprints/`
Returns all sprints with linked tickets. Optional: `?project_id=<uuid>`.

#### `GET /api/sprints/<sprint_number>/`
Returns a single sprint by number (e.g. `1`, `2`, `3`).

#### `GET /api/sprints/<sprint_number>/tickets/`
Returns all tickets in the sprint with completion status and summary counts.

**Response:**
```json
{
    "id": "...",
    "sprint_number": 2,
    "name": "Sprint 2",
    "total_tickets": 10,
    "completed_count": 7,
    "pending_count": 3,
    "tickets": [...]
}
```

**Optional query param:** `?project_id=<uuid>` — disambiguate when sprint numbers are not unique across projects.

#### `GET /api/sprints/<sprint_number>/meetings/`
Returns all meetings whose date falls within the sprint's start and end dates.

---

### Decisions

#### `GET /api/decisions/`
Returns the unified decision timeline across meetings, Confluence, Jira, and commits.

**Optional query params:**
- `?category=architecture` — filter by category
- `?source_type=meeting` — filter by source (meeting, confluence, jira, git_commit)

#### `GET /api/decisions/<uuid>/`
Returns a single decision record.

---

### Search

#### `GET /api/search/?q=<query>`
Full-text search across commit messages, ticket summaries/descriptions, page titles/content, and meeting titles.

**Response:**
```json
{
    "query": "login",
    "commits": [...],
    "tickets": [...],
    "pages": [...],
    "meetings": [...]
}
```

---

### Activity

#### `GET /api/activity/`
Returns a blended feed of recent commits, ticket updates, and meetings, sorted newest-first.

**Optional query params:**
- `?project_id=<uuid>` — filter by project
- `?limit=<n>` — max number of items (default 20)

---

### Teams Messages

#### `GET /api/teams/messages/`
Returns Teams messages for a project. Currently returns placeholder data — a real Microsoft Teams integration is not yet implemented.

**Optional query params:**
- `?project_id=<uuid>`
- `?channel=<name>` — filter by channel name

---

## Ingest APIs

These trigger a sync from an external source into the database. All are POST requests.
Reads config from `.env` — no request body needed (except meetings which requires a file upload).
Safe to run multiple times — uses `update_or_create`, no duplicates.

---

### `POST /api/ingest/github/`

**Requires in `.env`:** `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`
**Optional in `.env`:** `GITHUB_MAX_COMMITS` (default: 100)

Pulls commits from the configured GitHub repo. Creates entity references linking commits to Jira ticket keys found in commit messages.

**Response:**
```json
{ "source": "github", "repository": "mycompany/backend-api", "created": 5, "updated": 12, "errors": 0, "total": 17 }
```

---

### `POST /api/ingest/jira/`

**Requires in `.env`:** `JIRA_DOMAIN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
**Optional in `.env`:** `JIRA_PROJECT_KEY` (default: PAY), `JIRA_MAX_ISSUES` (default: 500)

Pulls all tickets from the configured Jira project. Creates entity references for epic links.

**Response:**
```json
{ "source": "jira", "project": "PAY", "created": 10, "updated": 45, "errors": 0, "total": 55 }
```

---

### `POST /api/ingest/confluence/`

**Requires in `.env`:** `CONFLUENCE_DOMAIN`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_ID`
**Optional in `.env`:** `CONFLUENCE_SPACE_KEY` (default: ONBOARD)

Pulls all pages from the configured Confluence space, converts HTML to Markdown. Creates entity references for Jira ticket keys found in page content.

**Response:**
```json
{ "source": "confluence", "space": "ONBOARD", "created": 3, "updated": 8, "errors": 0, "total": 11 }
```

---

### `POST /api/ingest/meetings/`

**No `.env` vars needed.**

Upload a `.vtt` transcript file as `multipart/form-data` with key `file`. Extracts speakers and duration. Uploading the same filename again updates the existing record.

**In Postman:** Body → form-data → Key: `file`, type: File, upload `.vtt`

**Response:**
```json
{
    "source": "meeting",
    "meeting_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "2026-01-15 Standup",
    "created": true,
    "participants": 5,
    "duration_seconds": 1800,
    "ticket_references_created": 2
}
```

> `"created": true` = new record. `"created": false` = existing record updated.

---

## Delete API

### `DELETE /api/delete/<entity_type>/<id>/`

| What to delete | `entity_type` | `id` to use |
|----------------|--------------|-------------|
| Commit | `commits` | Full SHA |
| Jira Ticket | `tickets` | Issue key (e.g. `PAY-221`) |
| Confluence Page | `pages` | UUID |
| Meeting | `meetings` | UUID |
| Project | `projects` | UUID |
| Employee | `employees` | UUID |
| Sprint | `sprints` | UUID |
| Decision | `decisions` | UUID |

**Response:**
```json
{ "deleted": true, "entity_type": "meetings", "id": "550e8400-..." }
```

**Error — unknown entity type:**
```json
{ "error": "Unknown entity type \"foo\". Choose from: commits, tickets, pages, meetings, projects, employees, sprints, decisions" }
```

---

## Test

### `GET /api/test/`

Health check — returns `{ "message": "hello preety" }`. Use to verify the server is up.

---

## Common Errors

| Status | Message | Fix |
|--------|---------|-----|
| `400` | `GITHUB_TOKEN not set in environment` | Add `GITHUB_TOKEN` to `.env` and restart server |
| `400` | `GITHUB_OWNER and GITHUB_REPO must be set` | Add both to `.env` and restart |
| `400` | `No file uploaded` | Body → form-data → set key `file` with type File |
| `400` | `File must be a .vtt file` | Only `.vtt` files are accepted |
| `400` | `Unknown entity type` | Valid types: `commits tickets pages meetings projects employees sprints decisions` |
| `404` | Not Found | The ID doesn't exist — use the list endpoint to find valid IDs |
| `503` | Failed to initialize chatbot | `GROQ_API_KEY` is missing or invalid in `.env` |
| `500` | Internal Server Error | Check the terminal running `runserver` for the full traceback |

---

## Notes

- Always include the **trailing slash** in URLs — `/api/chat/` not `/api/chat`
- Ingest endpoints are **synchronous** — the request blocks until the sync completes. Large Jira syncs (500 tickets) can take a few minutes.
- Ingest endpoints use **update_or_create** — safe to run multiple times, no duplicates created.
- The Swagger UI at `/api/docs/` documents every endpoint with request/response schemas.
