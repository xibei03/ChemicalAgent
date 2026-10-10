"""E19（2B）：TaskSpec 的 JSON Schema 能不能被百炼的 json_schema（strict）接受，回复长什么样。

台账 L39 验证过 SelectionDraft 的 Schema（$defs、anyOf 加 null、additionalProperties: false，
没有 default 和 minLength）。2B 的 TaskSpec 嵌套更深（进料 → 组成 → 各项；反应 → 拆分产物 → 配比），要先确认
strict 模式照样接受，再把客户端和 Skill 建在它上面。

要回答的问题：
  Q1 三个 TaskSpec 类（转化、平衡、Gibbs）的 Schema 各自被接受吗？
  Q2 回复能通过各自的校验吗？第一处不合法在哪里？
  Q3 用时和用量（关闭思考）是多少？没有字段说明时回复的形状对不对？（粗看，不打分）

用法：python spikes/e19_taskspec_schema.py [--tag 名字]
密钥：环境变量里的（名字在 config/settings.yaml）；没有就退出。输出里不含密钥。
输出：spikes/out/e19_taskspec_schema_<tag>.txt（回复全文只留前 2500 个字符）
"""

import argparse
import os
import time

import openai
from _common import Log, use_utf8
from openai import OpenAI
from pydantic import ValidationError

from reactor_agent.cli import REPO_ROOT, SETTINGS_FILE
from reactor_agent.spec.settings import load_settings
from reactor_agent.spec.task_spec import (
    ConversionTaskSpec,
    EquilibriumTaskSpec,
    GibbsTaskSpec,
    TaskSpecBase,
)

use_utf8()

REPLY_LIMIT = 2500
TIMEOUT_S = 90.0
INPUTS = REPO_ROOT / "evals" / "inputs"
SYSTEM = (
    "你是化工过程建模系统里的一个环节。读用户的描述，把用户说了什么写成给定的结构。"
    "数值和单位照原文抄，不换算，不做算术；原文没给的量写 null 并列进 missing；"
    "需要假设时把来源写成 assumed 并给出依据。只按给定的结构输出。"
)
CASES: tuple[tuple[str, type[TaskSpecBase], str], ...] = (
    ("equilibrium", EquilibriumTaskSpec, "scenario-1.txt"),
    ("conversion", ConversionTaskSpec, "scenario-2.txt"),
    ("gibbs", GibbsTaskSpec, "scenario-3.txt"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e19_taskspec_schema_{args.tag}")
    settings = load_settings(SETTINGS_FILE).llm
    key = os.environ.get(settings.api_key_env, "")
    if not key:
        log.say(f"环境变量 {settings.api_key_env} 没有设置，退出。")
        return
    client = OpenAI(api_key=key, base_url=settings.base_url, timeout=TIMEOUT_S, max_retries=0)
    for name, model, input_file in CASES:
        text = (INPUTS / input_file).read_text(encoding="utf-8").strip()
        log.say(f"== {name}（{input_file}）==")
        schema = model.model_json_schema()
        log.say(f"  Schema 的顶层字段：{list(schema['properties'])}")
        started = time.time()
        try:
            reply = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"用户的描述（原文）：\n\n{text}"},
                ],
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "task_spec", "strict": True, "schema": schema},
                },
                extra_body={"enable_thinking": False},
            )
        except openai.APIError as error:
            body = str(getattr(error, "body", error))[:400]
            log.say(f"  {time.time() - started:.1f} 秒，{type(error).__name__}：{body}")
            continue
        content = reply.choices[0].message.content or ""
        usage = reply.usage
        log.say(
            f"  {time.time() - started:.1f} 秒，用量 {usage.prompt_tokens}+{usage.completion_tokens}，"
            f"回复 {len(content)} 字"
        )
        try:
            model.model_validate_json(content)
            log.say("  校验通过")
        except ValidationError as error:
            first = error.errors()[0]
            log.say(
                f"  校验失败（{error.error_count()} 处，第一处 {first['loc']}：{first['msg']}）"
            )
        log.say(f"  回复：{content[:REPLY_LIMIT]}")
    log.conclude("见上面每个类的接受情况、校验结果和回复。")


if __name__ == "__main__":
    main()
