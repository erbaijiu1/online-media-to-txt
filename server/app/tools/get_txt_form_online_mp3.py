import os
import requests
from faster_whisper import WhisperModel
from app.tools.model_deal import process_text_with_prompt
from app.tools.joplinUtil import JoplinToolbox

# --- 配置区 ---
LLM_API_KEY = os.getenv("LLM_API_KEY", "your-api-key")
LLM_BASE_URL = "https://api.openai.com/v1"
MODEL_NAME = "gpt-4o"

# Joplin 配置
JOPLIN_TOKEN = os.getenv("JOPLIN_TOKEN", "你的_TOKEN")
JOPLIN_TARGET_PATH = "Project/stock/不惑少年/直播"  # 严格匹配该路径
JOPLIN_TAGS = []

# 下载保存路径
DOWNLOAD_DIR = "./temp_audio"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 全局初始化 Whisper 模型 (避免在循环内重复加载)
print("正在加载 Whisper 模型...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")


def download_file(url, alias):
    """将在线 MP3 下载到本地"""
    local_path = os.path.join(DOWNLOAD_DIR, f"{alias}.mp3")
    if os.path.exists(local_path):
        print(f"⏩ 文件已存在，跳过下载: {alias}")
        return local_path

    print(f"正在从网络下载: {alias}...")
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"✅ 下载完成: {local_path}")
    return local_path


def transcribe_audio(file_path):
    """提取文字"""
    print(f"正在识别文字: {file_path}...")
    segments, _ = whisper_model.transcribe(file_path, beam_size=1, vad_filter=True)
    full_text = "\n".join([s.text for s in segments])
    return full_text


def process_online_list(tasks, target_path):
    """
    主逻辑：
    1. 第一阶段：全量下载
    2. 第二阶段：识别 + LLM加工 + Joplin同步
    """
    # 初始化 Joplin 工具
    try:
        joplin = JoplinToolbox(JOPLIN_TOKEN)
    except Exception as e:
        print(f"❌ Joplin 工具初始化失败: {e}")
        return

    # --- 第一阶段：全部下载 ---
    print(f"🚀 [阶段 1] 批量下载 (共 {len(tasks)} 个任务)...")
    for task in tasks:
        try:
            task['local_path'] = download_file(task['url'], task['alias'])
        except Exception as e:
            print(f"❌ 下载 {task['alias']} 失败: {e}")
            task['local_path'] = None

    print("\n" + "=" * 40 + "\n")

    # --- 第二阶段：识别、加工并同步 ---
    print(f"🚀 [阶段 2] 处理并同步至 Joplin 路径: {target_path}")
    for task in tasks:
        if not task.get('local_path'):
            continue

        local_file = task['local_path']
        try:
            # 1. Whisper 转文字
            raw_text = transcribe_audio(local_file)
            if not raw_text.strip():
                print(f"⚠️ {task['alias']} 识别内容为空，跳过。")
                continue

            # 2. 大模型提炼
            print(f"🧠 正在调用 LLM 加工文本: {task['alias']}...")
            final_content = process_text_with_prompt(raw_text)

            # 3. 同步到 Joplin (严格路径模式)
            # 在正文末尾附带原始链接，方便回溯
            note_body = f"{final_content}\n\n---\n> **原始音频地址:** {task['url']}"

            sync_result = joplin.create_note(
                title=task['alias'],
                body=note_body,
                notebook_path=target_path,
                tags=JOPLIN_TAGS
            )

            # 4. 如果同步成功，则清理本地文件和做本地备份
            if sync_result:
                # 本地保存一份 txt 备份
                with open(f"{task['alias']}_final.txt", "w", encoding="utf-8") as f:
                    f.write(final_content)

                # 删除临时 mp3
                if os.path.exists(local_file):
                    os.remove(local_file)
                    print(f"🗑️ 已清理临时文件: {local_file}")
            else:
                print(f"⚠️ 由于同步失败，保留本地音频文件以备重试: {local_file}")

        except Exception as e:
            print(f"❌ 任务 {task['alias']} 处理出错: {e}")


if __name__ == "__main__":
    # 在线音频列表
    host_list = [
        "https://wechatapppro-1252524126.file.myqcloud.com/appfvn6my9u7697/audio_compressed/1775699541_3boqwgmnqtg1xd.mp3",
        "https://wechatapppro-1252524126.file.myqcloud.com/appfvn6my9u7697/audio_compressed/1775699611_n1h90dmnqtnwtd.mp3",
        "https://wechatapppro-1252524126.file.myqcloud.com/appfvn6my9u7697/audio_compressed/1775699708_j8z1wnmnqtpyh8.mp3",
        "https://wechatapppro-1252524126.file.myqcloud.com/appfvn6my9u7697/audio_compressed/1775699789_x1wnyimnqts44n.mp3"
    ]

    name_pre = "《地缘冲突（如波斯事件）对市场的真实影响-260408》"
    my_tasks = []
    for i, host in enumerate(host_list):
        my_tasks.append({
            "url": host,
            "alias": f"{name_pre}_{i + 1}"
        })

    # 执行主流程
    process_online_list(my_tasks, JOPLIN_TARGET_PATH)