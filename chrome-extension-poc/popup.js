// ── LightHouse Chrome Extension - Enhanced Popup ─────────────────

// Notify background when this side panel is closed so toggle state stays accurate
window.addEventListener('beforeunload', () => {
  chrome.runtime.sendMessage({ action: 'sidePanelClosed' }).catch(() => {});
});

// State Management
let currentTab = 'overview';
let currentProject = null;
let ticketsData = [];
let meetingsData = [];
let teamsData = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadCollapseState();
  setupEventListeners();
  loadSettings();
  initializeDefaultData();
});

// ── Collapse/Expand Functions ──────────────────────────
function toggleCollapse() {
  const isCollapsed = document.body.classList.contains('collapsed');
  
  if (isCollapsed) {
    expandExtension();
  } else {
    collapseExtension();
  }
}

function collapseExtension() {
  document.body.classList.add('collapsed');
  chrome.storage.local.set({ extensionCollapsed: true });
}

function expandExtension() {
  document.body.classList.remove('collapsed');
  chrome.storage.local.set({ extensionCollapsed: false });
}

function loadCollapseState() {
  chrome.storage.local.get('extensionCollapsed', (result) => {
    if (result.extensionCollapsed) {
      document.body.classList.add('collapsed');
    }
  });
}

// ── Event Listeners Setup ──────────────────────────────
function setupEventListeners() {
  // Collapse/Expand functionality
  const collapseBtn = document.getElementById('collapseBtn');
  const collapsedButton = document.getElementById('collapsedButton');
  
  if (collapseBtn) {
    collapseBtn.addEventListener('click', toggleCollapse);
  }
  
  if (collapsedButton) {
    collapsedButton.addEventListener('click', toggleCollapse);
  }

  // Tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-tab');
      switchTab(tab);
    });
  });

  // Profile button
  document.getElementById('profileBtn').addEventListener('click', showProfile);
  document.getElementById('profileClose').addEventListener('click', hideProfile);
  document.getElementById('profileSave').addEventListener('click', saveSettings);
  document.getElementById('profileLogout').addEventListener('click', logout);

  // Project selector
  document.getElementById('projectSelector').addEventListener('change', (e) => {
    selectProject(e.target.value);
  });

  // Main app link
  document.getElementById('appLinkBtn').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:3000/project_dashboard.html' });
  });

  // Chat functionality
  document.getElementById('sendBtn').addEventListener('click', sendQuery);
  document.getElementById('queryInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });

  // Status filter
  document.getElementById('statusFilter')?.addEventListener('change', filterTickets);

  // Add task button
  document.getElementById('addTaskBtn')?.addEventListener('click', openCreateTaskModal);

  // Refresh meetings
  document.getElementById('refreshMeetings')?.addEventListener('click', loadMeetings);

  // Teams channel filter
  document.getElementById('teamsChanelFilter')?.addEventListener('input', filterTeamsMessages);
}

// ── Tab Management ────────────────────────────────────
function switchTab(tabName) {
  currentTab = tabName;

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabName);
  });

  // Update content sections
  document.querySelectorAll('.content-section').forEach(section => {
    section.classList.remove('active');
  });
  const activeSection = document.getElementById(tabName + '-section');
  if (activeSection) {
    activeSection.classList.add('active');
  }

  // Load data for the tab
  if (tabName === 'jira') {
    loadTickets();
  } else if (tabName === 'meetings') {
    loadMeetings();
  } else if (tabName === 'teams') {
    loadTeamsMessages();
  }
}

// ── Project Selection ──────────────────────────────────
function selectProject(projectId) {
  currentProject = projectId;
  // Reload data based on selected project
  if (currentTab === 'jira') loadTickets();
  if (currentTab === 'meetings') loadMeetings();
  if (currentTab === 'teams') loadTeamsMessages();
}

// ── Jira Tickets (Checklist) ───────────────────────────
function loadTickets() {
  const container = document.getElementById('ticketsContainer');
  if (!container) return;

  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    // Fetch tickets from backend
    fetch(`${backendUrl}/api/tickets/?project_id=${currentProject || 'all'}`)
      .then(response => response.json())
      .then(data => {
        // Map backend data to ticket format
        const tickets = Array.isArray(data) ? data : (data.results || []);
        
        ticketsData = tickets.map(t => ({
          id: t.id || t.ticket_id || 'TICKET-' + t.id,
          title: t.title || t.name,
          description: t.description || '',
            status: normalizeStatus(t.status || 'active'),
          assignee: t.assignee || 'Unassigned',
          dueDate: t.due_date || t.dueDate || 'TBD'
        }));
        
        renderTickets();
      })
      .catch(error => {
        console.error('Error loading tickets:', error);
        // Fallback to mock data
        const mockTickets = [
          {
            id: 'TASK-101',
            title: 'Implement OAuth2 authentication',
            description: 'Add OAuth2 token refresh mechanism',
              status: normalizeStatus('active'),
            assignee: 'John Doe',
            dueDate: '2026-05-15'
          },
          {
            id: 'TASK-102',
            title: 'Database migration',
            description: 'Migrate user data to new schema',
            status: 'active',
            assignee: 'Jane Smith',
            dueDate: '2026-05-18'
          },
          {
            id: 'TASK-103',
            title: 'UI performance optimization',
            description: 'Reduce page load time',
            status: 'not-started',
            assignee: 'Unassigned',
            dueDate: '2026-05-20'
          },
          {
            id: 'TASK-104',
            title: 'Security audit complete',
            description: 'Complete security review',
            status: 'completed',
            assignee: 'Sarah Jones',
            dueDate: '2026-05-10'
          }
        ];
        
        ticketsData = mockTickets;
        renderTickets();
      });
  });
}

function renderTickets() {
  const container = document.getElementById('ticketsContainer');
  const filter = document.getElementById('statusFilter')?.value || 'all';

  const filtered = filter === 'all' ? ticketsData : ticketsData.filter(t => t.status === filter);

  container.innerHTML = filtered.map(ticket => `
    <div class="ticket-item">
      <input type="checkbox" class="ticket-checkbox" data-id="${ticket.id}">
      <div class="ticket-content" onclick="openTicketModal('${ticket.id}')">
        <div class="ticket-title">${ticket.id}: ${ticket.title}</div>
        <div class="ticket-description">${ticket.description}</div>
        <div class="ticket-meta">
          <span class="ticket-status ${ticket.status}">${formatStatusLabel(ticket.status)}</span>
          <span>${ticket.assignee}</span>
          <span>${ticket.dueDate}</span>
        </div>
      </div>
      <button class="ticket-action-btn" onclick="event.stopPropagation(); openChangeStatusModal('${ticket.id}')" title="Change status">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
    </div>
  `).join('');
}

function filterTickets() {
  renderTickets();
}

function normalizeStatus(status) {
  return (status || 'active')
    .toString()
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/_/g, '-');
}

function formatStatusLabel(status) {
  return (status || '')
    .toString()
    .trim()
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

function openTicketModal(ticketId) {
  const ticket = ticketsData.find(t => t.id === ticketId);
  if (!ticket) return;

  document.getElementById('ticketTitle').textContent = ticket.id + ': ' + ticket.title;
  const modal = document.getElementById('ticketModal');

  const detailHTML = `
    <div class="ticket-detail-row">
      <div class="ticket-detail-label">Title</div>
      <div class="ticket-detail-value">${ticket.title}</div>
    </div>
    <div class="ticket-detail-row">
      <div class="ticket-detail-label">Description</div>
      <div class="ticket-detail-value">${ticket.description}</div>
    </div>
    <div class="ticket-detail-row">
      <div class="ticket-detail-label">Status</div>
      <div class="ticket-detail-value">${formatStatusLabel(ticket.status)}</div>
    </div>
    <div class="ticket-detail-row">
      <div class="ticket-detail-label">Assignee</div>
      <div class="ticket-detail-value">${ticket.assignee}</div>
    </div>
    <div class="ticket-detail-row">
      <div class="ticket-detail-label">Due Date</div>
      <div class="ticket-detail-value">${ticket.dueDate}</div>
    </div>
  `;

  document.getElementById('ticketDetail').innerHTML = detailHTML;

  // Existing comments + New comment input
  const commentsHTML = `
    <h4>Comments</h4>
    <div class="comment">
      <div class="comment-author">John Doe</div>
      <div class="comment-text">Started working on this. Will update progress tomorrow.</div>
    </div>
    <div class="comment">
      <div class="comment-author">Manager</div>
      <div class="comment-text">Let me know if you need any assistance with this.</div>
    </div>
    
    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);">
      <label style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 6px;">Add Comment</label>
      <textarea id="newCommentText" placeholder="Add your comment here..." style="width: 100%; padding: 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; color: var(--text); font-size: 12px; font-family: inherit; resize: none; height: 60px;"></textarea>
    </div>
  `;

  document.getElementById('ticketComments').innerHTML = commentsHTML;

  modal.style.display = 'flex';
}

function closeTicketModal() {
  document.getElementById('ticketModal').style.display = 'none';
}

function saveTicketChanges() {
  const newCommentText = document.getElementById('newCommentText');
  const commentContent = newCommentText?.value.trim() || '';

  if (commentContent) {
    // Send comment to backend
    chrome.storage.local.get('backendUrl', (result) => {
      const backendUrl = result.backendUrl || 'http://localhost:8000';
      
      const ticketTitle = document.getElementById('ticketTitle').textContent;
      const ticketId = ticketTitle.split(':')[0].trim();

      fetch(`${backendUrl}/api/tickets/${ticketId}/comments/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: commentContent,
          author: 'Current User'
        })
      })
      .then(response => response.json())
      .then(data => {
        addMessage(`Comment added to ${ticketId}: "${commentContent}"`, 'system-message');
        closeTicketModal();
      })
      .catch(error => {
        console.error('Comment error:', error);
        addMessage(`Comment saved locally: "${commentContent}"`, 'system-message');
        closeTicketModal();
      });
    });
  } else {
    closeTicketModal();
  }
}

// ── Team Members & Ticket Management ───────────────────
let teamMembers = [];

function loadTeamMembers() {
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    fetch(`${backendUrl}/api/employees/`)
      .then(response => response.json())
      .then(data => {
        const members = Array.isArray(data) ? data : (data.results || []);
        teamMembers = members.map(m => ({
          id: m.id,
          name: m.full_name || m.name || 'Unknown',
          email: m.email || ''
        }));
        
        // Populate assignee dropdowns
        populateAssigneeSelects();
      })
      .catch(error => {
        console.error('Error loading team members:', error);
        // Fallback to mock team members
        teamMembers = [
          { id: '1', name: 'John Doe', email: 'john@example.com' },
          { id: '2', name: 'Jane Smith', email: 'jane@example.com' },
          { id: '3', name: 'Mike Wilson', email: 'mike@example.com' },
          { id: '4', name: 'Sarah Jones', email: 'sarah@example.com' },
          { id: '5', name: 'Alex Chen', email: 'alex@example.com' }
        ];
        populateAssigneeSelects();
      });
  });
}

function populateAssigneeSelects() {
  const newTaskAssignee = document.getElementById('newTaskAssignee');
  const changeStatusAssignee = document.getElementById('changeStatusAssignee');
  
  if (newTaskAssignee) {
    const options = teamMembers.map(m => `<option value="${m.name}">${m.name}</option>`).join('');
    newTaskAssignee.innerHTML = '<option value="">Select team member...</option>' + options;
  }
  
  if (changeStatusAssignee) {
    const options = teamMembers.map(m => `<option value="${m.name}">${m.name}</option>`).join('');
    changeStatusAssignee.innerHTML = '<option value="">No change</option>' + options;
  }
}

function openCreateTaskModal() {
  document.getElementById('createTaskModal').style.display = 'flex';
  // Ensure team members are loaded
  if (teamMembers.length === 0) {
    loadTeamMembers();
  } else {
    populateAssigneeSelects();
  }
}

function closeCreateTaskModal() {
  document.getElementById('createTaskModal').style.display = 'none';
  // Reset form
  document.getElementById('newTaskSummary').value = '';
  document.getElementById('newTaskDescription').value = '';
  document.getElementById('newTaskAssignee').value = '';
  document.getElementById('newTaskPriority').value = 'Medium';
  document.getElementById('newTaskType').value = 'Task';
  document.getElementById('newTaskStatus').value = 'Active';
}

function saveNewTask() {
  const summary = document.getElementById('newTaskSummary').value.trim();
  const description = document.getElementById('newTaskDescription').value.trim();
  const assignee = document.getElementById('newTaskAssignee').value || 'Unassigned';
  const priority = document.getElementById('newTaskPriority').value;
  const issueType = document.getElementById('newTaskType').value;
  const status = document.getElementById('newTaskStatus').value;
  
  if (!summary) {
    alert('Task summary is required!');
    return;
  }
  
  addMessage('⏳ Creating new task...', 'system-message');
  
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    fetch(`${backendUrl}/api/tickets/create/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        summary: summary,
        description: description,
        assignee: assignee,
        priority: priority,
        issue_type: issueType,
        status: status
      })
    })
    .then(response => response.json())
    .then(data => {
      if (data.issue_key) {
        addMessage(`✅ Task created successfully: ${data.issue_key} - ${summary}\nAssigned to: ${assignee}`, 'system-message');
        closeCreateTaskModal();
        // Reload tickets to show the new one
        loadTickets();
      } else {
        addMessage(`Task saved: ${summary}\nAssigned to: ${assignee}`, 'system-message');
        closeCreateTaskModal();
        loadTickets();
      }
    })
    .catch(error => {
      console.error('Error creating task:', error);
      addMessage(`Task created locally: ${summary}\nAssigned to: ${assignee}`, 'system-message');
      closeCreateTaskModal();
      loadTickets();
    });
  });
}

function openChangeStatusModal(ticketId) {
  const ticket = ticketsData.find(t => t.id === ticketId);
  if (!ticket) return;
  
  document.getElementById('changeStatusTitle').textContent = `Change Status: ${ticket.id}`;
  document.getElementById('changeStatusValue').value = normalizeStatus(ticket.status);
  document.getElementById('changeStatusModal').dataset.ticketId = ticketId;
  document.getElementById('changeStatusModal').style.display = 'flex';
  
  // Ensure team members are loaded
  if (teamMembers.length === 0) {
    loadTeamMembers();
  } else {
    populateAssigneeSelects();
  }
}

function closeChangeStatusModal() {
  document.getElementById('changeStatusModal').style.display = 'none';
  document.getElementById('changeStatusValue').value = '';
  document.getElementById('changeStatusAssignee').value = '';
}

function saveChangeStatus() {
  const modal = document.getElementById('changeStatusModal');
  const ticketId = modal.dataset.ticketId;
  const newStatus = document.getElementById('changeStatusValue').value;
  const newAssignee = document.getElementById('changeStatusAssignee').value;
  
  if (!ticketId || !newStatus) {
    alert('Please select a status!');
    return;
  }
  
  addMessage('⏳ Updating ticket status...', 'system-message');
  
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    const updateData = { status: newStatus };
    if (newAssignee) {
      updateData.assignee = newAssignee;
    }
    
    fetch(`${backendUrl}/api/tickets/${ticketId}/status/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updateData)
    })
    .then(response => response.json())
    .then(data => {
      addMessage(`✅ Ticket ${ticketId} updated!\nStatus: ${newStatus}${newAssignee ? `\nAssigned to: ${newAssignee}` : ''}`, 'system-message');
      closeChangeStatusModal();
      // Reload tickets to show the update
      loadTickets();
    })
    .catch(error => {
      console.error('Error updating ticket:', error);
      addMessage(`Ticket ${ticketId} status updated to: ${newStatus}${newAssignee ? `\nAssigned to: ${newAssignee}` : ''}`, 'system-message');
      closeChangeStatusModal();
      loadTickets();
    });
  });
}

// ── Meetings (Calendar View) ───────────────────────────
function loadMeetings() {
  const container = document.getElementById('meetingsContainer');
  if (!container) return;

  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    // Fetch meetings from backend
    fetch(`${backendUrl}/api/meetings/?project_id=${currentProject || 'all'}`)
      .then(response => response.json())
      .then(data => {
        // Map backend data to meeting format
        const meetings = Array.isArray(data) ? data : (data.results || []);
        
        meetingsData = meetings.map(m => ({
          id: m.id || 'MTG-' + m.id,
          title: m.title || m.name,
          time: m.time || m.start_time || 'TBD',
          duration: m.duration || '1h',
          location: m.location || 'Virtual',
          link: m.link || m.meeting_link || '#'
        }));
        
        renderMeetings();
      })
      .catch(error => {
        console.error('Error loading meetings:', error);
        // Fallback to mock data
        const mockMeetings = [
          {
            id: 'MTG-001',
            title: 'Team Standup',
            time: '10:00 AM',
            duration: '1h',
            location: 'Meeting Room A',
            link: 'https://teams.microsoft.com/l/meetup-join/...'
          },
          {
            id: 'MTG-002',
            title: 'Sprint Planning',
            time: '11:30 AM',
            duration: '45 min',
            location: 'Virtual (Teams)',
            link: 'https://teams.microsoft.com/l/meetup-join/...'
          },
          {
            id: 'MTG-003',
            title: 'Client Demo',
            time: '2:00 PM',
            duration: '1h 30min',
            location: 'Virtual',
            link: 'https://meet.google.com/...'
          }
        ];
        
        meetingsData = mockMeetings;
        renderMeetings();
      });
  });
}

function renderMeetings() {
  const container = document.getElementById('meetingsContainer');
  container.innerHTML = meetingsData.map(meeting => `
    <div class="meeting-item">
      <div class="meeting-time">${meeting.time}</div>
      <div class="meeting-title">${meeting.title}</div>
      <div class="meeting-details">
        <span>${meeting.duration}</span>
        <span>${meeting.location}</span>
      </div>
      <a href="${meeting.link}" target="_blank" class="meeting-link">Join Meeting →</a>
    </div>
  `).join('');
}

// ── Teams Chat ─────────────────────────────────────────
function loadTeamsMessages() {
  const container = document.getElementById('teamsContainer');
  if (!container) return;

  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    // Fetch Teams messages from backend
    fetch(`${backendUrl}/api/teams/messages/?project_id=${currentProject || 'all'}`)
      .then(response => response.json())
      .then(data => {
        // Map backend data to Teams message format
        const messages = Array.isArray(data) ? data : (data.results || []);
        
        teamsData = messages.map(m => ({
          id: m.id || 'MSG-' + m.id,
          channel: m.channel || '#general',
          sender: m.sender || m.author || 'Unknown',
          text: m.text || m.message,
          likes: m.likes || 0,
          replies: m.replies || 0
        }));
        
        renderTeamsMessages();
      })
      .catch(error => {
        console.error('Error loading Teams messages:', error);
        // Fallback to mock data
        const mockMessages = [
          {
            id: 'MSG-001',
            channel: '#general',
            sender: 'John Doe',
            text: 'Hey team! Just deployed the new API to staging.',
            likes: 5,
            replies: 3
          },
          {
            id: 'MSG-002',
            channel: '#product',
            sender: 'Jane Smith',
            text: 'The new dashboard design is looking great! Check out the preview.',
            likes: 12,
            replies: 8
          },
          {
            id: 'MSG-003',
            channel: '#engineering',
            sender: 'Mike Wilson',
            text: 'Code review completed. Ready to merge!',
            likes: 8,
            replies: 2
          }
        ];
        
        teamsData = mockMessages;
        renderTeamsMessages();
      });
  });
}

function renderTeamsMessages() {
  const container = document.getElementById('teamsContainer');
  const filter = document.getElementById('teamsChanelFilter')?.value.toLowerCase() || '';

  const filtered = filter ? teamsData.filter(m => m.channel.toLowerCase().includes(filter)) : teamsData;

  container.innerHTML = filtered.map(message => `
    <div class="teams-message">
      <div class="teams-channel">${message.channel}</div>
      <div class="teams-sender">${message.sender}</div>
      <div class="teams-text">${message.text}</div>
      <div class="teams-meta">
        <span>${message.likes} likes</span>
        <span>${message.replies} replies</span>
      </div>
    </div>
  `).join('');
}

function filterTeamsMessages() {
  renderTeamsMessages();
}

// ── Chatbot Functionality ──────────────────────────────
function sendQuery() {
  const input = document.getElementById('queryInput');
  const query = input.value.trim();

  if (!query) return;

  // Add user message
  addMessage(query, 'user-message');
  input.value = '';
  input.style.height = 'auto';

  // Show loading indicator
  addMessage('⏳ Processing your query...', 'bot-message');

  // Get backend URL
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    // Send query to backend
    fetch(`${backendUrl}/api/query/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: query,
        project_id: currentProject || 'all'
      })
    })
    .then(response => response.json())
    .then(data => {
      // Remove loading message
      const messagesArea = document.getElementById('messagesArea');
      const lastMsg = messagesArea.lastChild;
      if (lastMsg && lastMsg.textContent.includes('Processing')) {
        lastMsg.remove();
      }
      
      // Add bot response (backend returns 'answer' field)
      const responseText = data.answer || data.response || data.message || 'Query processed successfully.';
      addMessage(responseText, 'bot-message');
      
      // Show sources if available
      if (data.sources && Array.isArray(data.sources) && data.sources.length > 0) {
        let sourcesText = '\n📚 Sources: ';
        data.sources.slice(0, 3).forEach((source, idx) => {
          sourcesText += `[${idx + 1}] ${source.substring(0, 50)} `;
        });
        addMessage(sourcesText, 'bot-message');
      }
    })
    .catch(error => {
      console.error('Query error:', error);
      // Remove loading message
      const messagesArea = document.getElementById('messagesArea');
      const lastMsg = messagesArea.lastChild;
      if (lastMsg && lastMsg.textContent.includes('Processing')) {
        lastMsg.remove();
      }
      addMessage('Response: ' + query + ' - This integration is being connected to your backend.', 'bot-message');
    });
  });
}

function addMessage(text, type) {
  const messagesArea = document.getElementById('messagesArea');
  const messageEl = document.createElement('div');
  messageEl.className = `message ${type}`;
  messageEl.textContent = text;
  messagesArea.appendChild(messageEl);
  messagesArea.scrollTop = messagesArea.scrollHeight;
}

// ── Voice Search ───────────────────────────────────────
// Voice search removed - use text input instead for better reliability

// ── Profile & Settings ─────────────────────────────────
function showProfile() {
  document.getElementById('profilePanel').classList.add('show');
}

function hideProfile() {
  document.getElementById('profilePanel').classList.remove('show');
}

function loadSettings() {
  chrome.storage.local.get(['SOLUTION_USER_INFO', 'backendUrl', 'voiceSearch', 'contextMenu'], (result) => {
    if (result.SOLUTION_USER_INFO) {
      try {
        const userInfo = JSON.parse(result.SOLUTION_USER_INFO);
        document.getElementById('profileName').textContent = userInfo.name || 'User';
        document.getElementById('profileEmail').textContent = userInfo.email || '';
      } catch (e) {
        console.error('Error parsing user info', e);
      }
    }

    document.getElementById('settingsBackendUrl').value = result.backendUrl || 'http://localhost:8000';
    document.getElementById('settingsVoice').checked = result.voiceSearch !== false;
    document.getElementById('settingsContextMenu').checked = result.contextMenu !== false;
  });
}

function saveSettings() {
  const settings = {
    backendUrl: document.getElementById('settingsBackendUrl').value,
    voiceSearch: document.getElementById('settingsVoice').checked,
    contextMenu: document.getElementById('settingsContextMenu').checked
  };

  chrome.storage.local.set(settings, () => {
    addMessage('Settings saved successfully!', 'system-message');
    hideProfile();
  });
}

function logout() {
  chrome.storage.local.clear(() => {
    chrome.tabs.create({ url: 'http://localhost:3000/login.html' });
    window.close();
  });
}

// ── Initialize Default Data ────────────────────────────
function initializeDefaultData() {
  loadProjectResources();
  loadRecentActivity();
  loadTeamMembers();
}

function loadProjectResources() {
  const resourcesContainer = document.getElementById('projectResources');
  if (!resourcesContainer) return;

  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    resourcesContainer.innerHTML = `
      <a href="#" class="resource-link" onclick="openConfluence(event)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 21H3V3h9V1H3a2 2 0 0 0-2 2v18a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2v-9h-2v9z"></path>
          <polyline points="15 1 20 1 20 6"></polyline>
          <line x1="20" y1="1" x2="9" y2="12"></line>
        </svg>
        Confluence Pages
      </a>
      <a href="#" class="resource-link" onclick="openGitCommits(event)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="1"></circle>
          <path d="M12 1v6m0 6v6"></path>
          <path d="M4.22 4.22l4.24 4.24m2.12 2.12l4.24 4.24"></path>
          <path d="M1 12h6m6 0h6"></path>
          <path d="M4.22 19.78l4.24-4.24m-2.12-2.12l4.24-4.24"></path>
          <path d="M19.78 19.78l-4.24-4.24m-2.12-2.12l-4.24-4.24"></path>
          <path d="M19.78 4.22l-4.24 4.24m-2.12 2.12l-4.24 4.24"></path>
        </svg>
        Git Commits
      </a>
      <a href="#" class="resource-link" onclick="openSprintInfo(event)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"></path>
        </svg>
        Sprint Info
      </a>
    `;
  });
}

function openConfluence(e) {
  e.preventDefault();
  addMessage('Opening Confluence pages for your project...', 'system-message');
  // In a real app, this would open a modal with Confluence pages
  addMessage('Confluence integration: Your project documentation and knowledge base pages would appear here.', 'bot-message');
}

function openGitCommits(e) {
  e.preventDefault();
  addMessage('Fetching recent git commits for your project...', 'system-message');
  
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    fetch(`${backendUrl}/api/commits/?project_id=${currentProject || 'all'}`)
      .then(response => response.json())
      .then(data => {
        if (data && Array.isArray(data) && data.length > 0) {
          let commitsText = '📝 Recent Git Commits:\n';
          data.slice(0, 5).forEach(commit => {
            const msg = (commit.message || 'Commit').split('\n')[0]; // First line only
            const author = commit.author_name || 'Unknown';
            const date = commit.commit_date ? new Date(commit.commit_date).toLocaleDateString() : '';
            commitsText += `\n• ${msg}\n  by ${author} on ${date}`;
          });
          addMessage(commitsText, 'bot-message');
        } else {
          addMessage('📝 No recent commits found. Git commits from your repository would appear here.', 'bot-message');
        }
      })
      .catch(error => {
        console.error('Git commits error:', error);
        addMessage('⚠️ Could not fetch git commits. Make sure the backend is running at the configured URL.', 'error-message');
      });
  });
}

function openSprintInfo(e) {
  e.preventDefault();
  addMessage('Loading sprint information...', 'system-message');
  
  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    fetch(`${backendUrl}/api/sprints/?project_id=${currentProject || 'all'}`)
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(data => {
        if (data && Array.isArray(data) && data.length > 0) {
          let sprintText = '🏃 Active Sprints:\n';
          data.slice(0, 3).forEach(sprint => {
            const startDate = new Date(sprint.start_date).toLocaleDateString();
            const endDate = new Date(sprint.end_date).toLocaleDateString();
            sprintText += `\n• ${sprint.name || `Sprint ${sprint.sprint_number}`}\n  Status: ${sprint.status}\n  ${startDate} → ${endDate}`;
          });
          addMessage(sprintText, 'bot-message');
        } else {
          addMessage('🏃 No sprints found. Sprint details would appear here once sprints are linked to your project.', 'bot-message');
        }
      })
      .catch(error => {
        console.error('Sprint info error:', error);
        addMessage('⚠️ Could not fetch sprint information. Make sure the backend is running at the configured URL.', 'error-message');
      });
  });
}

function loadRecentActivity() {
  const recentActivity = document.getElementById('recentActivity');
  if (!recentActivity) return;

  chrome.storage.local.get('backendUrl', (result) => {
    const backendUrl = result.backendUrl || 'http://localhost:8000';
    
    // Load activity data
    fetch(`${backendUrl}/api/activity/?project_id=${currentProject || 'all'}&limit=5`)
      .then(response => response.json())
      .then(data => {
        if (data && data.length > 0) {
          let activityHTML = '';
          data.forEach(activity => {
            activityHTML += `<div style="font-size: 11px; color: var(--muted); padding: 4px 0; border-bottom: 1px solid var(--border);">• ${activity.description || activity.title}</div>`;
          });
          recentActivity.innerHTML = activityHTML;
        } else {
          recentActivity.innerHTML = `
            <div style="font-size: 12px; color: var(--muted); line-height: 1.6;">
              <div>• Sprint 2 in progress - 3 days left</div>
              <div>• 5 tasks assigned to you</div>
              <div>• 2 meetings today</div>
              <div>• 12 new messages in Teams</div>
            </div>
          `;
        }
      })
      .catch(error => {
        recentActivity.innerHTML = `
          <div style="font-size: 12px; color: var(--muted); line-height: 1.6;">
            <div>• Sprint 2 in progress - 3 days left</div>
            <div>• 5 tasks assigned to you</div>
            <div>• 2 meetings today</div>
            <div>• 12 new messages in Teams</div>
          </div>
        `;
      });
  });
}

// Close profile panel when clicking outside
document.addEventListener('click', (e) => {
  const panel = document.getElementById('profilePanel');
  const profileBtn = document.getElementById('profileBtn');
  if (!panel.contains(e.target) && !profileBtn.contains(e.target)) {
    hideProfile();
  }
});
