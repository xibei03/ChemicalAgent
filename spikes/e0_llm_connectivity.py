"""E0（0A 任务 4，用户答复 D1 之后补做）：从这台机器发出最小的 LLM 调用并得到回复。

用户答复 D1：LLM 统一用阿里云百炼的 Qwen API（OpenAI 兼容接口），密钥只从环境变量 DASHSCOPE_API_KEY
读取，不硬编码。三个模型：主 qwen3.8-max、快速 qwen3.8-flash、备用 qwen3.7-plus，不增加别的模型。

要回答的问题：
  Q1 环境变量里有没有密钥？（只打印“已设置”和长度，绝不打印内容、不写进日志）
  Q2 这台机器能不能访问百炼的接口？国内站和国际站哪个能通？
  Q3 三个模型名各自能不能调通？延迟多少？返回的 model 字段是什么？
  Q4 （--capabilities）主模型支不支持 JSON 输出（response_format）和函数调用（tools）？
     阶段 2A 的 LLM 客户端怎么封装结构化输出，取决于这一条。

只用标准库的 urllib，不引入 openai 之类的新依赖（CLAUDE.md 不变量 7）。

用法：python spikes/e0_llm_connectivity.py [--tag 名字] [--capabilities]
可选环境变量：DASHSCOPE_BASE_URL（覆盖默认的国内站地址）
输出：spikes/out/e0_llm_connectivity_<tag>.txt
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from _common import Log, use_utf8

use_utf8()

API_KEY_VARIABLE = "DASHSCOPE_API_KEY"
BASE_URL_VARIABLE = "DASHSCOPE_BASE_URL"
BASE_URLS = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
MODELS = (("主模型", "qwen3.8-max"), ("快速模型", "qwen3.8-flash"), ("备用模型", "qwen3.7-plus"))
TIMEOUT_S = 90.0
ERROR_TEXT_LIMIT = 600
PING = [{"role": "user", "content": "请只回复两个字母：OK"}]


def scrub(text: str, api_key: str) -> str:
    """把可能回显的密钥片段抹掉，错误文字才能写进日志。"""
    for piece in {api_key, api_key[:8], api_key[-6:]}:
        if len(piece) >= 6:
            text = text.replace(piece, "***")
    return text


def chat(base_url: str, api_key: str, model: str, messages: list, **extra) -> dict:
    """调一次 /chat/completions，返回 {status, seconds, payload 或 error}。"""
    body = {"model": model, "messages": messages, "max_tokens": 64, "temperature": 0, **extra}
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"status": response.status, "seconds": time.time() - start, "payload": payload}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        error = scrub(text, api_key)[:ERROR_TEXT_LIMIT]
        return {"status": exc.code, "seconds": time.time() - start, "error": error}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        message = scrub(str(exc), api_key)[:ERROR_TEXT_LIMIT]
        return {"status": None, "seconds": time.time() - start, "error": f"连接失败 {message}"}


def summarize(result: dict) -> str:
    """一次调用的一行摘要：状态、用时、回复文字、用量或错误。"""
    seconds = f"{result['seconds']:.2f} 秒"
    if "payload" not in result:
        return f"状态 {result['status']}，{seconds}，错误 {result['error']}"
    payload = result["payload"]
    choice = payload.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = (message.get("content") or "").strip()
    usage = payload.get("usage", {})
    extras = []
    if message.get("tool_calls"):
        extras.append(f"tool_calls={message['tool_calls']}")
    if message.get("reasoning_content"):
        extras.append("含 reasoning_content")
    return (
        f"状态 {result['status']}，{seconds}，返回 model={payload.get('model')!r}，"
        f"回复 {content[:80]!r}，finish_reason={choice.get('finish_reason')!r}，"
        f"用量 {usage.get('prompt_tokens')}+{usage.get('completion_tokens')} tokens"
        + ("，" + "，".join(extras) if extras else "")
    )


def find_working_base_url(log: Log, api_key: str) -> str | None:
    """Q2：依次试国内站和国际站，用主模型发一次最小调用，第一个返回 200 的就是可用的。"""
    log.say("== Q2 接口地址 ==")
    candidates = [os.environ[BASE_URL_VARIABLE]] if os.environ.get(BASE_URL_VARIABLE) else []
    candidates += [url for url in BASE_URLS if url not in candidates]
    model = MODELS[0][1]
    for base_url in candidates:
        result = chat(base_url, api_key, model, PING)
        log.say(f"  {base_url} 用 {model}：{summarize(result)}")
        if result["status"] == 200:
            return base_url
    return None


def test_models(log: Log, base_url: str, api_key: str) -> bool:
    """Q3：三个模型各发一次最小调用。"""
    log.say("== Q3 三个模型 ==")
    passed = True
    for role, model in MODELS:
        result = chat(base_url, api_key, model, PING)
        log.say(f"  {role} {model}：{summarize(result)}")
        passed = passed and result["status"] == 200
    return passed


def test_capabilities(log: Log, base_url: str, api_key: str) -> None:
    """Q4：JSON 输出和函数调用，只测主模型。"""
    log.say("== Q4 主模型的结构化输出和函数调用 ==")
    model = MODELS[0][1]
    json_messages = [
        {"role": "system", "content": "你只输出 JSON，不要任何别的文字。"},
        {
            "role": "user",
            "content": '输出一个 JSON 对象：answer 是 1 加 1 的结果，unit 是字符串 "none"。',
        },
    ]
    result = chat(base_url, api_key, model, json_messages, response_format={"type": "json_object"})
    log.say(f"  response_format=json_object：{summarize(result)}")
    if "payload" in result:
        content = result["payload"]["choices"][0]["message"].get("content") or ""
        try:
            log.say(f"      解析为 JSON：{json.loads(content)!r}")
        except json.JSONDecodeError as exc:
            log.say(f"      回复不是合法 JSON：{exc}")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "add",
                "description": "把两个数相加",
                "parameters": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            },
        }
    ]
    tool_messages = [{"role": "user", "content": "请调用工具 add 计算 1 加 1。"}]
    result = chat(base_url, api_key, model, tool_messages, tools=tools)
    log.say(f"  tools=[add]：{summarize(result)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args()
    log = Log(f"e0_llm_connectivity_{args.tag}")
    api_key = os.environ.get(API_KEY_VARIABLE, "")
    log.say("== Q1 环境变量 ==")
    if not api_key:
        log.say(f"  {API_KEY_VARIABLE} 未设置：这个进程的环境里没有密钥，没有发出任何请求")
        return 2
    log.say(f"  {API_KEY_VARIABLE} 已设置，长度 {len(api_key)}（不打印内容）")
    base_url = find_working_base_url(log, api_key)
    if base_url is None:
        log.say("== E0 未通过：国内站和国际站都没有返回 200 ==")
        return 1
    log.say(f"  可用的接口地址：{base_url}")
    passed = test_models(log, base_url, api_key)
    if args.capabilities:
        test_capabilities(log, base_url, api_key)
    log.say(
        f"== E0 {'通过' if passed else '未通过'}：三个模型{'都' if passed else '不全'}返回了 200 =="
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
