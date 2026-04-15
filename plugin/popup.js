document.addEventListener('DOMContentLoaded', async () => {
  const pathInput = document.getElementById('joplinPath');
  const titleInput = document.getElementById('noteTitle');
  const urlListDiv = document.getElementById('urlList');
  const status = document.getElementById('status');

  // 1. 获取当前页面标题并填充
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  titleInput.value = tab.title.replace(/[\/\\?%*:|"<>]/g, '-');

  // 2. 从 Storage 加载上次使用的路径
  chrome.storage.local.get(['lastPath'], (res) => {
    if (res.lastPath) pathInput.value = res.lastPath;
  });

  // 3. 执行 content.js 嗅探 MP3
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const links = Array.from(document.querySelectorAll('a, audio, source'))
        .map(el => el.href || el.src)
        .filter(url => url && url.includes('.mp3'));
      return [...new Set(links)]; // 去重
    }
  }, (results) => {
    const urls = results[0].result;
    if (urls && urls.length > 0) {
      urlListDiv.innerHTML = urls.map(url => `<div class="url-item" data-url="${url}">${url}</div>`).join('');
      // 点击 URL 自动选中
      document.querySelectorAll('.url-item').forEach(item => {
        item.addEventListener('click', () => {
          document.querySelectorAll('.url-item').forEach(i => i.style.background = 'none');
          item.style.background = '#e7f3ff';
          item.id = 'selected-url';
        });
      });
    } else {
      urlListDiv.innerHTML = "未发现 MP3 链接，请手动点击猫抓复制。";
    }
  });

  // 4. 点击发送
  document.getElementById('sendBtn').addEventListener('click', async () => {
    const selectedItem = document.getElementById('selected-url');
    const mp3Url = selectedItem ? selectedItem.getAttribute('data-url') : "";

    if (!mp3Url) {
      status.innerText = "❌ 请先点击选择一个 MP3 链接";
      return;
    }

    const payload = {
      url: mp3Url,
      alias: titleInput.value,
      joplin_path: pathInput.value
    };

    // 保存路径偏好
    chrome.storage.local.set({ lastPath: pathInput.value });

    try {
      status.innerText = "⏳ 正在发送中...";
      const response = await fetch('http://localhost:5000/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const result = await response.json();
      status.innerText = "✅ 后端已接收任务！";
    } catch (err) {
      status.innerText = "❌ 连接后端失败，请确认服务已启动。";
      console.error(err);
    }
  });
});
