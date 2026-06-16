/* ============================================================
   LightHouse — Solution Chat (Agentic Mode)
   ============================================================
   AI-powered assistant panel backed by the real OnboardingChatbot
   on the Django backend (/api/chat/). Supports multi-turn
   conversation memory, intent classification, and Groq responses.
   ============================================================ */

const Solution = (() => {
  // ── State ─────────────────────────────────────────────────
  let isOpen = false;
  let isThinking = false;
  let messages = [];
  let conversationId = Date.now();
  let chatHistory = [];          // { id, title, messages[], ts }
  let historyOpen = false;
  // ── DOM refs (set after inject) ───────────────────────────
  let panel, fab, messagesEl, textarea, sendBtn, statusText, statusDot;

  // ── Suggested questions ───────────────────────────────────
  const SUGGESTIONS = [
    { icon: 'search', text: 'What decisions were made this sprint?' },
    { icon: 'git-commit', text: 'Show me recent commits and their changes' },
    { icon: 'users', text: 'Who is working on what right now?' },
    { icon: 'file-text', text: 'Summarize the latest meeting notes' },
  ];

  // ── Icons ─────────────────────────────────────────────────
  const ICONS = {
    sparkles: '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/><line x1="12" y1="11" x2="12" y2="14"/><path d="M8 14h8"/></svg>',
    send: '<svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    close: '<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    clear: '<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    'git-commit': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><line x1="1.05" y1="12" x2="7" y2="12"/><line x1="17.01" y1="12" x2="22.96" y2="12"/></svg>',
    users: '<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    'file-text': '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
    user: '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    bot: '<svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="3"/><path d="M7 15h0"/><path d="M17 15h0"/><path d="M9 19h6"/></svg>',
    check: '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>',
    loader: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>',
    zap: '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    newchat: '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    history: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    edit: '<svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    collapse: '<svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>',
  };

  // ── Inject DOM ────────────────────────────────────────────
  function inject() {
    // Collapsed tab (replaces FAB)
    const tabEl = document.createElement('div');
    tabEl.className = 'solution-collapsed-tab';
    tabEl.title = 'Open Solution AI (Ctrl+L)';
    tabEl.innerHTML = `${ICONS.sparkles}<span>Solution</span><div class="tab-dot"></div>`;
    tabEl.addEventListener('click', toggle);
    document.body.appendChild(tabEl);
    fab = tabEl;

    // Panel
    const panelEl = document.createElement('div');
    panelEl.className = 'solution-panel';
    panelEl.innerHTML = `
      <div class="solution-header">
        <div class="solution-header-icon">${ICONS.sparkles}</div>
        <div>
          <div class="solution-header-title">Solution <span>AI</span></div>
          <div class="solution-header-subtitle">agentic assistant</div>
        </div>
        <div class="solution-header-actions">
          <button class="solution-header-btn" id="solutionNewChatBtn" title="New chat">${ICONS.newchat}</button>
          <button class="solution-header-btn" id="solutionHistoryBtn" title="Previous chats">${ICONS.history}</button>
          <button class="solution-header-btn" id="solutionCloseBtn" title="Collapse panel">${ICONS.collapse}</button>
        </div>
      </div>
      <div class="solution-history-drawer" id="solutionHistoryDrawer">
        <div class="solution-history-header">Previous Chats</div>
        <div class="solution-history-list" id="solutionHistoryList"></div>
      </div>
      <div class="solution-status">
        <div class="solution-status-dot" id="solutionStatusDot"></div>
        <span id="solutionStatusText">Ready — connected to knowledge base</span>
      </div>
      <div class="solution-messages" id="solutionMessages"></div>
      <div class="solution-input-area">
        <div class="solution-input-wrap">
          <textarea class="solution-textarea" id="solutionTextarea" placeholder="Ask Solution anything about this project..." rows="1"></textarea>
          <button class="solution-send-btn" id="solutionSendBtn" disabled>${ICONS.send}</button>
        </div>
        <div class="solution-hint">
          <span><kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> new line</span>
          <span><kbd>Ctrl+L</kbd> toggle</span>
        </div>
      </div>
    `;
    document.body.appendChild(panelEl);
    panel = panelEl;

    // Cache refs
    messagesEl = document.getElementById('solutionMessages');
    textarea = document.getElementById('solutionTextarea');
    sendBtn = document.getElementById('solutionSendBtn');
    statusText = document.getElementById('solutionStatusText');
    statusDot = document.getElementById('solutionStatusDot');

    // Events
    document.getElementById('solutionCloseBtn').addEventListener('click', close);
    document.getElementById('solutionNewChatBtn').addEventListener('click', newChat);
    document.getElementById('solutionHistoryBtn').addEventListener('click', toggleHistory);
    sendBtn.addEventListener('click', handleSend);

    textarea.addEventListener('input', () => {
      autoGrow();
      sendBtn.disabled = !textarea.value.trim() || isThinking;
    });

    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (textarea.value.trim() && !isThinking) handleSend();
      }
    });

    // Global keyboard shortcut
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
        e.preventDefault();
        toggle();
      }
      if (e.key === 'Escape' && isOpen) {
        close();
      }
    });

    showWelcome();
    loadHistory();

    // Restore chat panel state from localStorage
    if (localStorage.getItem('solutionChatOpen') === 'true') {
      open();
    }
  }

  // ── Auto-grow textarea ────────────────────────────────────
  function autoGrow() {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  }

  // ── Open / Close / Toggle ─────────────────────────────────
  function open() {
    isOpen = true;
    document.body.classList.add('solution-open');
    localStorage.setItem('solutionChatOpen', 'true');
    setTimeout(() => textarea.focus(), 350);
  }

  function close() {
    isOpen = false;
    document.body.classList.remove('solution-open');
    localStorage.setItem('solutionChatOpen', 'false');
  }

  function toggle() {
    isOpen ? close() : open();
  }

  // ── Welcome Screen ────────────────────────────────────────
  function showWelcome() {
    const suggestionsHtml = SUGGESTIONS.map(s => `
      <button class="solution-suggestion" onclick="Solution.askSuggestion('${escHtml(s.text)}')">
        ${ICONS[s.icon]}
        <span>${escHtml(s.text)}</span>
      </button>
    `).join('');

    messagesEl.innerHTML = `
      <div class="solution-welcome">
        <div class="solution-welcome-icon">${ICONS.sparkles}</div>
        <h3>Solution AI</h3>
        <p>Your agentic project assistant. I can search commits, tickets, meetings, decisions, and Confluence pages to answer your questions.</p>
        <div class="solution-suggestions">
          ${suggestionsHtml}
        </div>
      </div>
    `;
  }

  // ── Ask suggestion ────────────────────────────────────────
  function askSuggestion(text) {
    textarea.value = text;
    autoGrow();
    sendBtn.disabled = false;
    handleSend();
  }

  // ── Clear conversation ────────────────────────────────────
  function clearConversation() {
    messages = [];
    conversationId = generateId(); // new ID = fresh bot instance on backend
    showWelcome();
    setStatus('ready');
  }
  // ── Chat History (localStorage) ──────────────────────
const HISTORY_KEY = 'solution_chat_history';
const MAX_HISTORY = 20;

function loadHistory() {
  try {
    chatHistory = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch { chatHistory = []; }
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(chatHistory.slice(0, MAX_HISTORY)));
  } catch {}
}

function saveCurrentChat() {
  if (!messages.length) return;
  // Derive title from first user message
  const firstUser = messages.find(m => m.role === 'user');
  const title = firstUser ? firstUser.content.substring(0, 50) + (firstUser.content.length > 50 ? '…' : '') : 'Chat';

  // Update existing or create new
  const existing = chatHistory.findIndex(c => c.id === conversationId);
  const entry = { id: conversationId, title, messages: messages.slice(), ts: Date.now() };
  if (existing >= 0) {
    chatHistory[existing] = entry;
  } else {
    chatHistory.unshift(entry);
  }
  // Trim
  chatHistory = chatHistory.slice(0, MAX_HISTORY);
  saveHistory();
}

function newChat() {
  saveCurrentChat();
  messages = [];
  conversationId = Date.now();
  showWelcome();
  setStatus('ready');
  closeHistory();
}

function loadChat(id) {
  saveCurrentChat();
  const chat = chatHistory.find(c => c.id === id);
  if (!chat) return;
  conversationId = chat.id;
  messages = chat.messages.slice();
  // Re-render all messages
  messagesEl.innerHTML = '';
  messages.forEach((msg, idx) => {
    const div = document.createElement('div');
    div.className = 'msg';
    div.dataset.msgIndex = idx;
    div.innerHTML = `
      <div class="msg-avatar ${msg.role === 'user' ? 'user' : 'bot'}">
        ${msg.role === 'user' ? ICONS.user : ICONS.bot}
      </div>
      <div class="msg-body">
        <div class="msg-sender ${msg.role === 'user' ? 'user-name' : 'bot-name'}">${msg.role === 'user' ? 'You' : 'Solution'}</div>
        <div class="msg-content">${msg.role === 'user' ? escHtml(msg.content) : msg.content}</div>
        <div class="msg-time">${msg.time || ''}</div>
      </div>
      ${msg.role === 'user' ? `<button class="msg-edit-btn" onclick="Solution.editMessage(${idx})" title="Edit">${ICONS.edit}</button>` : ''}
    `;
    messagesEl.appendChild(div);
  });
  scrollToBottom();
  setStatus('ready');
  closeHistory();
}

function deleteChat(id, e) {
  e.stopPropagation();
  chatHistory = chatHistory.filter(c => c.id !== id);
  saveHistory();
  renderHistoryList();
}

function toggleHistory() {
  historyOpen ? closeHistory() : openHistory();
}

function openHistory() {
  historyOpen = true;
  renderHistoryList();
  document.getElementById('solutionHistoryDrawer').classList.add('open');
  document.getElementById('solutionHistoryBtn').classList.add('active');
}

function closeHistory() {
  historyOpen = false;
  document.getElementById('solutionHistoryDrawer').classList.remove('open');
  document.getElementById('solutionHistoryBtn').classList.remove('active');
}

function renderHistoryList() {
  const list = document.getElementById('solutionHistoryList');
  if (!chatHistory.length) {
    list.innerHTML = '<div class="solution-history-empty">No previous chats</div>';
    return;
  }
  list.innerHTML = chatHistory.map(c => {
    const date = new Date(c.ts);
    const when = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const msgCount = c.messages.filter(m => m.role === 'user').length;
    const isActive = c.id === conversationId;
    return `<div class="solution-history-item${isActive ? ' active' : ''}" onclick="Solution.loadChat(${c.id})">
      <div class="sh-item-body">
        <div class="sh-item-title">${escHtml(c.title)}</div>
        <div class="sh-item-meta">${when} · ${msgCount} message${msgCount !== 1 ? 's' : ''}</div>
      </div>
      <button class="sh-item-delete" onclick="Solution.deleteChat(${c.id}, event)" title="Delete">${ICONS.close}</button>
    </div>`;
  }).join('');
}
  // ── Handle Send ───────────────────────────────────────────
  async function handleSend() {
    const text = textarea.value.trim();
    if (!text || isThinking) return;

    // Remove welcome if present
    const welcome = messagesEl.querySelector('.solution-welcome');
    if (welcome) welcome.remove();

    // Add user message
    addMessage('user', text);
    saveCurrentChat();   // persist after each user message
    textarea.value = '';
    autoGrow();
    sendBtn.disabled = true;

    // Process via backend
    await processQuery(text);
  }

  // ── Add message to UI ─────────────────────────────────────
  function addMessage(role, content, extras = {}) {
    const now = new Date();
    const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const msg = { role, content, time, ...extras };
    messages.push(msg);
    const msgIndex = messages.length - 1;
    saveCurrentChat();   // persist after bot response too

    const div = document.createElement('div');
    div.className = 'msg';
    div.dataset.msgIndex = msgIndex;
    div.innerHTML = `
      <div class="msg-avatar ${role === 'user' ? 'user' : 'bot'}">
        ${role === 'user' ? ICONS.user : ICONS.bot}
      </div>
      <div class="msg-body">
        <div class="msg-sender ${role === 'user' ? 'user-name' : 'bot-name'}">${role === 'user' ? 'You' : 'Solution'}</div>
        <div class="msg-content">${role === 'user' ? escHtml(content) : content}</div>
        ${extras.steps ? renderSteps(extras.steps) : ''}
        ${extras.results ? renderResults(extras.results) : ''}
        <div class="msg-time">${time}</div>
      </div>
      ${role === 'user' ? `<button class="msg-edit-btn" onclick="Solution.editMessage(${msgIndex})" title="Edit">${ICONS.edit}</button>` : ''}
    `;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  // ── Thinking indicator ────────────────────────────────────
  function showThinking() {
    isThinking = true;
    sendBtn.disabled = true;
    setStatus('thinking');

    const div = document.createElement('div');
    div.className = 'msg';
    div.id = 'solutionThinking';
    div.innerHTML = `
      <div class="msg-avatar bot">${ICONS.bot}</div>
      <div class="msg-body">
        <div class="msg-sender bot-name">Solution</div>
        <div class="msg-steps" id="solutionSteps"></div>
        <div class="msg-thinking">
          <div class="msg-thinking-dot"></div>
          <div class="msg-thinking-dot"></div>
          <div class="msg-thinking-dot"></div>
        </div>
      </div>
    `;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function hideThinking() {
    isThinking = false;
    sendBtn.disabled = !textarea.value.trim();
    setStatus('ready');
    const el = document.getElementById('solutionThinking');
    if (el) el.remove();
  }

  function addStep(text, status = 'active') {
    const stepsEl = document.getElementById('solutionSteps');
    if (!stepsEl) return;

    // Complete previous active step
    const prev = stepsEl.querySelector('.msg-step.active');
    if (prev) {
      prev.classList.remove('active');
      prev.classList.add('done');
      prev.querySelector('.msg-step-icon').innerHTML = ICONS.check;
    }

    const step = document.createElement('div');
    step.className = `msg-step ${status}`;
    step.innerHTML = `
      <div class="msg-step-icon">${status === 'done' ? ICONS.check : ICONS.zap}</div>
      <span>${escHtml(text)}</span>
    `;
    stepsEl.appendChild(step);
    scrollToBottom();
  }

  function completeAllSteps() {
    const stepsEl = document.getElementById('solutionSteps');
    if (!stepsEl) return;
    stepsEl.querySelectorAll('.msg-step.active').forEach(s => {
      s.classList.remove('active');
      s.classList.add('done');
      s.querySelector('.msg-step-icon').innerHTML = ICONS.check;
    });
  }

  // ── Status ────────────────────────────────────────────────
  function setStatus(state) {
    if (state === 'thinking') {
      statusDot.classList.add('thinking');
      statusText.textContent = 'Thinking...';
    } else {
      statusDot.classList.remove('thinking');
      statusText.textContent = 'Ready — connected to knowledge base';
    }
  }

  // ── Process Query — calls /api/chat/ ──────────────────────
  async function processQuery(query) {
    showThinking();

    try {
      addStep('Analyzing your question...');
      await delay(300);

      addStep('Querying knowledge base...');

      const res = await fetch('/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, conversation_id: conversationId }),
      });

      addStep('Generating AI response...');
      await delay(200);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }

      const data = await res.json();

      // Persist conversation_id so follow-up questions use the same bot instance
      if (data.conversation_id) conversationId = data.conversation_id;

      const responseHtml = textToHtml(data.answer);

      // Convert source strings ("decision:Why we chose React") to result cards
      const sourceIcons = {
        decision:   '⚖️',
        confluence: '📄',
        jira:       '🎫',
        commit:     '🔀',
        meeting:    '📅',
        github:     '🐙',
      };
      const results = (data.sources || []).map(s => {
        const colonIdx = s.indexOf(':');
        const type = colonIdx > -1 ? s.substring(0, colonIdx).toLowerCase() : s.toLowerCase();
        const title = colonIdx > -1 ? s.substring(colonIdx + 1).trim() : s;
        return {
          type: type.charAt(0).toUpperCase() + type.slice(1),
          icon: sourceIcons[type] || '📎',
          title: title || s,
          meta: data.intent ? `${data.intent.replace(/_/g, ' ')} · turn ${data.turn || 1}` : '',
        };
      });

      // Build confidence badge
      const conf = data.confidence != null ? data.confidence : null;
      const confLabel = conf !== null
        ? (conf >= 0.7 ? 'high' : conf >= 0.4 ? 'medium' : 'low')
        : null;
      const intentBadge = data.intent
        ? `<span class="msg-intent-badge">${escHtml(data.intent.replace(/_/g, ' '))}</span>`
        : '';
      const confBadge = confLabel
        ? `<span class="msg-conf-badge msg-conf-${confLabel}">${Math.round(conf * 100)}% confidence</span>`
        : '';
      const metaHtml = (intentBadge || confBadge)
        ? `<div class="msg-response-meta">${intentBadge}${confBadge}</div>`
        : '';

      completeAllSteps();
      hideThinking();
      addMessage('bot', metaHtml + responseHtml, { results });

    } catch (err) {
      console.error('Solution error:', err);
      completeAllSteps();
      hideThinking();
      addMessage('bot',
        `<p>Sorry, I ran into an error: <code>${escHtml(err.message)}</code></p>` +
        `<p>Make sure the backend is running and set <code>GROQ_API_KEY</code> (or <code>BYTEZ_API_KEY</code>) in your <code>.env</code>.</p>`
      );
    }
  }

  // ── Render Helpers ────────────────────────────────────────
  function renderSteps(steps) {
    return `<div class="msg-steps">${steps.map(s => `
      <div class="msg-step done">
        <div class="msg-step-icon">${ICONS.check}</div>
        <span>${escHtml(s)}</span>
      </div>
    `).join('')}</div>`;
  }

  function renderResults(results) {
    if (!results || !results.length) return '';
    return `<div class="msg-citations">
      <button class="citation-toggle" onclick="this.parentElement.classList.toggle('expanded')">
        <span class="citation-toggle-label">Sources</span>
        <span class="citation-toggle-icon">▼</span>
      </button>
      <div class="citations-list">
        ${results.map((r, i) => `
          <a href="#" class="citation-item" data-index="${i}" onclick="event.preventDefault(); document.querySelectorAll('[data-citation-ref=\\'${i}\\']').forEach(el => el.scrollIntoView({behavior: 'smooth', block: 'center'}));">
            <span class="citation-num">${i + 1}</span>
            <span class="citation-icon">${r.icon || '📎'}</span>
            <div class="citation-content">
              <div class="citation-type">${escHtml(r.type)}</div>
              <div class="citation-title">${escHtml(r.title)}</div>
            </div>
          </a>
        `).join('')}
      </div>
    </div>`;
  }

  // ── Utilities ─────────────────────────────────────────────
  function escHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  // ── Markdown → HTML renderer ────────────────────────────
  // Handles: **bold**, *italic*, `code`, ```blocks```, headers,
  //          numbered lists, bullet lists, and paragraphs.
  function textToHtml(text) {
    if (!text) return '<p>No response received.</p>';

    // Normalise line endings
    const raw = text.replace(/\r\n/g, '\n');

    // Split into blocks separated by blank lines
    const blocks = raw.split(/\n\n+/);
    const htmlParts = [];

    for (const block of blocks) {
      const trimmed = block.trim();
      if (!trimmed) continue;

      // Fenced code block (```)
      if (trimmed.startsWith('```')) {
        const code = trimmed.replace(/^```[^\n]*\n?/, '').replace(/```$/, '');
        htmlParts.push(`<pre class="msg-code-block"><code>${escHtml(code)}</code></pre>`);
        continue;
      }

      // Header lines (# … ####)
      if (/^#{1,4}\s/.test(trimmed)) {
        const level = trimmed.match(/^(#+)/)[1].length;
        const content = trimmed.replace(/^#+\s*/, '');
        htmlParts.push(`<h${level + 1} class="msg-heading">${inlineMd(content)}</h${level + 1}>`);
        continue;
      }

      const lines = trimmed.split('\n');

      // Numbered list (1. … / 2. …)
      if (/^\d+[\.\)]\s/.test(lines[0])) {
        htmlParts.push(parseList(lines, 'ol'));
        continue;
      }

      // Bullet list (- … / * … / • …)
      if (/^[-*•]\s/.test(lines[0])) {
        htmlParts.push(parseList(lines, 'ul'));
        continue;
      }

      // Regular paragraph
      htmlParts.push(`<p>${inlineMd(escHtml(trimmed).replace(/\n/g, '<br>'))}</p>`);
    }

    return htmlParts.join('');
  }

  /** Parse a block of list lines into <ol>/<ul> with nested sub-items */
  function parseList(lines, tag) {
    let html = `<${tag} class="msg-list">`;
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      // Detect sub-item (indented - or * or numbered)
      const isSubItem = /^\s+[-*•]\s/.test(line) || /^\s+\d+[\.\)]\s/.test(line);
      const text = line.replace(/^\s*[-*•\d.\)]+\s*/, '');

      if (isSubItem) {
        // Collect consecutive sub-items
        const subLines = [];
        while (i < lines.length && (/^\s+[-*•]\s/.test(lines[i]) || /^\s+\d+[\.\)]\s/.test(lines[i]))) {
          subLines.push(lines[i]);
          i++;
        }
        const subTag = /^\s+\d+[\.\)]\s/.test(subLines[0]) ? 'ol' : 'ul';
        html += parseList(subLines.map(l => l.replace(/^\s{2,4}/, '')), subTag);
      } else {
        html += `<li>${inlineMd(escHtml(text))}</li>`;
        i++;
      }
    }
    html += `</${tag}>`;
    return html;
  }

  /** Apply inline markdown: **bold**, *italic*, `code` */
  function inlineMd(html) {
    return html
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>');
  }

  function generateId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function fmtDate(d) {
    if (!d) return '';
    try {
      return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch { return String(d); }
  }

  function delay(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  // ── Edit message ──────────────────────────────────────────
  function editMessage(index) {
    if (isThinking) return;
    const msg = messages[index];
    if (!msg || msg.role !== 'user') return;

    // Remove this message and everything after it from state
    messages = messages.slice(0, index);
    saveCurrentChat();

    // Remove the corresponding DOM elements
    const allMsgEls = messagesEl.querySelectorAll('.msg');
    for (let i = allMsgEls.length - 1; i >= 0; i--) {
      const elIdx = parseInt(allMsgEls[i].dataset.msgIndex, 10);
      if (elIdx >= index) allMsgEls[i].remove();
    }

    // If no messages left, show welcome
    if (!messages.length) showWelcome();

    // Put the text into the textarea for editing
    textarea.value = msg.content;
    autoGrow();
    sendBtn.disabled = false;
    textarea.focus();
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ── Public API ────────────────────────────────────────────
  return {
    init: inject,
    open,
    close,
    toggle,
    askSuggestion,
    loadChat,
    deleteChat,
    editMessage,
  };
})();

// ── Auto-initialize on DOM ready ────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => Solution.init());
} else {
  Solution.init();
}
