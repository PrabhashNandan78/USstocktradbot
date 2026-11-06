/**
 * Service Worker Background Script for MV3 Extension
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log('[Antigravity Bridge] Extension installed successfully.');
});

// Relay messages between popup and active TradingView tab if required
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') {
    chrome.tabs.query({ url: '*://*.tradingview.com/*' }, (tabs) => {
      sendResponse({
        tv_tabs_open: tabs.length,
        tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title }))
      });
    });
    return true;
  }
});
