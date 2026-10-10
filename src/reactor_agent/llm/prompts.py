"""给 LLM 的提问的拼装：写规格的上下文和重写时的内容。纯字符串处理，不读文件，不调用 LLM。

每次调用都是“系统提示 + 知识 + 状态视图”的纯函数，不带之前的对话（计划 §11）。系统提示和知识放在
system 里，用户的原文和选型结论放在 user 里，不混在一起。知识（Skill 正文、参考文件、字段说明、
组分命名参考）由调用方读好，按顺序传进来。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from reactor_agent.spec.results import Issue
from reactor_agent.spec.selection import REACTOR_NAMES, SelectionResult


@dataclass(frozen=True)
class Prompt:
    """给 LLM 的一次提问：system 是系统提示和知识，user 是用户的原文（和随任务变化的内容）。"""

    system: str
    user: str


def specify_prompt(
    system_prompt: str, knowledge: Sequence[str], selection: SelectionResult, text: str
) -> Prompt:
    """写规格的上下文：系统提示和各种知识放 system，用户的原文和（已经确定的）选型结论放 user。"""
    reactor = "无" if selection.reactor_type is None else REACTOR_NAMES[selection.reactor_type]
    basis = "；".join(selection.rule_notes)
    user = (
        f"用户的描述（原文）：\n\n{text}\n\n---\n"
        f"选型结论（系统已经确定，不能改）：{reactor} 反应器。依据：{basis}"
    )
    return Prompt(system="\n\n".join([system_prompt, *knowledge]), user=user)


def rewrite_content(prompt: Prompt, previous: BaseModel, issues: Sequence[Issue]) -> str:
    """重写时的用户内容：原来的提问，加上上一次的 TaskSpec 和程序发现的问题。"""
    lines = [
        f"- {issue.field_path}：{issue.message}"
        + ("（出在用户给的信息上）" if issue.user_fixable else "")
        for issue in issues
    ]
    return (
        f"{prompt.user}\n\n---\n你上一次写的 TaskSpec：\n{previous.model_dump_json()}\n\n"
        "程序校验发现的问题：\n" + "\n".join(lines) + "\n"
        "请只改有问题的地方，其余原样保留，重新输出完整的 TaskSpec。"
        "出在用户给的信息上的问题，先对照原文：是你抄错了就照原文改正；原文本来就是这样，"
        "就原样保留并写进 ambiguities，不要替用户改。"
    )
