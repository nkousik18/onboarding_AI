# LIGHTHOUSE Frontend — Feature Documentation

> **Generated**: March 7, 2026  
> **Stack**: Vanilla JS (no framework) · Vite 6.2.0 · Dark sci-fi theme  
> **Dev server**: `localhost:3000` proxying API to Django at `localhost:8000`

---

## Table of Contents

1. [Login Page](#1-login-page)
2. [Register Page](#2-register-page)
3. [Forgot Password Page](#3-forgot-password-page)
4. [Project Dashboard Page](#4-project-dashboard-page-main-application)
5. [Workspace / Integrations Page](#5-workspace--integrations-page)
6. [Solution AI Chat Panel](#6-solution-ai-chat-panel-global)
7. [Shared Design System](#7-shared-design-system)

---

## 1. Login Page

**File**: `frontend/login.html`  
**Route**: `/` (dev server rewrites to `login.html`)  
**Styles**: Inline `<style>` tag  
**Scripts**: Inline `<script>` tag  

### What It Is
The entry point of the application — a sign-in form where users authenticate with email and password.

### Why It's Used
Acts as the authentication gate. All other pages check `sessionStorage.isLoggedIn` and redirect here if the user hasn't authenticated.

### Features

| Feature | Description |
|---|---|
| **Email & Password Fields** | Standard form inputs with validation (email must contain `@`, password ≥ 1 char) |
| **Password Visibility Toggle** | Eye icon toggles between `password` and `text` input types |
| **Remember Me Checkbox** | UI checkbox (visual only, not persisted to backend) |
| **Forgot Password Link** | Navigates to `forgot_password.html` |
| **Register Link** | Navigates to `register.html` |
| **Animated Background** | Full-page `bg.jpg` with an animated radial glow effect |
| **Session Storage Auth** | On submit: stores `isLoggedIn`, `userEmail`, `userName`, `jiraDomain` in `sessionStorage`, then redirects to `project_dashboard.html` |

### API Endpoints
| Endpoint | Method | Purpose |
|---|---|---|
| *(none)* | — | Client-side only; no backend auth verification |

---

## 2. Register Page

**File**: `frontend/register.html`  
**Route**: `/register`  
**Styles**: `static/css/auth.css`  
**Scripts**: `static/js/auth.js` + inline `<script>`  

### What It Is
An account creation form that collects user details and registers them as an employee in the system.

### Why It's Used
Onboards new team members into the platform by creating their employee record in the database, which subsequently appears in project dashboards, member chips, and team listings.

### Features

| Feature | Description |
|---|---|
| **Full Name Input** | Collects the user's display name |
| **Email Input** | Email address with `@` validation |
| **Role Dropdown** | 12 roles: Engineering Manager, Software Engineer, Frontend Developer, Backend Developer, Full Stack Developer, DevOps Engineer, QA Engineer, UI/UX Designer, Product Manager, Data Analyst, Scrum Master, Technical Lead |
| **Department Dropdown** | 9 departments: Engineering, Product, Design, QA, Data, DevOps, Management, Security, Research |
| **Password with Strength Meter** | Visual bar that checks: length ≥ 8, uppercase, lowercase, number, bonus at ≥ 12 chars. Colors: red → orange → yellow → green |
| **Confirm Password** | Must match password field |
| **Backend Registration** | Sends `POST /api/register/` to create employee record |

### API Endpoints
| Endpoint | Method | Body | Purpose |
|---|---|---|---|
| `POST /api/register/` | POST | `{name, email, role, department}` | Creates an employee in the knowledge base |

---

## 3. Forgot Password Page

**File**: `frontend/forgot_password.html`  
**Route**: `/forgot_password`  
**Styles**: `static/css/auth.css`  
**Scripts**: `static/js/auth.js`  

### What It Is
A simple password reset request form.

### Why It's Used
Allows users who have forgotten their password to request a reset link via email.

### Features

| Feature | Description |
|---|---|
| **Back to Login Link** | Returns to `login.html` |
| **Lock Icon** | Visual indicator of the page purpose |
| **Email Input** | Collects the user's email address |
| **Submit Button** | Client-side validation only (no backend reset flow implemented) |

### API Endpoints
| Endpoint | Method | Purpose |
|---|---|---|
| *(none)* | — | Reset flow not connected to backend |

---

## 4. Project Dashboard Page (Main Application)

**File**: `frontend/project_dashboard.html`  
**Route**: `/project_overview` (also `/project_overview?page=integrations`)  
**Styles**: `project_dashboard.css` (~2300 lines), `integrations.css` (~700 lines), `solution_chat.css` (~700 lines)  
**Scripts**: `project_dashboard.js` (~2100 lines, ES module), `solution_chat.js` (~690 lines)  

### What It Is
The primary hub of the application — a rich project overview dashboard that aggregates sprints, decisions, tickets, meetings, and integrations into a single view.

### Why It's Used
Gives team members a comprehensive, real-time view of their project's state — what was decided, who's working on what, how sprints are progressing, and what happened in meetings. This is the page users land on after login.

### Features

#### 4.1 — Sidebar Navigation

| Feature | Description |
|---|---|
| **Collapsible Sidebar** | Toggles between full and icon-only mode; state saved in `localStorage` |
| **Project Rail** | Vertical strip of gradient orbs — one per project. Click to switch active project |
| **Sub-links** | "Overview" and "Ecosystem" links for SPA-style navigation |
| **Flyout Card** | Hovering a project orb shows a floating card with name, status, and description |
| **User Chip** | Bottom of sidebar: avatar initials, name, role, and logout button |
| **Mobile Responsive** | On ≤ 900px: sidebar becomes a slide-out overlay with dim backdrop |

#### 4.2 — Top Bar & Stats

| Feature | Description |
|---|---|
| **Page Title** | "Project Overview" with dynamic subtitle showing project name |
| **Stat Chips** | Dynamic counters: Total tickets, Done, Pending, Blockers, In Progress, Story Points — calculated from the tickets API |

#### 4.3 — Project Goal Banner

| Feature | Description |
|---|---|
| **Project Description** | Displays the project's goal/description text |
| **Team Toggle** | Collapsible section showing all team members |
| **Member Chips** | Each member displays: avatar initials, name, Owner badge (if applicable), **(new) badge** (if added within last 2 days — auto-expires) |
| **Member Hover Tooltip** | On hover: role, department, email link, Microsoft Teams "Chat on Teams" link |

#### 4.4 — Project Summary Banner

| Feature | Description |
|---|---|
| **Auto-generated Prose Summary** | A rich text summary of the project synthesized from all data (sprints, tickets, meetings, decisions) |
| **Decision Timeline Map** | Visual timeline showing decisions grouped by category with 3 view modes: overall, grouped, filtered |

#### 4.5 — Sprint Timeline

| Feature | Description |
|---|---|
| **Horizontal Timeline** | Row of sprint nodes displayed chronologically |
| **Sprint Progress Bar** | Each node shows completion percentage based on ticket statuses |
| **Active Sprint Highlight** | Current sprint is visually emphasized |
| **Click to Select** | Clicking a sprint node loads its detail panel |

#### 4.6 — Detail Panel (4 Tabs)

**Tab 1 — AI Summary**

| Feature | Description |
|---|---|
| **Sprint Summary** | Auto-generated prose summary of the selected sprint |
| **Calendar Grid** | Monthly calendar with dots indicating meeting days |
| **Meeting Day Click** | Clicking a day with meetings opens the meeting popup |

**Tab 2 — Meetings**

| Feature | Description |
|---|---|
| **Meeting Cards** | Lists all meetings for the selected sprint with date, title, and participant count |
| **Meeting Popup Modal** | Full-screen overlay showing: summary, key decisions, action items, participants, and meeting metadata |

**Tab 3 — Outcomes**

| Feature | Description |
|---|---|
| **Ticket List** | All tickets associated with the sprint |
| **3 View Modes** | All tickets, grouped by sprint, grouped by assignee |
| **Ticket Cards** | Each card shows: type icon (Task/Story/Bug/Epic), priority badge, assignee avatar, comments count, status badge |
| **Member Count** | Shows number of unique assignees |

**Tab 4 — Decisions**

| Feature | Description |
|---|---|
| **Decision Cards** | Lists all project decisions with title, date, status, confidence bar |
| **3 View Modes** | Overall, grouped by category, filter by single category |
| **Decision Entry** | Shows: title, status (Active/Superseded), confidence percentage bar, decided-by list, rationale, source block, tags |
| **Source Enrichment** | Automatically links decisions back to meetings, Confluence pages, tickets, or commits by fetching related entities |

#### 4.7 — Integrations Section (inline)

| Feature | Description |
|---|---|
| **SPA Toggle** | Accessible via `?page=integrations` without page reload (uses `pushState`) |
| **Jira Card** | Stats: total tickets, completed, in progress, blockers; buttons: Open Dashboard, View Tickets |
| **Confluence Card** | Stats: total pages, spaces, authors, last updated; buttons: Open Confluence, View Pages |
| **GitHub Card** | Stats: total commits, contributors, files changed, last commit; buttons: Open Repository, View Commits |
| **New Integration Modal** | Grid of 6 available integrations: Zoom, Google Meet, Slack, MS Teams, Outlook Calendar, Trello — each triggers a simulated OAuth sign-in flow |

#### 4.8 — Loading Overlay

| Feature | Description |
|---|---|
| **Animated Orbit** | Central LIGHTHOUSE logo with 4 orbiting icons (Jira, GitHub, Teams, Confluence) |
| **Progress Bar** | Animated fill bar with phase text: "Connecting to knowledge base" → "Fetching sprints & project data" → "Loading integrations" → "Preparing AI insights" |
| **Auto-dismiss** | Disappears when all parallel data fetches complete |

### API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/projects/` | GET | Load project rail, goal banner, summary, integration links |
| `POST /api/projects/{id}/add-member/` | POST | Auto-add logged-in user to project team |
| `GET /api/sprints/` | GET | Fetch all sprints for the timeline |
| `GET /api/sprints/{n}/meetings/` | GET | Fetch meetings for a specific sprint |
| `GET /api/meetings/` | GET | Meeting list for popup matching |
| `GET /api/meetings/{id}/` | GET | Meeting detail for decision source enrichment |
| `GET /api/tickets/` | GET | Ticket data for stats, outcomes tab, integrations |
| `GET /api/employees/` | GET | Employee lookup for member chips and tooltips |
| `GET /api/decisions/` | GET | All decisions for decisions tab and timeline map |
| `GET /api/pages/` | GET | Confluence pages for integrations stats |
| `GET /api/pages/{id}/` | GET | Confluence page detail for decision enrichment |
| `GET /api/commits/` | GET | Git commits for integrations stats |

---

## 5. Workspace / Integrations Page

**Files**: `frontend/workspace.html`, `frontend/integrations.html` (near-identical)  
**Route**: `/workspace` or `/integrations`  
**Styles**: `project_dashboard.css`, `integrations.css`, `solution_chat.css`  
**Scripts**: `integrations.js` (ES module), `solution_chat.js`  

### What It Is
A standalone integrations page showing connected data sources (Jira, Confluence, GitHub) with detailed data browsing.

### Why It's Used
Provides a dedicated view to inspect the raw data flowing in from external tools — useful for verifying that integrations are working correctly and browsing source data outside the sprint-centric dashboard view.

### Features

| Feature | Description |
|---|---|
| **Sidebar** | Dashboard + Ecosystem navigation links |
| **3 Integration Cards** | Jira (Project Management), Confluence (Documentation), GitHub (Version Control) — each with green "Connected" badge |
| **Stat Boxes** | Each card shows 4 stat counters pulled from APIs |
| **Open External Link** | Buttons linking to the actual Jira/Confluence/GitHub instances |
| **Expandable Detail Section** | Click "View Tickets/Pages/Commits" to reveal a data table/grid below the cards |
| **Jira Table** | Columns: key, summary, type, status, priority, assignee — with color-coded badges |
| **Confluence Grid** | Card grid layout: title, space, author, creation date |
| **GitHub Table** | Columns: SHA, message, author, date, files changed — file count chips |
| **Search & Filter** | Search input + dropdown filter (e.g., status, type) within each detail section |

### API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/projects/` | GET | Project data for setting external tool links |
| `GET /api/tickets/` | GET | Jira ticket list and stats |
| `GET /api/pages/` | GET | Confluence page list and stats |
| `GET /api/commits/` | GET | GitHub commit list and stats |

---

## 6. Solution AI Chat Panel (Global)

**File**: `static/js/solution_chat.js` + `static/css/solution_chat.css`  
**Available on**: `project_dashboard.html`, `workspace.html`, `integrations.html`  

### What It Is
A persistent AI assistant panel that slides out from the right side of the screen, powered by the OnboardingChatbot backend via Groq (llama-3.3-70b-versatile).

### Why It's Used
Enables natural-language Q&A about the project — users can ask about decisions, commits, tickets, meetings, and team members without manually navigating through data.

### Features

| Feature | Description |
|---|---|
| **Collapsed Tab** | Bottom-right corner tab labeled "Solution" with sparkle icon; click or `Ctrl+L` to toggle |
| **Slide-out Panel** | 400px wide panel with header, messages area, and input |
| **Welcome Screen** | 4 suggested questions: "What decisions were made this sprint?", "Show me recent commits", "Who is working on what?", "Summarize the latest meeting notes" |
| **Message Bubbles** | User messages (right-aligned) and bot messages (left-aligned) with avatars and timestamps |
| **Markdown Rendering** | Bot responses render: **bold**, *italic*, `inline code`, ```code blocks```, # headers, numbered lists, bullet lists |
| **Thinking Indicator** | 3 animated dots + step-by-step progress (Analyzing → Querying → Generating) |
| **Intent Badge** | Shows classified intent (e.g., "decision query", "general query") on bot responses |
| **Confidence Badge** | Color-coded confidence level: green (≥70%), yellow (40–69%), red (<40%) |
| **Source Cards** | Below each response: type-specific emoji icons (⚖️ decision, 📄 confluence, 🎫 jira, 🔀 commit, 📅 meeting) with source title and metadata |
| **Message Editing** | Click the edit icon on any user message to re-send it (removes all subsequent messages) |
| **Chat History** | Stored in `localStorage` (max 20 chats). Previous chats accessible via history drawer |
| **New Chat** | Creates a fresh conversation with a new `conversation_id` |
| **Keyboard Shortcuts** | `Ctrl+L` toggle, `Escape` close, `Enter` send, `Shift+Enter` new line |
| **Multi-turn Memory** | Backend maintains conversation context via `conversation_id` — the bot resolves references like "it" or "that decision" across turns |

### API Endpoints

| Endpoint | Method | Body | Purpose |
|---|---|---|---|
| `POST /api/chat/` | POST | `{query, conversation_id}` | Send natural-language query to AI chatbot |

### Response Format
```json
{
  "answer": "Markdown-formatted response text...",
  "intent": "decision_query",
  "confidence": 0.8,
  "sources": ["decision:Title of decision", "confluence:Page title"],
  "conversation_id": "uuid",
  "turn": 1
}
```

---

## 7. Shared Design System

### Theme Variables

| Variable | Value | Usage |
|---|---|---|
| `--bg` | `#040a18` | Page background |
| `--surface` | `#0b1528` | Card backgrounds |
| `--surface2` | `#111d33` | Secondary surfaces |
| `--accent` | `#1e8fff` | Primary blue accent |
| `--accent2` | `#6c5ce7` | Secondary purple accent |
| `--success` | `#00d48a` | Green for done/active |
| `--warn` | `#f5a623` | Orange for warnings |
| `--danger` | `#ff4d6a` | Red for errors/blockers |
| `--text` | `#e8edf5` | Primary text color |
| `--secondary` | `#8899b4` | Muted text color |
| `--border` | `rgba(30,143,255,0.12)` | Subtle borders |

### Fonts

| Font | Variable | Usage |
|---|---|---|
| Rajdhani | `--font-heading` | Display headings |
| Source Sans 3 | `--font-body` | Body text |
| JetBrains Mono | `--font-mono` | Code, stats, badges |

### Auth Guard
All pages (except login, register, forgot_password) check:
```javascript
if (!sessionStorage.getItem('isLoggedIn')) {
  window.location.href = 'login.html';
}
```

### Empty Pages
- `home.html` — Exists in build config but has no content
- `detail.html` — Exists in build config but has no content
- `template/base.html` — Exists as a Django template base but unused by the Vite frontend
