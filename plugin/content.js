/**
 * Content Script - MP3 嗅探器
 * 深度扫描页面中所有可能的音频链接
 */
(function () {
  'use strict';

  const AUDIO_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac'];

  /**
   * 判断 URL 是否为音频文件
   */
  function isAudioUrl(url) {
    if (!url) return false;
    const lower = url.toLowerCase().split('?')[0]; // 忽略查询参数
    return AUDIO_EXTENSIONS.some(ext => lower.endsWith(ext));
  }

  /**
   * 扫描页面 DOM 中的音频链接
   */
  function scanDomForAudio() {
    const urls = new Set();

    // <a> 标签
    document.querySelectorAll('a[href]').forEach(el => {
      if (isAudioUrl(el.href)) urls.add(el.href);
    });

    // <audio> 和 <video> 标签的 src
    document.querySelectorAll('audio[src], video[src]').forEach(el => {
      if (isAudioUrl(el.src)) urls.add(el.src);
    });

    // <source> 标签
    document.querySelectorAll('source[src]').forEach(el => {
      if (isAudioUrl(el.src)) urls.add(el.src);
    });

    // <embed> 和 <object> 标签
    document.querySelectorAll('embed[src], object[data]').forEach(el => {
      const src = el.src || el.data;
      if (isAudioUrl(src)) urls.add(src);
    });

    // iframe 内的 audio (同源的才能访问)
    document.querySelectorAll('iframe').forEach(iframe => {
      try {
        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
        iframeDoc.querySelectorAll('audio[src], source[src], a[href]').forEach(el => {
          const url = el.src || el.href;
          if (isAudioUrl(url)) urls.add(url);
        });
      } catch (e) {
        // 跨域 iframe，无法访问
      }
    });

    return Array.from(urls);
  }

  /**
   * 监听来自 popup 的消息请求
   */
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'scanAudio') {
      const audioUrls = scanDomForAudio();
      sendResponse({ urls: audioUrls });
    }
    return true; // 保持消息通道开放
  });
})();
