FROM python:3.10-slim

# 替换 apt 源为腾讯云镜像 (兼容新旧两种 Debian 源格式)
RUN if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list; \
    fi && \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi

# 安装系统依赖 (ffmpeg 是 Whisper 必需的)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安装 Python 依赖 (利用 Docker 缓存，使用腾讯云 PyPI 镜像)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.cloud.tencent.com/pypi/simple/ \
    --trusted-host mirrors.cloud.tencent.com

# 复制应用代码
COPY . .

# 创建临时音频目录
RUN mkdir -p /tmp/temp_audio

EXPOSE 8000

# 启动 FastAPI 服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
