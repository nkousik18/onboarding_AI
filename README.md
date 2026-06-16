# LIGHTHOUSE — AI Onboarding Assistant

An AI-powered employee onboarding assistant that aggregates institutional knowledge from GitHub, Jira, Confluence, and meeting transcripts into a unified knowledge base. New hires ask natural-language questions and get grounded answers with source citations instead of digging through four disconnected tools.

Built for **DAE AI Hackathon 2026**.

---

## What's Inside

| Surface | Description |
|---------|-------------|
| **Django REST API** | 34 endpoints — ingestion, chat, read, write, delete |
| **AI Chatbot** | Groq LLMs, 12 intent types, multi-turn conversation |
| **Vite Frontend** | 8-page vanilla JS app (no framework) |
| **Chrome Extension** | Manifest V3 side panel — access from any web page |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Backend framework | Django 5.2 + Django REST Framework |
| API docs | drf-spectacular (Swagger UI at `/api/docs/`) |
| Database | PostgreSQL (Render) |
| LLM — generation | Groq `llama-3.3-70b-versatile` |
| LLM — classification | Groq `llama-3.1-8b-instant` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) |
| Frontend | Vite 6.2 + Vanilla JS |
| Chrome extension | Manifest V3 side panel |
| Env management | python-dotenv |

---

## Project Structure

```
Onboarding_AI/
├── manage.py
├── .env                         ← secrets (never commit)
├── requirements.txt
│
├── config/                      ← Django project config
│   ├── settings.py
│   └── urls.py
│
├── api/                         ← REST API (34 endpoints)
│   ├── views.py                 ← all views (~1 238 lines)
│   ├── urls.py                  ← all routes
│   ├── serializers.py           ← DRF serializers
│   └── ingestion.py             ← GitHub / Jira / Confluence / VTT ingest
│
├── chatbot/                     ← AI chatbot module
│   ├── main.py                  ← OnboardingChatbot orchestrator
│   ├── intent/                  ← LLM-first classifier (12 intents)
│   ├── retriever/               ← SQL retrieval + PeopleRegistry
│   ├── context/                 ← context builder (8 000 char cap)
│   └── llm/                     ← Groq wrapper (BytezLLM class)
│
├── database/                    ← raw SQL schema + scripts
│   ├── scripts/                 ← standalone ingestion / analysis scripts
│   └── knowledge_base/models.py ← 10 Django models (managed=False)
│
├── frontend/                    ← Vite MPA (8 pages)
│   ├── vite.config.js           ← dev server port 3000, proxy → 8000
│   ├── *.html                   ← login, register, dashboard, integrations, etc.
│   └── static/js/               ← 6 JS modules
│
├── chrome-extension-poc/        ← Chrome side panel extension
│   ├── manifest.json
│   ├── popup.html / popup.js    ← 4-tab panel + persistent chat
│   ├── background.js            ← service worker
│   └── content.js               ← floating button injected on all pages
│
└── docs/                        ← all project documentation
    ├── resume_project_doc.md    ← condensed source of truth (all layers)
    ├── DECISION_INTELLIGENCE_CHANGES.md
    └── ...
```

---

## Quick Start

### 1 — Backend

```bash
git clone https://github.com/nkousik18/onboarding_AI.git
cd onboarding_AI

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env              # fill in values (see below)

python manage.py runserver        # http://localhost:8000
```

> **Do not run `makemigrations` or `migrate`.**
> All models use `managed = False` — the database schema is created by raw SQL scripts in `database/scripts/`.

### 2 — Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

Vite proxies `/api` → `http://localhost:8000`. Keep Django running.

### 3 — Chrome Extension

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `chrome-extension-poc/`
4. Click the extension icon or the floating button on any page

---

## Environment Variables

All secrets in `.env` at the project root. Never commit this file.

```env
# Django
SECRET_KEY=your_django_secret_key
DEBUG=True

# Database (Render PostgreSQL)
DB_NAME=project_knowledge
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your-host.render.com
DB_PORT=5432

# Groq (powers the AI chatbot)
# Get key: console.groq.com → API Keys
GROQ_API_KEY=your_groq_api_key

# GitHub
GITHUB_TOKEN=your_personal_access_token
GITHUB_OWNER=org_or_username
GITHUB_REPO=repository_name
GITHUB_MAX_COMMITS=100

# Jira
JIRA_DOMAIN=yourcompany.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=PAY
JIRA_MAX_ISSUES=500

# Confluence (same Atlassian token as Jira)
CONFLUENCE_DOMAIN=yourcompany.atlassian.net
CONFLUENCE_EMAIL=your@email.com
CONFLUENCE_API_TOKEN=your_confluence_api_token
CONFLUENCE_SPACE_ID=your_space_id
CONFLUENCE_SPACE_KEY=ONBOARD
```

---

## Key Endpoints

| Method | Endpoint | What it does |
|--------|----------|-------------|
| `POST` | `/api/chat/` | Ask the AI chatbot (multi-turn) |
| `POST` | `/api/register/` | Create / update an employee record |
| `POST` | `/api/ingest/github/` | Pull commits from GitHub |
| `POST` | `/api/ingest/jira/` | Pull tickets from Jira |
| `POST` | `/api/ingest/confluence/` | Pull pages from Confluence |
| `POST` | `/api/ingest/meetings/` | Upload a `.vtt` meeting transcript |
| `GET` | `/api/decisions/` | Unified decision timeline |
| `GET` | `/api/search/?q=<query>` | Full-text search across all entities |
| `GET` | `/api/docs/` | Swagger UI (all 34 endpoints) |

---

## Common Commands

```bash
# Run Django dev server
python manage.py runserver

# Open Django shell
python manage.py shell

# Run the chatbot CLI directly (no server needed)
python -m chatbot.main

# Test intent classifier
python -m chatbot.intent.classifier
```

---

## Documentation

| Doc | What it covers |
|-----|---------------|
| [`docs/resume_project_doc.md`](docs/resume_project_doc.md) | Condensed source of truth — all layers, quantifiable stats |
| [`API_DOCS.md`](API_DOCS.md) | All 34 endpoints with request/response examples |
| [`FRONTEND_README.md`](FRONTEND_README.md) | Frontend pages, JS modules, auth model, build |
| [`FRONTEND_FEATURES.md`](FRONTEND_FEATURES.md) | Feature-by-feature breakdown of every page |
| [`chatbot/README.md`](chatbot/README.md) | Chatbot pipeline, 12 intents, models, configuration |
| [`chrome-extension-poc/README.md`](chrome-extension-poc/README.md) | Extension setup, tabs, API endpoints used |
| [`database/Database.md`](database/Database.md) | Schema, 10 models, raw SQL setup |
| [`docs/DECISION_INTELLIGENCE_CHANGES.md`](docs/DECISION_INTELLIGENCE_CHANGES.md) | All 8 Decision Intelligence changes |
