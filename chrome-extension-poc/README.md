# LightHouse Chrome Extension

A Chrome side panel extension that gives instant access to the LIGHTHOUSE knowledge base from any web page. Query the AI chatbot, view Jira tickets, check meetings, and browse Teams messages — all without leaving the page you're on.

---

## Installation (Development)

1. Open `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** and select this `chrome-extension-poc/` folder
4. The extension appears in your toolbar and injects a floating button on every page

---

## How to Use

**Floating button:** A blue circle button appears on every page (bottom-right). Click it to open/close the side panel.

**Context menu:** Right-click any selected text → "Ask LightHouse about this text". Right-click anywhere → "Ask LightHouse about this page". The side panel opens with the query pre-filled.

**Chat:** The "Ask LightHouse" input is always visible at the bottom of the side panel, regardless of which tab is open. Send a question; the response comes from `POST /api/query/` on the backend.

---

## The 4 Tabs

| Tab | Content |
|-----|---------|
| **Overview** | Recent activity feed (`/api/activity/`), quick links to Confluence pages, Git commits (`/api/commits/`), sprint info (`/api/sprints/`) |
| **Tickets** | Jira tickets list (`/api/tickets/`); create a task (`POST /api/tickets/create/`); change ticket status (`PATCH /api/tickets/<id>/status/`); add comment (`POST /api/tickets/<id>/comments/`) |
| **Calendar** | Upcoming meetings from `/api/meetings/`; falls back to placeholder data if the backend returns nothing |
| **Teams** | Teams messages from `/api/teams/messages/` (returns placeholder data — real Microsoft Teams integration not yet implemented) |

---

## Configuration

Click the profile icon (top right of the panel) to open Settings:

| Setting | Default | Notes |
|---------|---------|-------|
| Backend URL | `http://localhost:8000` | Change this for staging/production |
| Voice Search toggle | — | Saved to Chrome storage but **does nothing** — voice was removed. Left as a placeholder. |
| Context Menu toggle | enabled | Controls whether the right-click "Ask LightHouse" items appear |

Settings are saved to `chrome.storage.local`. Logout clears storage and opens `http://localhost:3000/login.html`.

---

## File Structure

```
chrome-extension-poc/
├── manifest.json        # Manifest V3; side panel at popup.html
├── popup.html           # Side panel UI (4 tabs + persistent chat)
├── popup.css            # Dark navy theme
├── popup.js             # All panel logic (~1000 lines)
├── background.js        # Service worker: context menus, side panel toggle
├── content.js           # Injects floating button on every page
├── README.md            # This file
└── images/
    ├── icon-16.png
    ├── icon-48.png
    ├── icon-128.png
    ├── icon-lighthouse.svg
    ├── icon-chat.svg
    ├── icon-projects.svg
    ├── icon-calendar.svg
    └── icon-teams.svg
```

---

## API Endpoints Used

All calls go to the backend URL configured in settings (default `http://localhost:8000`).

| Method | Endpoint | Used by |
|--------|----------|---------|
| `POST` | `/api/query/` | Chat input (alias for `/api/chat/`) |
| `GET` | `/api/tickets/` | Tickets tab |
| `POST` | `/api/tickets/create/` | Create task modal |
| `PATCH` | `/api/tickets/<key>/status/` | Change status modal |
| `POST` | `/api/tickets/<key>/comments/` | Ticket detail → Add Comment |
| `GET` | `/api/employees/` | Assignee dropdowns |
| `GET` | `/api/meetings/` | Calendar tab |
| `GET` | `/api/teams/messages/` | Teams tab |
| `GET` | `/api/activity/` | Overview → Recent Activity |
| `GET` | `/api/commits/` | Overview → Git Commits link |
| `GET` | `/api/sprints/` | Overview → Sprint Info link |

All endpoints are documented in `API_DOCS.md` at the project root.

---

## Development Notes

- **Manifest V3 side panel** — the extension opens as a side panel (`chrome.sidePanel`), not a popup. The HTML is `popup.html` but it renders in the browser's native side panel.
- **No auth in the extension** — authentication is handled by the main web app. The extension reads user info from `SOLUTION_USER_INFO` in `chrome.storage.local` if present; it does not perform login itself.
- **Project selector** — the project dropdown is hardcoded with "Employee Onboarding Portal" and "Payment Processing System". Tickets/meetings are filtered by `?project_id=<selection>` when a project is chosen.
- **Reload after edits** — after changing any file, go to `chrome://extensions/` and click the refresh icon on the LightHouse entry.
- **Debugging** — right-click the extension icon → "Inspect" for the side panel DevTools. Service worker logs are in `chrome://extensions/` → Details → "Inspect views: service worker".
