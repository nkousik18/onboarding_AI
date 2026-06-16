# LIGHTHOUSE Frontend

Vanilla JS multi-page application (MPA) that provides the browser UI for the LIGHTHOUSE onboarding assistant. No framework — pure HTML + CSS + JavaScript, bundled by Vite.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Directory Layout](#directory-layout)
3. [Pages](#pages)
4. [JavaScript Modules](#javascript-modules)
5. [Auth Model](#auth-model)
6. [API Integration](#api-integration)
7. [Dev Server](#dev-server)
8. [Build](#build)

---

## Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Vite | 6.2.0 | Dev server, HMR, production build |
| Vanilla JS | ES2022+ | All interactivity (no React/Vue/Svelte) |
| CSS custom properties | — | Dark sci-fi theme with light mode toggle |
| `localStorage` | — | Theme preference, chat history |
| `sessionStorage` | — | Login state, user name/email across pages |

---

## Directory Layout

```
frontend/
├── package.json             # Vite project config
├── vite.config.js           # Dev server (port 3000), proxy, MPA entry points
│
├── login.html               # Login page
├── register.html            # Registration page
├── project_dashboard.html   # Main app shell (sprints, tickets, decisions, people)
├── integrations.html        # Jira / GitHub / Confluence data viewer + ingest triggers
├── workspace.html           # Workspace view (integrations alias)
├── employee_personal.html   # Personal task list + calendar (per-employee view)
├── home.html                # Marketing / landing page
├── detail.html              # Detail view (generic entity detail)
├── 404.html                 # Error page
│
└── static/
    ├── css/                 # Per-page and shared stylesheets
    ├── js/
    │   ├── project_dashboard.js   # Main dashboard logic (~2100 lines)
    │   ├── solution_chat.js       # AI chat panel (IIFE, loaded on most pages)
    │   ├── integrations.js        # Integrations/workspace page logic
    │   ├── employee_personal.js   # Employee personal page logic
    │   ├── auth.js                # Password strength meter + form validation UI (register page)
    │   └── theme-toggle.js        # Dark/light theme slider (self-contained IIFE)
    └── img/                 # Static images and icons
```

---

## Pages

| Page | JS loaded | Description |
|------|-----------|-------------|
| `login.html` | inline only | Client-side validation; sets `sessionStorage` and redirects to dashboard |
| `register.html` | `auth.js` + inline | Calls `POST /api/register/` to create an Employee record, then sets `sessionStorage` |
| `project_dashboard.html` | `project_dashboard.js` + `solution_chat.js` | Main app: sprints, tickets, decisions, people, activity feed |
| `integrations.html` | `integrations.js` + `solution_chat.js` | Jira tickets, GitHub commits, Confluence pages; ingest buttons |
| `workspace.html` | `integrations.js` + `solution_chat.js` | Same as integrations (alternate route) |
| `employee_personal.html` | `employee_personal.js` | Personal task list grouped by project, calendar, skills |
| `home.html` | inline only | Landing/marketing page |
| `detail.html` | inline only | Generic entity detail |

---

## JavaScript Modules

### `project_dashboard.js`

The main app shell. Loaded as `type="module"`.

- **State**: `SPRINTS`, `activeSprint`, `decisionsData`, `employeesCache`, `ticketsData`
- **Data fetching**: All data fetched in parallel on load via `Promise.all`. Each resource cached with a promise-singleton (`fetchSprints`, `fetchTicketsOnce`, `fetchDecisionsOnce`, `fetchEmployeesOnce`).
- **Auth guard**: Checks `sessionStorage.getItem('isLoggedIn')` on load; redirects to `login.html` if missing.
- **Loading animation**: One-time overlay plays after login, suppressed on navigation back (`sessionStorage.dashboardLoaded`).
- **Key features**: Sprint timeline, member chips with hover tooltips linking to Teams/email, ticket board, decisions panel, people rail, activity feed.

### `solution_chat.js`

Self-contained IIFE exported as `window.Solution`. Loaded on the dashboard, integrations, and workspace pages.

- Calls `POST /api/chat/` with `{ query, conversation_id }`.
- Tracks `conversationId` across turns for multi-turn memory in the backend.
- Persists up to 20 saved chats to `localStorage` under key `solution_chat_history`.
- **Exports**: `Solution.init()`, `Solution.open()`, `Solution.close()`, `Solution.toggle()`, `Solution.askSuggestion()`, `Solution.loadChat()`, `Solution.deleteChat()`, `Solution.editMessage()`

### `integrations.js`

Loaded on `integrations.html` and `workspace.html`.

- Fetches and renders Jira tickets (`/api/tickets/`), GitHub commits (`/api/commits/`), Confluence pages (`/api/pages/`).
- Triggers data ingest via `POST /api/ingest/github/`, `/api/ingest/jira/`, `/api/ingest/confluence/`.
- Builds external links (Jira board, Confluence space, GitHub repo) from project metadata.

### `employee_personal.js`

Loaded only on `employee_personal.html`.

- Fetches employee data from `/api/employees/?email=<email>`.
- Attempts to load per-user tasks and skills from project-specific endpoints; falls back to mock data when endpoints return empty.
- Renders a monthly calendar with task-due-date indicators.
- Local task completion calls `PATCH /api/tickets/<issue_key>/status/`.

### `auth.js`

Loaded only on `register.html`.

- Password visibility toggle (show/hide).
- Password strength meter (4 criteria + length bonus → Weak / Fair / Good / Strong).
- Client-side form validation for login, register, and forgot-password forms.
- No API calls — pure UI logic.

### `theme-toggle.js`

Self-contained IIFE. Can be added to any page with `<button id="lhThemeToggle"></button>` or auto-creates the button if absent.

- Reads/writes `localStorage.theme` (`"dark"` or `"light"`).
- Sets `data-theme` attribute on `<html>` immediately (before DOM ready) to prevent flash of wrong theme.
- Default theme is `dark`.

---

## Auth Model

The frontend uses **sessionStorage**, not JWT tokens.

| Action | How it works |
|--------|-------------|
| Login | `login.html` validates the form client-side and writes `isLoggedIn`, `userEmail`, `userName`, `jiraDomain` to `sessionStorage`. No backend call. |
| Register | `register.html` calls `POST /api/register/` (creates/updates an `Employee` record), then writes the same `sessionStorage` keys and redirects. |
| Auth guard | Each protected page checks `sessionStorage.getItem('isLoggedIn')` on load; redirects to `login.html` if missing. |
| Session lifetime | Until the browser tab/window is closed (sessionStorage is tab-scoped). |

**Note:** There is no JWT authentication in the current backend. The files `api-client.js` and `api-bridge.js` were earlier prototypes of a JWT auth layer; they have been removed as they were unused dead code.

---

## API Integration

All API calls use plain `fetch()` with relative `/api/...` paths. Vite's dev server proxy rewrites these to `http://localhost:8000`.

No authentication headers are sent — the backend endpoints are currently open (no token required).

The AI chat panel (`solution_chat.js`) calls:

```js
fetch('/api/chat/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query, conversation_id })
})
```

See `API_DOCS.md` for the full list of available endpoints.

---

## Dev Server

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

The Vite dev server (port 3000) proxies `/api` to Django at `http://localhost:8000`. Make sure Django is running before opening any page that fetches data.

```bash
# In a separate terminal:
cd /Users/Masters/Projects/Onboarding_AI
source venv/bin/activate
python manage.py runserver
```

---

## Build

```bash
cd frontend
npm run build      # outputs to dist/
```

Vite builds all 8 HTML entry points as a multi-page app. The `dist/` output is suitable for static hosting (Netlify, Vercel, S3) with the Django API deployed separately.
