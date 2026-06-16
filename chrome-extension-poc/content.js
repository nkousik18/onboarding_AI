// ── Content Script ───────────────────────────────────────
// This script runs on all web pages

// Add a floating button to pages if needed
function injectFloatingButton() {
  if (localStorage.getItem('solutionAI_disableFloatingButton') === 'true') return;
  // Prevent duplicate injection on SPA navigation or re-runs
  if (document.getElementById('solution-ai-floating-btn')) return;
  
  // Create floating button
  const btn = document.createElement('button');
  btn.id = 'solution-ai-floating-btn';
  btn.title = 'Ask LightHouse';
  btn.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1e8fff, #0b7dd8);
    border: none;
    color: white;
    cursor: pointer;
    z-index: 10000;
    box-shadow: 0 4px 12px rgba(30, 143, 255, 0.4);
    transition: all 0.3s;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  `;
  
  // SVG Lighthouse Icon
  btn.innerHTML = `
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="white" stroke-width="1.5">
      <!-- Lighthouse tower -->
      <path d="M16 2 L22 8 L22 26 L10 26 L10 8 Z"/>
      <!-- Top light section -->
      <circle cx="16" cy="5" r="3" fill="white"/>
      <!-- Light beams -->
      <path d="M13 7 L8 2" stroke="white" stroke-width="1"/>
      <path d="M19 7 L24 2" stroke="white" stroke-width="1"/>
      <!-- Door -->
      <rect x="14" y="14" width="4" height="6" fill="none" stroke="white" stroke-width="1"/>
    </svg>
  `;
  
  // Hover effect
  btn.addEventListener('mouseenter', () => {
    btn.style.transform = 'scale(1.1)';
    btn.style.boxShadow = '0 8px 20px rgba(30, 143, 255, 0.5)';
  });
  
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = 'scale(1)';
    btn.style.boxShadow = '0 4px 12px rgba(30, 143, 255, 0.4)';
  });
  
  btn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'toggleSidePanel' }, (response) => {
      if (chrome.runtime.lastError) {
        console.warn('LightHouse side panel toggle failed:', chrome.runtime.lastError.message);
        return;
      }
      if (response?.state === 'expanded') {
        btn.title = 'Collapse LightHouse';
      } else {
        btn.title = 'Ask LightHouse';
      }
    });
  });
  
  document.body.appendChild(btn);
}

// Inject on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectFloatingButton);
} else {
  injectFloatingButton();
}

// Listen for messages from background
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'queryFromContext') {
    // Forward context query to popup
    sendResponse({ success: true });
  }
});
