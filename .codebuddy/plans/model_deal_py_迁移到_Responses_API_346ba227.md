---
name: model_deal.py 迁移到 Responses API
overview: 将 `server/app/tools/model_deal.py` 的模型调用从旧的 `chat.completions.create`（流式）迁移到官方示例的 `responses.create`（非流式），并切换到 MaaS 专属端点，同时保持 `chat_with_model` 的生成器返回协议不变，使下游调用方无需改动。
todos:
  - id: migrate-responses-api
    content: 改写 `chat_with_model` 为 `client.responses.create` 非流式调用并解析 `response.output`
    status: completed
  - id: update-baseurl-thinking
    content: 更新默认 `base_url` 为新 MaaS 端点，扩展 `enable_thinking` 支持 qwen3.8-flash
    status: completed
    dependencies:
      - migrate-responses-api
  - id: verify-callers
    content: 核对 `run_chat_demo` 与下游 converter/get_txt 调用兼容性并运行本地演示验证
    status: completed
    dependencies:
      - update-baseurl-thinking
---

## 产品概述
将现有大模型调用从旧版 `chat.completions` 流式接口迁移到官方示例的 `responses.create` 非流式接口，并切换到阿里云百炼 MaaS 专属端点，同时保持对外调用协议与返回结果不变。

## 核心功能
- 使用 `client.responses.create` 非流式调用模型，`input` 传入消息列表
- 解析 `response.output`，按 `item.type` 区分 `reasoning`（思考过程）与 `message`（最终回答）
- 将思考内容与最终回答仍按 `thinking` / `answer_start` / `answer` 事件顺序 yield，保证下游无需改动
- 默认 `base_url` 更新为新 MaaS 端点
- `enable_thinking` 扩展支持 `qwen3.8-flash`，同时保留 `qwen-plus` / `qwen-max` 的原有判断


## 技术栈
- 语言：Python 3
- SDK：openai 1.82.0（`server/requirements.txt` 已固定，支持 `responses.create` Responses API）
- 修改文件：`server/app/tools/model_deal.py`

## 实现方案
保持 `chat_with_model` 作为生成器的返回协议不变，内部实现从流式 `chat.completions.create` 改为非流式 `responses.create`，一次性解析 `response.output` 后再按原事件顺序 yield。`run_chat_demo`、`process_text_with_prompt` 及下游 `converter.py`、`get_txt_form_online_mp3.py` 调用均无需改动。

关键决策：
- 采用非流式：与官方示例一致，实现更简单；思考与回答一次性返回，通过生成器协议向下游顺序回放。
- 移除已无意义的 `stream` 参数：全项目无外部调用传入该参数，避免保留无效分支。
- 保留 `messages` / `model_name` / `api_key` / `base_url` 参数，仅改 `base_url` 默认值。

## 实现细节
- `base_url` 默认值改为 `https://llm-fihg3x9syo13k841.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
- `enable_thinking` 判断：`model_name` 以 `qwen-plus`、`qwen-max` 或 `qwen3` 开头时设置 `{"enable_thinking": True}`
- 解析时防御性处理：`reasoning` 的 `item.summary` 可能包含多个对象，逐个拼接 `summary.text`；`message` 的 `item.content` 可能包含多个片段，逐个拼接 `text`
- 保持 yield 顺序：先 `("thinking", 文本)`，再 `("answer_start", None)`，最后 `("answer", 文本)`
- API Key 仍从 `DASHSCOPE_API_KEY` 环境变量读取，与现有逻辑一致

## 目录结构
```
server/app/tools/model_deal.py  # [MODIFY] 迁移到 responses API，保持生成器返回协议与下游兼容
```

## 关键代码结构
```python
def chat_with_model(
    messages, model_name="qwen3.8-flash", api_key=None,
    base_url="https://llm-fihg3x9syo13k841.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
) -> Generator[Union[tuple, str], None, None]:
    client = OpenAI(api_key=api_key or os.getenv("DASHSCOPE_API_KEY"), base_url=base_url.strip())
    extra_body = {}
    if model_name.startswith("qwen-plus") or model_name.startswith("qwen-max") or model_name.startswith("qwen3"):
        extra_body = {"enable_thinking": True}
    response = client.responses.create(
        model=model_name,
        input=messages,
        **({"extra_body": extra_body} if extra_body else {})
    )
    for item in response.output:
        if item.type == "reasoning":
            thinking_text = "".join(s.text for s in item.summary)
            yield ("thinking", thinking_text)
        elif item.type == "message":
            answer_text = "".join(c.text for c in item.content if getattr(c, "text", None))
            yield ("answer_start", None)
            yield ("answer", answer_text)
```

