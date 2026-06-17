# Online Media to TXT

在线音频转文字工具 —— Chrome 插件嗅探网页 MP3，后端自动转录并同步到 Joplin 笔记。

## 架构

```
Chrome 插件 ──POST /api/convert──▶ FastAPI 后端 (Docker)
                                      │
                                      ├── 1. 下载 MP3
                                      ├── 2. Whisper 语音转文字
                                      ├── 3. LLM 整理格式 (通义千问)
                                      └── 4. 写入 Joplin 笔记
```

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key 和 Joplin Token
```

**需要的环境变量：**
- `DASHSCOPE_API_KEY`: 通义千问 API Key
- `JOPLIN_TOKEN`: Joplin 桌面客户端 → 选项 → Web Clipper → Token

### 2. 启动后端服务

```bash
docker compose up -d --build
```

服务将在 `http://localhost:8000` 启动。

验证服务状态：
```bash
curl http://localhost:8000/api/health
```

### 3. 安装 Chrome 插件

1. 打开 Chrome → `chrome://extensions/`
2. 开启右上角「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `plugin/` 目录

### 4. 使用

1. 打开包含音频的网页
2. 点击插件图标 🎵
3. 插件会自动嗅探页面中的 MP3 链接
4. 选择要转换的音频，修改标题和 Joplin 路径
5. 点击「发送到后端处理」
6. 等待处理完成，笔记会自动出现在 Joplin 中

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/convert` | 提交音频转换任务 |
| GET | `/api/tasks/{id}` | 查询转换任务状态 |
| GET | `/api/health` | 健康检查 |
| POST | `/api/xiaoe/upload-curl` | 上传小鹅通 cURL，后台自动抓取帖子并同步 Joplin |

### 提交任务示例

### 提交抓取小鹅通任务示例 (支持断点续传)

```bash
curl -X POST http://localhost:8000/api/xiaoe/upload-curl \
  -F "file=@curl_content.txt" \
  -F "joplin_path=Project/stock/不惑少年/帖子" \
  -F "start_page=1" \
  -F "limit=0"
```
**参数说明：**
- `file`: (必填) 从浏览器里复制出的 `Copy as cURL (bash)` 文本文件。
- `joplin_path`: (必填) 将帖子同步到 Joplin 的目标笔记本路径。
- `start_page`: (可选) 起始页码，用于报错断开时接着之前的页数继续抓取，默认为 `1`。
- `limit`: (可选) 本次抓取的最大页数限制，传 `0` 则表示不限制或读取 `.env` 中设置的默认值。


## 项目结构

```
├── plugin/                  # Chrome 插件
│   ├── manifest.json
│   ├── content.js           # MP3 嗅探
│   ├── popup.html / .js     # 弹窗 UI
│   └── icons/               # 图标
├── server/
│   ├── app/                 # FastAPI 应用
│   │   ├── main.py          # 入口
│   │   ├── config.py        # 配置
│   │   ├── api/routes.py    # API 路由
│   │   ├── services/        # 业务逻辑
│   │   └── tools/           # 已验证的工具模块
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## 注意事项

- Joplin 桌面客户端必须运行中，且 Web Clipper 服务已启用（默认端口 41184）
- Docker 容器通过 `host.docker.internal` 访问宿主机的 Joplin
- Whisper 模型首次启动时会自动下载，需要网络
