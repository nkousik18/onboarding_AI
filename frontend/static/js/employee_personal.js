/**
 * Employee Personal Page — JavaScript
 * Handles daily tasks, skills, calendar, and Jira ticket integration
 */

// State
let currentDate = new Date();
let employeeData = null;
let tasksData = [];
let skillsData = [];
let selectedTask = null;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
  if (!sessionStorage.getItem('isLoggedIn')) {
    window.location.href = 'login.html';
    return;
  }

  initializePage();
  loadEmployeeData();
  loadTasks();
  loadSkills();
  initializeCalendar();
  setupEventListeners();
  updateDate();
});

function initializePage() {
  const userEmail = sessionStorage.getItem('userEmail') || 'Employee';
  const userName = sessionStorage.getItem('userName') || userEmail.split('@')[0];
  
  document.getElementById('sidebarUserName').textContent = userName;
  const avatar = document.getElementById('userAvatar');
  const initials = userName.split(' ').map(n => n[0]).join('').toUpperCase();
  avatar.textContent = initials || '—';
}

function setupEventListeners() {
  // Sidebar toggle
  document.getElementById('sidebarToggle').addEventListener('click', function() {
    document.getElementById('sidebar').classList.toggle('collapsed');
    document.getElementById('sidebarOverlay').classList.toggle('visible');
  });

  // Sidebar overlay
  document.getElementById('sidebarOverlay').addEventListener('click', function() {
    document.getElementById('sidebar').classList.remove('collapsed');
    document.getElementById('sidebarOverlay').classList.remove('visible');
  });

  // Calendar navigation
  document.getElementById('prevMonth').addEventListener('click', previousMonth);
  document.getElementById('nextMonth').addEventListener('click', nextMonth);

  // Task modal close on overlay click
  document.getElementById('taskModal').addEventListener('click', function(e) {
    if (e.target === this) {
      this.classList.remove('active');
    }
  });
}

// ════════════════════════════════════════════════════════════════════════════════
// DATA LOADING
// ════════════════════════════════════════════════════════════════════════════════

async function loadEmployeeData() {
  try {
    const userEmail = sessionStorage.getItem('userEmail');
    const response = await fetch(`/api/employees/?email=${encodeURIComponent(userEmail)}`);
    
    if (!response.ok) throw new Error('Failed to load employee data');
    
    const data = await response.json();
    employeeData = data[0] || {};
  } catch (error) {
    console.error('Error loading employee data:', error);
  }
}

async function loadSkills() {
  try {
    const userEmail = sessionStorage.getItem('userEmail');
    
    // Fetch all projects
    const projectsRes = await fetch('/api/projects/');
    const projectsData = await projectsRes.json();
    const projects = Array.isArray(projectsData) ? projectsData : (projectsData.results || []);
    
    if (!projects.length) {
      skillsData = generateMockSkills();
      renderSkills();
      return;
    }
    
    // Fetch skills from ALL projects
    let allSkills = {};
    for (const project of projects) {
      try {
        const response = await fetch(`/api/projects/${project.id}/employee-skills/?email=${encodeURIComponent(userEmail)}`);
        if (response.ok) {
          const projectSkills = await response.json();
          const skillsArray = Array.isArray(projectSkills) ? projectSkills : (projectSkills.results || []);
          skillsArray.forEach(skill => {
            if (!allSkills[skill.name]) {
              allSkills[skill.name] = { name: skill.name, level: 0, projects: [] };
            }
            allSkills[skill.name].level = Math.max(allSkills[skill.name].level, skill.level || 3);
            allSkills[skill.name].projects.push(project.name);
          });
        }
      } catch (e) {
        console.warn(`Failed to load skills from project ${project.id}:`, e);
      }
    }
    
    if (Object.keys(allSkills).length === 0) {
      skillsData = generateMockSkills();
    } else {
      skillsData = Object.values(allSkills);
    }
    
    renderSkills();
  } catch (error) {
    console.error('Error loading skills:', error);
    skillsData = generateMockSkills();
    renderSkills();
  }
}

function generateMockSkills() {
  return [
    { name: 'Backend Development', level: 5, projects: ['Employee Onboarding Portal', 'Payment Processing System'] },
    { name: 'Payment Processing', level: 4, projects: ['Payment Processing System'] },
    { name: 'API Design', level: 4, projects: ['Employee Onboarding Portal'] },
    { name: 'Database Design', level: 4, projects: ['Both Projects'] },
    { name: 'JavaScript', level: 5, projects: ['Employee Onboarding Portal'] },
    { name: 'Python', level: 4, projects: ['Payment Processing System'] },
    { name: 'System Architecture', level: 3, projects: ['Employee Onboarding Portal', 'Payment Processing System'] },
    { name: 'Security & Encryption', level: 4, projects: ['Payment Processing System'] }
  ];
}

async function loadTasks() {
  try {
    const userEmail = sessionStorage.getItem('userEmail');
    
    // Fetch all projects first
    const projectsRes = await fetch('/api/projects/');
    const projectsData = await projectsRes.json();
    const projects = Array.isArray(projectsData) ? projectsData : (projectsData.results || []);
    
    if (!projects.length) {
      tasksData = generateMockTasks();
      renderTasks();
      renderMeetings();
      return;
    }
    
    // Fetch tasks from ALL projects
    let allTasks = [];
    for (const project of projects) {
      try {
        const response = await fetch(`/api/projects/${project.id}/tasks/?assignee=${encodeURIComponent(userEmail)}`);
        if (response.ok) {
          const projectTasks = await response.json();
          const tasksArray = Array.isArray(projectTasks) ? projectTasks : (projectTasks.results || []);
          // Add project context to each task
          allTasks = allTasks.concat(tasksArray.map(t => ({ ...t, projectName: project.name, projectId: project.id })));
        }
      } catch (e) {
        console.warn(`Failed to load tasks from project ${project.id}:`, e);
      }
    }
    
    if (allTasks.length === 0) {
      // Fall back to mock if no tasks found
      tasksData = generateMockTasks();
    } else {
      tasksData = allTasks;
    }
    
    renderTasks();
    renderMeetings();
  } catch (error) {
    console.error('Error loading tasks:', error);
    tasksData = generateMockTasks();
    renderTasks();
  }
}

function generateMockTasks() {
  // Generate realistic mock data from both projects
  return [
    // Employee Onboarding Portal tasks
    {
      id: 'PROJ-1243',
      title: 'Implement authentication flow',
      description: 'Add JWT token support and session management',
      status: 'In Progress',
      priority: 'High',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Employee Onboarding Portal'
    },
    {
      id: 'PROJ-1256',
      title: 'Review PR for API endpoints',
      description: 'Code review for the new REST API endpoints',
      status: 'To Do',
      priority: 'Medium',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Employee Onboarding Portal'
    },
    {
      id: 'PROJ-1289',
      title: 'Update database schema',
      description: 'Add new fields to user and project tables',
      status: 'In Progress',
      priority: 'High',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Employee Onboarding Portal'
    },
    // Payment Processing System tasks
    {
      id: 'PAY-201',
      summary: 'Implement payment processing logic',
      description: 'Core transaction processing engine',
      status: 'In Progress',
      priority: 'Critical',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Payment Processing System'
    },
    {
      id: 'PAY-202',
      summary: 'Add error handling and retries',
      description: 'Handle failed transactions gracefully',
      status: 'In Progress',
      priority: 'High',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Payment Processing System'
    },
    {
      id: 'PAY-203',
      summary: 'Webhook implementation',
      description: 'Handle payment notifications',
      status: 'To Do',
      priority: 'Medium',
      dueDate: new Date().toISOString().split('T')[0],
      assignee: 'You',
      completed: false,
      projectName: 'Payment Processing System'
    },
  ];
}

// ════════════════════════════════════════════════════════════════════════════════
// RENDERING
// ════════════════════════════════════════════════════════════════════════════════

// Project color scheme
const PROJECT_COLORS = {
  'Employee Onboarding Portal': { 
    name: 'Onboarding',
    hex: '#1e8fff', 
    rgb: 'rgb(30, 143, 255)',
    light: 'rgba(30, 143, 255, 0.12)',
    gradient: 'linear-gradient(135deg, #1e8fff 0%, #0066cc 100%)'
  },
  'Payment Processing System': { 
    name: 'Payment',
    hex: '#00d48a', 
    rgb: 'rgb(0, 212, 138)',
    light: 'rgba(0, 212, 138, 0.12)',
    gradient: 'linear-gradient(135deg, #00d48a 0%, #00a366 100%)'
  },
  'Analytics Dashboard': { 
    name: 'Analytics',
    hex: '#ff9f43', 
    rgb: 'rgb(255, 159, 67)',
    light: 'rgba(255, 159, 67, 0.12)',
    gradient: 'linear-gradient(135deg, #ff9f43 0%, #ff7f1a 100%)'
  },
  'Mobile App': { 
    name: 'Mobile',
    hex: '#a78bfa', 
    rgb: 'rgb(167, 139, 250)',
    light: 'rgba(167, 139, 250, 0.12)',
    gradient: 'linear-gradient(135deg, #a78bfa 0%, #8b5cf6 100%)'
  },
};

function getProjectColor(projectName) {
  return PROJECT_COLORS[projectName] || { 
    name: projectName,
    hex: '#888888', 
    rgb: 'rgb(136, 136, 136)',
    light: 'rgba(136, 136, 136, 0.12)',
    gradient: 'linear-gradient(135deg, #888888 0%, #555555 100%)'
  };
}

function renderTasks() {
  const container = document.getElementById('tasksContainer');
  
  if (tasksData.length === 0) {
    container.innerHTML = '<p class="ep-placeholder">No tasks assigned. Great job! 🎉</p>';
    return;
  }

  // Group tasks by project
  const groupedTasks = {};
  tasksData.forEach((task, index) => {
    const projectName = task.projectName || 'Unassigned';
    if (!groupedTasks[projectName]) {
      groupedTasks[projectName] = [];
    }
    groupedTasks[projectName].push({ task, index });
  });

  // Render grouped tasks with collapsible sections
  let html = '';
  
  Object.entries(groupedTasks).forEach(([projectName, tasks]) => {
    const color = getProjectColor(projectName);
    const projectId = tasks[0].task.projectId || projectName.toLowerCase().replace(/\s+/g, '_');
    
    html += `
      <div class="ep-project-group" data-project="${projectId}">
        <div class="ep-project-header" onclick="toggleProjectGroup(this)">
          <div class="ep-project-color" style="background-color: ${color.hex}"></div>
          <div class="ep-project-title">
            <h3>${escapeHtml(projectName)}</h3>
            <span class="ep-project-count">${tasks.length} task${tasks.length !== 1 ? 's' : ''}</span>
          </div>
          <div class="ep-project-toggle">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </div>
        </div>
        <div class="ep-project-tasks" style="display: block;">
          ${tasks.map(({ task, index }) => `
            <div class="ep-task ${task.completed ? 'completed' : ''} ${task.priority.toLowerCase()}-priority" 
                 style="border-left-color: ${color.hex}; background: ${task.completed ? 'transparent' : color.light}"
                 onclick="openTaskModal(${index})">
              <div class="ep-task-checkbox" onclick="toggleTaskComplete(event, ${index})"></div>
              <div class="ep-task-content">
                <h4 class="ep-task-title">${escapeHtml(task.title || task.summary || task.id)}</h4>
                <div class="ep-task-meta">
                  <span class="ep-task-id">${escapeHtml(task.id || task.issue_key)}</span>
                  <span class="ep-task-priority ${(task.priority || 'Medium').toLowerCase()}">${task.priority || 'Medium'}</span>
                  <span>${task.status}</span>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
  
  // Restore collapsed states from localStorage
  Object.keys(groupedTasks).forEach((projectName, i) => {
    const projectId = (groupedTasks[projectName][0].task.projectId || projectName.toLowerCase().replace(/\s+/g, '_'));
    const isCollapsed = localStorage.getItem(`ep-project-collapsed-${projectId}`);
    if (isCollapsed === 'true') {
      const group = container.querySelector(`[data-project="${projectId}"]`);
      if (group) {
        const tasksDiv = group.querySelector('.ep-project-tasks');
        tasksDiv.style.display = 'none';
        group.querySelector('.ep-project-header').classList.add('collapsed');
      }
    }
  });
}

function toggleProjectGroup(headerEl) {
  const group = headerEl.closest('.ep-project-group');
  const tasksDiv = group.querySelector('.ep-project-tasks');
  const isCollapsed = tasksDiv.style.display === 'none';
  
  tasksDiv.style.display = isCollapsed ? 'block' : 'none';
  headerEl.classList.toggle('collapsed');
  
  const projectId = group.dataset.project;
  localStorage.setItem(`ep-project-collapsed-${projectId}`, !isCollapsed);
}

function renderSkills() {
  const container = document.getElementById('skillsContainer');
  
  if (skillsData.length === 0) {
    container.innerHTML = '<p style="color: var(--muted); font-size: 13px;">Loading your skills...</p>';
    return;
  }

  container.innerHTML = skillsData.map(skill => `
    <div class="ep-skill">
      <div class="ep-skill-name">${skill.name}</div>
      ${skill.projects ? `<div class="ep-skill-projects" style="font-size: 11px; color: var(--muted); margin-top: 4px;">${skill.projects.join(', ')}</div>` : ''}
    </div>
  `).join('');
}

function renderMeetings() {
  const container = document.getElementById('meetingsContainer');
  
  // Generate mock meetings for today
  const meetings = [
    { time: '09:30 AM', title: 'Sprint Planning' },
    { time: '02:00 PM', title: 'Code Review Session' },
    { time: '04:30 PM', title: '1-on-1 with Manager' }
  ];

  container.innerHTML = meetings.map(meeting => `
    <div class="ep-meeting">
      <div class="ep-meeting-time">${meeting.time}</div>
      <div class="ep-meeting-title">${meeting.title}</div>
    </div>
  `).join('');
}

function updateDate() {
  const options = { weekday: 'long', month: 'short', day: 'numeric' };
  const dateStr = currentDate.toLocaleDateString('en-US', options);
  document.getElementById('currentDate').textContent = dateStr;
}

// ════════════════════════════════════════════════════════════════════════════════
// CALENDAR
// ════════════════════════════════════════════════════════════════════════════════

function initializeCalendar() {
  renderCalendar();
}

function renderCalendar() {
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  
  // Update header
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];
  document.getElementById('monthYear').textContent = `${monthNames[month]} ${year}`;
  
  // Create calendar grid
  const grid = document.getElementById('calendarGrid');
  grid.innerHTML = '';
  
  // Add day headers
  const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  dayHeaders.forEach(day => {
    const header = document.createElement('div');
    header.className = 'cal-day-header';
    header.textContent = day;
    grid.appendChild(header);
  });
  
  // Get first day of month and number of days
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  
  // Add empty cells
  for (let i = 0; i < firstDay; i++) {
    const emptyDay = document.createElement('div');
    emptyDay.className = 'cal-day empty';
    grid.appendChild(emptyDay);
  }
  
  // Add day cells
  const today = new Date();
  for (let day = 1; day <= daysInMonth; day++) {
    const dayCell = document.createElement('div');
    dayCell.className = 'cal-day';
    dayCell.textContent = day;
    
    const cellDate = new Date(year, month, day);
    if (cellDate.toDateString() === today.toDateString()) {
      dayCell.classList.add('today');
    }
    
    // Add event indicator if tasks exist
    if (hasTasksOnDate(cellDate)) {
      dayCell.classList.add('has-event');
    }
    
    dayCell.addEventListener('click', () => selectDate(cellDate));
    grid.appendChild(dayCell);
  }
}

function hasTasksOnDate(date) {
  const dateStr = date.toISOString().split('T')[0];
  return tasksData.some(task => task.dueDate === dateStr);
}

function selectDate(date) {
  currentDate = date;
  renderCalendar();
  updateDate();
}

function previousMonth() {
  currentDate.setMonth(currentDate.getMonth() - 1);
  renderCalendar();
}

function nextMonth() {
  currentDate.setMonth(currentDate.getMonth() + 1);
  renderCalendar();
}

// ════════════════════════════════════════════════════════════════════════════════
// TASK ACTIONS
// ════════════════════════════════════════════════════════════════════════════════

function openTaskModal(index) {
  const task = tasksData[index];
  selectedTask = { index, data: task };
  
  document.getElementById('modalTaskTitle').textContent = task.title;
  document.getElementById('modalTaskId').textContent = task.id;
  document.getElementById('modalTaskStatus').innerHTML = `<span style="color: #1e8fff;">${task.status}</span>`;
  document.getElementById('modalTaskPriority').innerHTML = getPriorityBadge(task.priority);
  document.getElementById('modalTaskDesc').textContent = task.description;
  document.getElementById('taskComment').value = '';
  
  const modal = document.getElementById('taskModal');
  modal.classList.add('active');
  
  document.getElementById('completeTaskBtn').onclick = () => completeTask(index);
}

function toggleTaskComplete(event, index) {
  event.stopPropagation();
  tasksData[index].completed = !tasksData[index].completed;
  renderTasks();
  
  if (tasksData[index].completed) {
    showNotification(`Task ${tasksData[index].id} marked as complete!`);
  }
}

async function completeTask(index) {
  const task = tasksData[index];
  const comment = document.getElementById('taskComment').value.trim();
  
  try {
    // Update task in backend
    await fetch(`/api/tasks/${task.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status: 'Done',
        comment: comment,
        completedBy: sessionStorage.getItem('userEmail'),
        completedAt: new Date().toISOString()
      })
    });
    
    // Update Jira ticket
    await updateJiraTicket(task.id, comment);
    
    tasksData[index].completed = true;
    tasksData[index].status = 'Done';
    
    document.getElementById('taskModal').classList.remove('active');
    renderTasks();
    
    showNotification(`Jira ticket ${task.id} updated and closed!`);
  } catch (error) {
    console.error('Error completing task:', error);
    showNotification('Error updating task. Please try again.');
  }
}

async function updateJiraTicket(taskId, comment) {
  try {
    // This would call your backend endpoint that integrates with Jira
    await fetch(`/api/jira/tickets/${taskId}/complete/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        comment: comment || 'Task completed via LightHouse',
        status: 'Done'
      })
    });
  } catch (error) {
    console.warn('Could not update Jira ticket:', error);
    // Continue anyway - local task is marked complete
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════════════════════════

function getPriorityBadge(priority) {
  const colors = {
    High: '#ff4d6a',
    Medium: '#FFA500',
    Low: '#00d48a'
  };
  return `<span style="color: ${colors[priority]}; font-weight: 600;">${priority}</span>`;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showNotification(message) {
  // Simple notification - could be enhanced with a toast system
  console.log('Notification:', message);
  
  // Optional: Show a brief toast notification
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #00d48a;
    color: #000;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 500;
    z-index: 2000;
    animation: slideIn 0.3s ease-out;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
