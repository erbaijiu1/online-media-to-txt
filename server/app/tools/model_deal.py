from openai import OpenAI
import httpx
import os
from typing import Any, Dict, Generator, Iterable, List, Optional, Union

from app.config import get_settings


def _event_error_message(event: Any) -> str:
    """Extract a useful error message from Responses API terminal events."""
    response = getattr(event, "response", None)
    error = getattr(response, "error", None) or getattr(event, "error", None)
    message = getattr(error, "message", None) or getattr(event, "message", None)
    code = getattr(error, "code", None) or getattr(event, "code", None)
    if code and message:
        return f"{code}: {message}"
    return message or code or "未知错误"


def _iter_response_events(events: Iterable[Any]) -> Generator[tuple, None, None]:
    """Yield text deltas and accept output only after response.completed."""
    completed = False
    answer_started = False
    received_text = False

    for event in events:
        event_type = getattr(event, "type", "")

        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "") or ""
            if not delta:
                continue
            if not answer_started:
                yield ("answer_start", None)
                answer_started = True
            received_text = True
            yield ("answer", delta)
        elif event_type == "response.completed":
            completed = True
        elif event_type == "response.incomplete":
            response = getattr(event, "response", None)
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) or "未知原因"
            raise RuntimeError(f"模型响应不完整: {reason}")
        elif event_type == "response.failed":
            raise RuntimeError(f"模型响应失败: {_event_error_message(event)}")
        elif event_type == "error":
            raise RuntimeError(f"模型流式请求错误: {_event_error_message(event)}")

    if not completed:
        raise RuntimeError("模型流式响应意外结束，未收到 response.completed")
    if not received_text:
        raise RuntimeError("模型响应已完成，但没有返回正文")


def chat_with_model(
        messages: List[Dict[str, str]],
        model_name: str = "qwen3.8-max-0902",
        api_key: Optional[str] = None,
        base_url: str = "https://llm-fihg3x9syo13k841.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
) -> Generator[Union[tuple, str], None, None]:
    """
    通过 Responses API 流式调用模型，并返回最终正文增量

    参数:
        messages: 消息列表，格式为[{"role": "user", "content": "消息内容"}]
        model_name: 模型名称
        api_key: API密钥，如果为None则从环境变量DASHSCOPE_API_KEY获取
        base_url: API基础URL

    返回:
        生成器，逐步返回 answer_start 和 answer 事件
    """
    settings = get_settings()

    # 流式读取按“连续无数据时间”计时；限制重试，避免请求静默等待几十分钟。
    client = OpenAI(
        api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
        base_url=base_url.strip(),
        timeout=httpx.Timeout(
            connect=settings.LLM_CONNECT_TIMEOUT_SEC,
            read=settings.LLM_READ_TIMEOUT_SEC,
            write=60.0,
            pool=10.0,
        ),
        max_retries=settings.LLM_MAX_RETRIES,
    )

    # 文本整理不需要推理过程；显式关闭，避免模型默认开启思考而增加延迟。
    stream = client.responses.create(
        model=model_name,
        input=messages,
        stream=True,
        extra_body={"enable_thinking": False},
    )

    yield from _iter_response_events(stream)


def run_chat_demo(
        prompt: str,
        model_name: str = "qwen3.8-max-0902"
):
    """
    运行聊天演示，直观展示思考过程和最终回复

    参数:
        prompt: 用户输入的提示
        model_name: 要使用的模型名称
    """
    messages = [{"role": "user", "content": prompt}]

    print(f"\n{'=' * 20} 与模型对话演示 (模型: {model_name}) {'=' * 20}")
    print(f"用户: {prompt}\n")

    thinking_lines = []
    full_answer = []

    for event_type, content in chat_with_model(messages, model_name=model_name):
        if event_type == "thinking":
            thinking_lines.append(content)
            print(content, end="", flush=True)
        elif event_type == "answer_start":
            print("\n" + "=" * 20 + " 最终回复 " + "=" * 20)
        elif event_type == "answer":
            full_answer.append(content)
            print(content, end="", flush=True)

    print("\n" + "=" * 50)
    print(f"\n思考过程总结: {''.join(thinking_lines)}")
    print(f"最终回复: {''.join(full_answer)}")
    print("=" * 50 + "\n")

    return ''.join(full_answer)

def process_text_with_prompt(need_deal_txt:  str, model_name: str = "qwen3.8-max-0902"):
    if not need_deal_txt:
        print("没有待处理的文本")
        return

    prompt_txt = """
    这是我的语音转文字内容。请帮我整理格式，意思不要做修改。

    要求：
    1. 保持原文内容，只调整格式和段落，通过上下文理解，有错误的词语需要纠正。
    2. 可以合并成一行的短句合并成一行，可以组成一段的内容合并成一段
    3. [根据需要添加：帮我加上合适的标点符号]
    4. 输出统一使用简体中文；如果原文含有繁体中文，请转换成简体中文。
    5. 保持原文的口语风格和表达特点，尽量不调整语义，错别字或者词语可以调整。
    6. 由于是语音转文字，所以，一些由语音转换来的词需要整体通过语境判断是不是对的，错误的纠正过来。
    7. 在输出原文后，在最后，输出一个对原文内容的总结。总结不需要添加观点，严格遵守原文的意思来进行总结。如果是提问与回答，就分列出提问和回答对应总结。

    内容如下：
    %need_deal_txt%
    """
    prompt_txt = prompt_txt.replace("%need_deal_txt%", need_deal_txt)

    return run_chat_demo(prompt_txt, model_name)

# 使用示例
if __name__ == "__main__":
    # 示例1: 使用默认模型（支持思考过程的模型）
    run_chat_demo("请解释量子计算的基本原理", "qwen3.8-max-0902")

    # 示例2: 使用需要额外参数的模型
    run_chat_demo("请解释相对论的基本原理", "qwen-plus-2025-07-28")

    # 示例3: 使用另一个需要额外参数的模型
    run_chat_demo("如何制作一杯好喝的咖啡?", "qwen-max")

    # 示例4: 自定义处理
    """
    messages = [{"role": "user", "content": "1+1等于几？"}]
    for event_type, content in chat_with_model(messages, model_name="qwen-plus-2025-07-28"):
        if event_type == "thinking":
            print(f"[思考] {content}", end="", flush=True)
        elif event_type == "answer_start":
            print("\n[开始回复]")
        elif event_type == "answer":
            print(f"[回复] {content}", end="", flush=True)
    """
