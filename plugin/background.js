/**
 * Background Service Worker - 监听网络请求中的音频文件
 */

// 存储每个 tab 发现的音频 URL
const tabAudioUrls = {};

const AUDIO_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac', '.wma'];
const AUDIO_MIME_TYPES = ['audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/m4a', 'audio/wav', 'audio/ogg', 'audio/flac', 'audio/aac'];

/**
 * 判断 URL 是否为音频文件
 */
function isAudioUrl(url) {
  if (!url) return false;
  const lower = url.toLowerCase().split('?')[0].split('#')[0];
  return AUDIO_EXTENSIONS.some(ext => lower.endsWith(ext));
}

/**
 * 判断 MIME 类型是否为音频
 */
function isAudioMime(type) {
  if (!type) return false;
  return AUDIO_MIME_TYPES.some(mime => type.toLowerCase().includes(mime));
}

/**
 * 监听所有网络请求，筛选音频文件
 */
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (details.tabId < 0) return; // 忽略非 tab 请求

    const url = details.url;
    if (isAudioUrl(url)) {
      if (!tabAudioUrls[details.tabId]) {
        tabAudioUrls[details.tabId] = new Set();
      }
      tabAudioUrls[details.tabId].add(url);
      console.log(`🎵 [Tab ${details.tabId}] 发现音频: ${url}`);
    }
  },
  { urls: ["<all_urls>"] },
  []
);

/**
 * 监听带 Content-Type 的响应头，捕获没有音频扩展名但 MIME 类型是音频的请求
 */
chrome.webRequest.onResponseStarted.addListener(
  (details) => {
    if (details.tabId < 0) return;

    const contentType = details.responseHeaders?.find(
      h => h.name.toLowerCase() === 'content-type'
    )?.value;

    if (isAudioMime(contentType)) {
      if (!tabAudioUrls[details.tabId]) {
        tabAudioUrls[details.tabId] = new Set();
      }
      tabAudioUrls[details.tabId].add(details.url);
      console.log(`🎵 [Tab ${details.tabId}] 通过 MIME 发现音频: ${details.url}`);
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

/**
 * Tab 关闭时清理数据
 */
chrome.tabs.onRemoved.addListener((tabId) => {
  delete tabAudioUrls[tabId];
});

/**
 * 仅在刷新当前页面时清理该 tab 的缓存状态
 */
chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0) return;
  if (details.transitionType !== 'reload') return;

  const tabId = details.tabId;
  delete tabAudioUrls[tabId];

  chrome.storage.local.get(['popupStateByTab', 'activeTasksByTab'], (res) => {
    const popupStateByTab = res.popupStateByTab || {};
    const activeTasksByTab = res.activeTasksByTab || {};

    if (Object.prototype.hasOwnProperty.call(popupStateByTab, tabId)) {
      delete popupStateByTab[tabId];
    }
    if (Object.prototype.hasOwnProperty.call(activeTasksByTab, tabId)) {
      delete activeTasksByTab[tabId];
    }

    chrome.storage.local.set({ popupStateByTab, activeTasksByTab });
  });
});

/**
 * 响应来自 popup 的消息
 */
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getAudioUrls') {
    const urls = tabAudioUrls[request.tabId];
    sendResponse({ urls: urls ? Array.from(urls) : [] });
  }
  return true;
});
