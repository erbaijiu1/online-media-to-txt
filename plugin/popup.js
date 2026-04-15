document.addEventListener('DOMContentLoaded', async () => {
  // === DOM 元素 ===
  const pathInput = document.getElementById('joplinPath');
  const titleInput = document.getElementById('noteTitle');
  const urlListDiv = document.getElementById('urlList');
  const sendBtn = document.getElementById('sendBtn');
  const statusDiv = document.getElementById('status');
  const backendUrlInput = document.getElementById('backendUrl');
  const settingsToggle = document.getElementById('settingsToggle');
  const settingsPanel = document.getElementById('settingsPanel');

  let selectedUrl = '';
  let pollingTimer = null;
  let currentTabId = null;

  const STORAGE_UI_KEY = 'popupStateByTab';
  const STORAGE_TASK_KEY = 'activeTasksByTab';

  function storageGet(keys) {
    return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
  }

  function storageSet(obj) {
    return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
  }

  async function saveUiState(extra = {}) {
    if (currentTabId === null) return;
    const res = await storageGet([STORAGE_UI_KEY]);
    const all = res[STORAGE_UI_KEY] || {};
    const prev = all[currentTabId] || {};

    all[currentTabId] = {
      ...prev,
      title: titleInput.value.trim(),
      selectedUrl,
      ...extra
    };

    await storageSet({ [STORAGE_UI_KEY]: all });
  }

  async function saveTaskState(taskState) {
    if (currentTabId === null) return;
    const res = await storageGet([STORAGE_TASK_KEY]);
    const all = res[STORAGE_TASK_KEY] || {};
    all[currentTabId] = taskState;
    await storageSet({ [STORAGE_TASK_KEY]: all });
  }

  async function loadUiState() {
    if (currentTabId === null) return null;
    const res = await storageGet([STORAGE_UI_KEY]);
    const all = res[STORAGE_UI_KEY] || {};
    return all[currentTabId] || null;
  }

  async function loadTaskState() {
    if (currentTabId === null) return null;
    const res = await storageGet([STORAGE_TASK_KEY]);
    const all = res[STORAGE_TASK_KEY] || {};
    return all[currentTabId] || null;
  }

  // === 初始化 ===

  // 1. 获取当前 tab 信息，用标题作为默认笔记名
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab.id;
  titleInput.value = tab.title.replace(/[\/\\?%*:|"<>]/g, '-');

  // 2. 从 storage 加载上次的配置
  chrome.storage.local.get(['lastPath', 'backendUrl'], (res) => {
    if (res.lastPath) pathInput.value = res.lastPath;
    if (res.backendUrl) backendUrlInput.value = res.backendUrl;
  });

  // 3. 恢复当前 tab 的上次状态（避免切页后弹窗内容丢失）
  const savedUiState = await loadUiState();
  if (savedUiState) {
    if (savedUiState.title) titleInput.value = savedUiState.title;
    if (savedUiState.selectedUrl) selectedUrl = savedUiState.selectedUrl;
    if (savedUiState.lastStatusText && savedUiState.lastStatusType) {
      setStatus(savedUiState.lastStatusText, savedUiState.lastStatusType);
    }
  }

  // 4. 设置面板开关
  settingsToggle.addEventListener('click', () => {
    settingsPanel.classList.toggle('open');
  });

  // 5. 后端地址变更自动保存
  backendUrlInput.addEventListener('change', () => {
    chrome.storage.local.set({ backendUrl: backendUrlInput.value.trim() });
  });

  titleInput.addEventListener('change', () => {
    saveUiState();
  });

  // === MP3 扫描 (网络嗅探 + DOM 扫描合并) ===
  const allUrls = new Set();

  // 方式1: 从 background.js 获取网络请求中嗅探到的音频 (核心方式)
  chrome.runtime.sendMessage({ action: 'getAudioUrls', tabId: tab.id }, (bgResponse) => {
    if (bgResponse && bgResponse.urls) {
      bgResponse.urls.forEach(url => allUrls.add(url));
    }

    // 方式2: 从 content.js 获取 DOM 中的音频
    chrome.tabs.sendMessage(tab.id, { action: 'scanAudio' }, (domResponse) => {
      if (!chrome.runtime.lastError && domResponse && domResponse.urls) {
        domResponse.urls.forEach(url => allUrls.add(url));
      }

      // 方式3: 如果前两种都没结果，直接注入脚本扫描 DOM
      if (allUrls.size === 0) {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const exts = ['.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac'];
            const urls = new Set();
            document.querySelectorAll('a[href], audio[src], source[src], video[src], embed[src]').forEach(el => {
              const url = el.href || el.src;
              if (!url) return;
              const lower = url.toLowerCase().split('?')[0];
              if (exts.some(ext => lower.endsWith(ext))) urls.add(url);
            });
            return Array.from(urls);
          }
        }, (results) => {
          if (results && results[0] && results[0].result) {
            results[0].result.forEach(url => allUrls.add(url));
          }
          renderUrls(Array.from(allUrls));
        });
      } else {
        renderUrls(Array.from(allUrls));
      }
    });
  });

  // === 渲染 URL 列表 ===
  function renderUrls(urls) {
    if (!urls || urls.length === 0) {
      if (savedUiState && Array.isArray(savedUiState.urls) && savedUiState.urls.length > 0) {
        renderUrls(savedUiState.urls);
        return;
      }
      urlListDiv.innerHTML = '<div class="url-empty">未发现音频链接</div>';
      return;
    }

    urlListDiv.innerHTML = urls.map((url, i) => {
      // 从 URL 中提取文件名作为显示
      const filename = decodeURIComponent(url.split('/').pop().split('?')[0]);
      return `<div class="url-item" data-url="${url}" title="${url}">${i + 1}. ${filename}</div>`;
    }).join('');

    // 点击选中逻辑
    document.querySelectorAll('.url-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('.url-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
        selectedUrl = item.getAttribute('data-url');
        saveUiState({ urls });
      });
    });

    // 默认选中第一个
    const first = urlListDiv.querySelector('.url-item');
    if (first) {
      first.classList.add('selected');
      if (!selectedUrl || !urls.includes(selectedUrl)) {
        selectedUrl = first.getAttribute('data-url');
      } else {
        const selectedEl = urlListDiv.querySelector(`.url-item[data-url="${CSS.escape(selectedUrl)}"]`);
        if (selectedEl) {
          first.classList.remove('selected');
          selectedEl.classList.add('selected');
        }
      }
    }

    saveUiState({ urls });
  }

  // === 状态显示 ===
  function setStatus(text, type = 'info') {
    statusDiv.textContent = text;
    statusDiv.className = type;
    saveUiState({ lastStatusText: text, lastStatusType: type });
  }

  // === 发送任务 ===
  sendBtn.addEventListener('click', async () => {
    if (!selectedUrl) {
      setStatus('❌ 请先选择一个音频链接', 'error');
      return;
    }
    if (!titleInput.value.trim()) {
      setStatus('❌ 请填写笔记标题', 'error');
      return;
    }
    if (!pathInput.value.trim()) {
      setStatus('❌ 请填写 Joplin 路径', 'error');
      return;
    }

    const backendBase = backendUrlInput.value.trim().replace(/\/$/, '');
    const payload = {
      url: selectedUrl,
      alias: titleInput.value.trim(),
      joplin_path: pathInput.value.trim()
    };

    // 保存路径偏好
    chrome.storage.local.set({ lastPath: pathInput.value.trim() });

    try {
      sendBtn.disabled = true;
      setStatus('⏳ 正在提交任务...', 'progress');

      const response = await fetch(`${backendBase}/api/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || '请求失败');
      }

      const result = await response.json();
      setStatus(`✅ 任务已提交！ID: ${result.task_id}`, 'success');

      await saveTaskState({
        taskId: result.task_id,
        backendBase,
        status: 'pending'
      });

      // 开始轮询任务状态
      startPolling(backendBase, result.task_id);

    } catch (err) {
      setStatus(`❌ ${err.message || '连接后端失败，请确认服务已启动'}`, 'error');
      sendBtn.disabled = false;
    }
  });

  // === 轮询任务状态 ===
  function startPolling(backendBase, taskId) {
    if (pollingTimer) clearInterval(pollingTimer);

    sendBtn.disabled = true;

    pollingTimer = setInterval(async () => {
      try {
        const res = await fetch(`${backendBase}/api/tasks/${taskId}`);
        if (!res.ok) return;

        const task = await res.json();

        // 根据状态更新 UI
        switch (task.status) {
          case 'pending':
            setStatus(`⏳ [${taskId}] 排队中...`, 'progress');
            saveTaskState({ taskId, backendBase, status: 'pending' });
            break;
          case 'downloading':
            setStatus(`⬇️ [${taskId}] ${task.progress}`, 'progress');
            saveTaskState({ taskId, backendBase, status: 'downloading' });
            break;
          case 'transcribing':
            setStatus(`🎙️ [${taskId}] ${task.progress}`, 'progress');
            saveTaskState({ taskId, backendBase, status: 'transcribing' });
            break;
          case 'llm_processing':
            setStatus(`🧠 [${taskId}] ${task.progress}`, 'progress');
            saveTaskState({ taskId, backendBase, status: 'llm_processing' });
            break;
          case 'syncing_joplin':
            setStatus(`📝 [${taskId}] ${task.progress}`, 'progress');
            saveTaskState({ taskId, backendBase, status: 'syncing_joplin' });
            break;
          case 'completed':
            setStatus(`🎉 [${taskId}] ${task.progress}`, 'success');
            clearInterval(pollingTimer);
            sendBtn.disabled = false;
            saveTaskState({ taskId, backendBase, status: 'completed' });
            break;
          case 'failed':
            setStatus(`❌ [${taskId}] 失败: ${task.error || '未知错误'}`, 'error');
            clearInterval(pollingTimer);
            sendBtn.disabled = false;
            saveTaskState({ taskId, backendBase, status: 'failed' });
            break;
        }
      } catch (e) {
        // 网络错误，继续轮询
      }
    }, 3000); // 每 3 秒轮询一次
  }

  // 6. 弹窗重新打开时恢复上个任务并继续轮询
  const savedTaskState = await loadTaskState();
  if (savedTaskState && savedTaskState.taskId && savedTaskState.backendBase) {
    const isTerminal = savedTaskState.status === 'completed' || savedTaskState.status === 'failed';
    if (!isTerminal) {
      setStatus(`⏳ [${savedTaskState.taskId}] 正在恢复任务状态...`, 'progress');
      startPolling(savedTaskState.backendBase, savedTaskState.taskId);
    }
  }
});
