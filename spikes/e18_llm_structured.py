"""E18（2A）：2A 的 LLM 客户端要用到、E0 没有测的能力。

E0 只确认了三个模型能调通、主模型的 json_object 和 tools 可用。2A 的客户端要用 openai SDK 连百炼的
OpenAI 兼容接口，并且要求：温度 0、供应商原生的结构化输出、明确的超时、有限的网络重试。
这些没有验证过，所以先在这里测，结论写进台账，客户端按结论写。

要回答的问题（用 2A 的真实输出模型 SelectionDraft 的 JSON Schema 和一段真实的选型提示）：
  Q1 temperature=0 被接受吗？打开思考和关闭思考两种情况。
  Q2 response_format=json_schema（strict）被接受吗？返回的内容能通过 SelectionDraft 的校验吗？
  Q3 response_format=json_object（Schema 写在提示里）能不能通过校验？这是 Q2 不行时的退路。
  Q4 extra_body={"enable_thinking": False} 被接受吗？对用时和 token 数有多大影响？
  Q5 同一个请求在温度 0 下重复 3 次，结果一样吗？（评测的可重复性）
  Q6 SDK 的 timeout 和 max_retries 怎么表现？总用时是不是 timeout 的 (1 + 重试次数) 倍？
  Q7 错误的密钥和不存在的模型名，SDK 抛什么异常、状态码是什么？（客户端要把它们转成 E_LLM）

用法：python spikes/e18_llm_structured.py [--tag 名字] [--ask-key]
  --ask-key：环境变量里没有密钥时在终端提示输入（不回显，只留在这个进程的内存里）。
可选环境变量：DASHSCOPE_BASE_URL。
输出：spikes/out/e18_llm_structured_<tag>.txt（不含密钥；回复全文只留前 2000 个字符）
"""

import argparse
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import openai
import yaml
from _common import Log, use_utf8
from e0_llm_connectivity import API_KEY_VARIABLE, BASE_URL_VARIABLE, BASE_URLS, ask_for_key, scrub
from openai import OpenAI
from pydantic import ValidationError

from reactor_agent.spec.selection import SelectionDraft

use_utf8()

MODEL = "qwen3.8-max"
TIMEOUT_S = 90.0
REPEATS = 3
SHORT_TIMEOUT_S = 0.5
REPLY_LIMIT = 2000
CASE_FILE = Path(__file__).resolve().parents[1] / "evals" / "cases" / "L1-S3.yaml"
SYSTEM = (
    "你是化工过程建模助手。读用户的描述，抽取下面这些特征，并推荐一种反应器类型"
    "（conversion、equilibrium、gibbs、pfr、cstr 之一；不是反应过程的模拟请求时为 null）。"
    "特征取值为是时，evidence 必须是用户原文里的一句原话。"
    "特征：是否反应过程的模拟请求；用户点名的反应器；是否给出动力学参数；是否给出设备尺寸；"
    "设备形式（tubular、vessel、unspecified）；是否给出转化率、收率或选择性的数值（待求量不算）；"
    "反应是否已明确；是否黑箱类体系（气化、燃烧、裂解，或用户明说产物分布未知）；"
    "是否给出平衡常数；相态（gas、liquid、multiphase、unknown）；是否聚合反应。"
    "alternatives 里对每个没有推荐的类型写一句不选的原因。输出语言跟随用户。"
)


def case_text() -> str:
    return yaml.safe_load(CASE_FILE.read_text(encoding="utf-8"))["input"]


def strict_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "selection_draft",
            "strict": True,
            "schema": SelectionDraft.model_json_schema(),
        },
    }


def schema_in_prompt() -> str:
    schema = json.dumps(SelectionDraft.model_json_schema(), ensure_ascii=False)
    return f"{SYSTEM}\n只输出一个 JSON 对象，必须符合这个 JSON Schema：{schema}"


def validate(content: str) -> str:
    """回复能不能通过 SelectionDraft 的校验，返回一行说明。"""
    try:
        draft = SelectionDraft.model_validate_json(content)
    except ValidationError as error:
        first = error.errors()[0]
        return f"校验失败（共 {error.error_count()} 处，第一处 {first['loc']}：{first['msg']}）"
    return f"校验通过，推荐 {draft.recommended_type}，黑箱={draft.features.black_box_system.value}"


class Probe:
    """一次调用的结果：用时、用量、回复、错误。"""

    def __init__(self, log: Log, client: OpenAI) -> None:
        self.log = log
        self.client = client

    def call(self, label: str, system: str, **kwargs: object) -> str | None:
        """发一次请求，打印摘要，返回回复文字（失败是 None）。"""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": case_text()}]
        start = time.time()
        try:
            reply = self.client.chat.completions.create(model=MODEL, messages=messages, **kwargs)
        except openai.APIStatusError as error:
            body = scrub(str(error.body), self.client.api_key)[:300]
            self.log.say(
                f"  {label}：{time.time() - start:.2f} 秒，"
                f"{type(error).__name__} 状态 {error.status_code} {body}"
            )
            return None
        except openai.APIError as error:
            self.log.say(f"  {label}：{time.time() - start:.2f} 秒，{type(error).__name__} {error}")
            return None
        content = reply.choices[0].message.content or ""
        usage = reply.usage
        extras = getattr(reply.choices[0].message, "reasoning_content", None)
        self.log.say(
            f"  {label}：{time.time() - start:.2f} 秒，"
            f"用量 {usage.prompt_tokens}+{usage.completion_tokens}，"
            f"finish_reason={reply.choices[0].finish_reason}，"
            f"{'含 reasoning_content ' if extras else ''}回复 {len(content)} 字"
        )
        return content


def q1_temperature(probe: Probe) -> None:
    probe.log.say("== Q1 temperature=0 ==")
    for label, extra in (
        ("思考默认", {}),
        ("关闭思考", {"extra_body": {"enable_thinking": False}}),
    ):
        content = probe.call(
            f"temperature=0 + json_object + {label}",
            schema_in_prompt(),
            temperature=0,
            response_format={"type": "json_object"},
            **extra,
        )
        if content is not None:
            probe.log.say(f"      {validate(content)}")


def q2_json_schema(probe: Probe) -> None:
    probe.log.say("== Q2 response_format=json_schema（strict）==")
    for label, extra in (
        ("思考默认", {}),
        ("关闭思考", {"extra_body": {"enable_thinking": False}}),
    ):
        content = probe.call(
            f"json_schema + {label}",
            SYSTEM,
            temperature=0,
            response_format=strict_schema(),
            **extra,
        )
        if content is not None:
            probe.log.say(f"      {validate(content)}")
            probe.log.say(f"      回复前 {REPLY_LIMIT} 字：{content[:REPLY_LIMIT]}")


def q3_q4_json_object(probe: Probe) -> None:
    probe.log.say("== Q3 json_object（Schema 写在提示里）== Q4 关闭思考的影响 ==")
    for label, extra in (
        ("思考默认", {}),
        ("关闭思考", {"extra_body": {"enable_thinking": False}}),
    ):
        content = probe.call(
            f"json_object + {label}",
            schema_in_prompt(),
            temperature=0,
            response_format={"type": "json_object"},
            **extra,
        )
        if content is not None:
            probe.log.say(f"      {validate(content)}")


def q5_repeatability(probe: Probe) -> None:
    probe.log.say(f"== Q5 温度 0 下重复 {REPEATS} 次（json_object，思考默认）==")
    replies = []
    for index in range(REPEATS):
        content = probe.call(
            f"第 {index + 1} 次",
            schema_in_prompt(),
            temperature=0,
            response_format={"type": "json_object"},
        )
        replies.append(json.loads(content) if content else None)
    same = all(item == replies[0] for item in replies)
    probe.log.say(f"  {REPEATS} 次的 JSON {'完全相同' if same else '不完全相同'}")
    if not same:
        keys = ("recommended_type",)
        probe.log.say(f"  推荐的类型：{[item and item.get(keys[0]) for item in replies]}")


def q6_timeout(log: Log, base_url: str, api_key: str) -> None:
    log.say("== Q6 SDK 的超时和重试 ==")
    for retries in (0, 2):
        client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=SHORT_TIMEOUT_S, max_retries=retries
        )
        start = time.time()
        try:
            client.chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": case_text()}], temperature=0
            )
            log.say(f"  max_retries={retries}：{time.time() - start:.2f} 秒内居然返回了")
        except openai.APIError as error:
            log.say(
                f"  timeout={SHORT_TIMEOUT_S}、max_retries={retries}："
                f"{time.time() - start:.2f} 秒后抛 {type(error).__name__}"
            )


def q7_errors(log: Log, base_url: str, api_key: str) -> None:
    log.say("== Q7 错误的密钥和不存在的模型名 ==")
    cases: tuple[tuple[str, Callable[[], OpenAI], str], ...] = (
        (
            "错误的密钥",
            lambda: OpenAI(api_key="sk-not-a-key", base_url=base_url, max_retries=0),
            MODEL,
        ),
        (
            "不存在的模型",
            lambda: OpenAI(api_key=api_key, base_url=base_url, max_retries=0),
            "qwen-no-such-model",
        ),
    )
    for label, make_client, model in cases:
        start = time.time()
        try:
            make_client().chat.completions.create(
                model=model, messages=[{"role": "user", "content": "OK"}], max_tokens=4
            )
            log.say(f"  {label}：居然成功了")
        except openai.APIStatusError as error:
            body = scrub(str(error.body), api_key)[:200]
            log.say(
                f"  {label}：{time.time() - start:.2f} 秒，{type(error).__name__}，"
                f"状态 {error.status_code}，{body}"
            )
        except openai.APIError as error:
            log.say(f"  {label}：{type(error).__name__} {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    parser.add_argument("--ask-key", action="store_true")
    args = parser.parse_args()
    log = Log(f"e18_llm_structured_{args.tag}")
    api_key = os.environ.get(API_KEY_VARIABLE, "")
    if not api_key and args.ask_key:
        api_key = ask_for_key()
    if not api_key:
        log.say(f"{API_KEY_VARIABLE} 未设置：没有发出任何请求")
        return 2
    base_url = os.environ.get(BASE_URL_VARIABLE) or BASE_URLS[0]
    log.say(
        f"接口 {base_url}，模型 {MODEL}，openai SDK {openai.__version__}，密钥长度 {len(api_key)}"
    )
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=TIMEOUT_S, max_retries=0)
    probe = Probe(log, client)
    q1_temperature(probe)
    q2_json_schema(probe)
    q3_q4_json_object(probe)
    q5_repeatability(probe)
    q6_timeout(log, base_url, api_key)
    q7_errors(log, base_url, api_key)
    log.say("== E18 结束，结论由人读上面的输出后写进台账 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
