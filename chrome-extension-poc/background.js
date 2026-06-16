// ── Background Service Worker ────────────────────────────
// This handles persistent background tasks and context menu

chrome.runtime.onInstalled.addListener(() => {
  console.log('LightHouse extension installed');

  // Enable the side panel globally and let Chrome open it natively on toolbar icon click
  chrome.sidePanel.setOptions({ enabled: true, path: 'popup.html' });
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

  // Create context menu items
  chrome.contextMenus.create({
    id: 'ask-lighthouse-about-text',
    title: 'Ask LightHouse about this text',
    contexts: ['selection'],
  });
  
  chrome.contextMenus.create({
    id: 'ask-lighthouse-about-page',
    title: 'Ask LightHouse about this page',
    contexts: ['page'],
  });
});

const panelOpenByTab = {};

function setPanelOpenState(tabId, isOpen) {
  panelOpenByTab[tabId] = isOpen;
}

function getPanelOpenState(tabId) {
  return Boolean(panelOpenByTab[tabId]);
}


// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let query = '';
  
  if (info.menuItemId === 'ask-lighthouse-about-text') {
    query = info.selectionText;
  } else if (info.menuItemId === 'ask-lighthouse-about-page') {
    const pageTitle = tab.title || 'this page';
    query = `What can you tell me about: "${pageTitle}"`;
  }
  
  if (query) {
    // Open side panel and send message
    await chrome.sidePanel.setOptions({ tabId: tab.id, enabled: true, path: 'popup.html' });
    await chrome.sidePanel.open({ tabId: tab.id });
    setPanelOpenState(tab.id, true);
    
    // Store query for the popup to retrieve
    chrome.storage.session.set({
      pendingQuery: query,
    });
    
    // Send message to popup if it's already open
    chrome.runtime.sendMessage({
      action: 'queryFromContext',
      query: query,
    }).catch(() => {
      // Popup not open, query stored in session storage
    });
  }
});

// Handle messages from popup or content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'sidePanelClosed') {
    // Sent by popup.js when the side panel unloads (user pressed Chrome's X)
    if (sender.tab?.id) {
      setPanelOpenState(sender.tab.id, false);
    }
    return false;
  }

  if (request.action === 'getBackendUrl') {
    chrome.storage.local.get('backendUrl', (result) => {
      sendResponse({
        url: result.backendUrl || 'http://localhost:8000',
      });
    });
    return true; // Keep channel open for async response
  }
  
  if (request.action === 'openSidePanelWithQuery') {
    // Open side panel and store query
    if (sender.tab?.id) {
      chrome.sidePanel.setOptions({ tabId: sender.tab.id, enabled: true, path: 'popup.html' });
      chrome.sidePanel.open({ tabId: sender.tab.id });
      chrome.storage.session.set({
        pendingQuery: request.query,
      });
      setPanelOpenState(sender.tab.id, true);
    }
    sendResponse({ success: true });
    return true;
  }

  if (request.action === 'setSidePanelState') {
    if (!sender.tab?.id) {
      sendResponse({ success: false, error: 'No tab context found.' });
      return true;
    }

    const tabId = sender.tab.id;
    const shouldOpen = Boolean(request.shouldOpen);

    if (!shouldOpen) {
      // Call synchronously to preserve user gesture context
      try {
        chrome.sidePanel.setOptions({ tabId, enabled: false });
        setPanelOpenState(tabId, false);
        sendResponse({ success: true, state: 'collapsed' });
      } catch (error) {
        console.error('setSidePanelState error (close):', error);
        sendResponse({ success: false, error: String(error) });
      }
      return true;
    }

    // Call synchronously (do not await/promises) so the call remains in the
    // immediate user gesture handling stack.
    try {
      chrome.sidePanel.setOptions({ tabId, enabled: true, path: 'popup.html' });
      chrome.sidePanel.open({ tabId });
      setPanelOpenState(tabId, true);
      sendResponse({ success: true, state: 'expanded' });
    } catch (error) {
      console.error('setSidePanelState error:', error);
      sendResponse({ success: false, error: String(error) });
    }

    return true;
  }

  if (request.action === 'toggleSidePanel') {
    if (!sender.tab?.id) {
      sendResponse({ success: false, error: 'No tab context found.' });
      return true;
    }

    const tabId = sender.tab.id;
    const isOpen = getPanelOpenState(tabId);

    try {
      if (isOpen) {
        chrome.sidePanel.setOptions({ tabId, enabled: false });
        setPanelOpenState(tabId, false);
        sendResponse({ success: true, state: 'collapsed' });
      } else {
        chrome.sidePanel.setOptions({ tabId, enabled: true, path: 'popup.html' });
        chrome.sidePanel.open({ tabId });
        setPanelOpenState(tabId, true);
        sendResponse({ success: true, state: 'expanded' });
      }
    } catch (error) {
      console.error('toggleSidePanel error:', error);
      sendResponse({ success: false, error: String(error) });
    }

    return true;
  }
});
