"""选型的上下文：系统提示、Skill、用户原文。

每次调用都是“系统提示 + Skill + 状态视图”的纯函数，不带之前的对话（计划 §11）。
系统提示和 Skill 放在 system 里，用户的原文放在 user 里，不混在一起。写规格的上下文在
llm/prompts.py，它不读文件；选型要读 Skill 的参考文件和示例，所以放在这里。
"""

from reactor_agent.llm.prompts import Prompt
from reactor_agent.skill_loader import EXAMPLES_DIR, REFERENCES_DIR, Skill, list_files, read_file
from reactor_agent.spec.selection import SelectionDraft
from reactor_agent.spec.selection_rules import Assessment, reask_feedback

# 选型要读的参考文件，按这个顺序放进上下文；示例全部放进去。
SELECTION_REFERENCES = ("selection_rules.md", "pitfalls.md")


def selection_prompt(system_prompt: str, skill: Skill, text: str) -> Prompt:
    """选型的上下文：系统提示、Skill 正文、参考文件、示例，加用户的原文。"""
    parts = [system_prompt, skill.body]
    parts += [read_file(skill, REFERENCES_DIR, name) for name in SELECTION_REFERENCES]
    parts += [read_file(skill, EXAMPLES_DIR, name) for name in list_files(skill, EXAMPLES_DIR)]
    return Prompt(system="\n\n".join(parts), user=f"用户的描述（原文）：\n\n{text}")


def reask_content(prompt: Prompt, previous: SelectionDraft, assessment: Assessment) -> str:
    """重问时的用户内容：原来的提问，加上上一次的输出和需要核对的问题。"""
    return (
        f"{prompt.user}\n\n---\n你上一次的输出：\n{previous.model_dump_json()}\n\n"
        f"需要核对的问题：\n{reask_feedback(previous, assessment)}\n"
        "请对照原文重新核对每个特征（分歧通常来自某个特征抽错了），再重新输出完整的结果。"
    )
