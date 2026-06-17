import os
import urllib.request
import sys

MODEL_FILES = [
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt"
]

BASE_URL = "https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/"
TARGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hf_cache", "whisper-small")

def download_progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    percent = min(100, int(downloaded * 100 / total_size)) if total_size > 0 else 0
    sys.stdout.write(f"\rDownloading... {percent}% ({downloaded / (1024*1024):.2f}MB / {total_size / (1024*1024):.2f}MB)")
    sys.stdout.flush()

def main():
    print("🚀 开始下载 Whisper 'small' 模型文件...")
    print(f"目标保存目录: {TARGET_DIR}")
    os.makedirs(TARGET_DIR, exist_ok=True)

    for file_name in MODEL_FILES:
        url = BASE_URL + file_name
        target_path = os.path.join(TARGET_DIR, file_name)
        print(f"\n📥 正在下载: {file_name}")
        
        try:
            # 使用 urllib.request.urlretrieve 并附带进度回调
            urllib.request.urlretrieve(url, target_path, download_progress)
            print(f"\n✅ 下载完成: {file_name}")
        except Exception as e:
            print(f"\n❌ 下载失败: {file_name}, 错误信息: {e}")
            print("提示: 请检查网络连接，或尝试在浏览器中直接打开以下链接下载并放入目标目录:")
            print(url)
            sys.exit(1)

    print("\n🎉 所有模型文件下载成功！")
    print(f"请确保您的 .env 文件中已配置如下项:")
    print("---------------------------------")
    print("WHISPER_MODEL_SIZE=/app/hf_cache/whisper-small")
    print("---------------------------------")

if __name__ == "__main__":
    main()
