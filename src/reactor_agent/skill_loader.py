"""Skill 加载：按名字读 skills/<名字>/，解析元数据和正文，按需读文件，读 rules.yaml。

Skill 是给 LLM 的知识包，不含执行逻辑。三级加载：元数据（不进 LLM）、SKILL.md 正文、
references/ 和 examples/ 里按需读的文件。skills/ 目录的位置由调用方传入。
内容哈希覆盖目录里的全部文件，Trace 用它记录“这次用的是哪一版”。
"""

import hashlib
import re
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import WorkflowState
from reactor_agent.spec.loading import parse_model, read_document

SKILL_FILE = "SKILL.md"
RULES_FILE = "rules.yaml"
REFERENCES_DIR = "references"
EXAMPLES_DIR = "examples"
# 开头是一段用 --- 围起来的 YAML 元数据，后面是正文。
FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)
ModelT = TypeVar("ModelT", bound=BaseModel)


class Skill(FrozenModel):
    """一个已加载的 Skill：元数据、正文、所在目录和内容哈希。"""

    name: str
    description: str
    version: str
    used_in: tuple[WorkflowState, ...]
    body: str
    directory: Path
    content_hash: str


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ReactorAgentError(ErrorCode.SCHEMA, f"读不了 Skill 文件 {path}：{error}") from error


def content_hash(directory: Path) -> str:
    """目录里全部文件的 SHA-256。换行统一成 LF，同一份内容在不同系统上哈希一样。"""
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8") + b"\0")
        digest.update(_read_bytes(path).replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def _split_front_matter(text: str, source: str) -> tuple[object, str]:
    match = FRONT_MATTER.match(text)
    if match is None:
        raise ReactorAgentError(ErrorCode.SCHEMA, f"{source} 开头没有用 --- 围起来的元数据")
    try:
        return yaml.safe_load(match.group(1)), match.group(2).strip()
    except yaml.YAMLError as error:
        raise ReactorAgentError(
            ErrorCode.SCHEMA, f"{source} 的元数据不是合法的 YAML：{error}"
        ) from error


class _Meta(FrozenModel):
    name: str
    description: str
    version: str
    used_in: tuple[WorkflowState, ...]


def load_skill(skills_dir: Path, name: str) -> Skill:
    """加载 skills_dir/<name>/。目录或 SKILL.md 不存在、元数据不合法、名字对不上都是 E_SCHEMA。"""
    directory = skills_dir / name
    skill_file = directory / SKILL_FILE
    if not skill_file.is_file():
        raise ReactorAgentError(ErrorCode.SCHEMA, f"没有找到 Skill {name}：{skill_file} 不存在")
    text = _read_bytes(skill_file).decode("utf-8")
    document, body = _split_front_matter(text, f"{name}/{SKILL_FILE}")
    meta = parse_model(_Meta, document, f"{name}/{SKILL_FILE} 的元数据")
    if meta.name != name:
        message = f"Skill 目录叫 {name}，元数据里的名字却是 {meta.name}"
        raise ReactorAgentError(ErrorCode.SCHEMA, message)
    return Skill(
        **meta.model_dump(), body=body, directory=directory, content_hash=content_hash(directory)
    )


def list_files(skill: Skill, subdirectory: str) -> tuple[str, ...]:
    """references/ 或 examples/ 下的文件名，按名字排序；目录不存在是空。"""
    folder = skill.directory / subdirectory
    if not folder.is_dir():
        return ()
    return tuple(sorted(item.name for item in folder.iterdir() if item.is_file()))


def read_file(skill: Skill, subdirectory: str, filename: str) -> str:
    """读 references/ 或 examples/ 下的一个文件。"""
    return _read_bytes(skill.directory / subdirectory / filename).decode("utf-8").strip()


def load_rules(skill: Skill, model: type[ModelT]) -> ModelT:
    """把 rules.yaml 读成规则表模型。文件不存在是 E_SCHEMA：它是 Skill 的一部分，不是运行时输入。"""
    path = skill.directory / RULES_FILE
    if not path.is_file():
        raise ReactorAgentError(ErrorCode.SCHEMA, f"Skill {skill.name} 没有 {RULES_FILE}")
    return parse_model(model, read_document(path), f"{skill.name}/{RULES_FILE}")
