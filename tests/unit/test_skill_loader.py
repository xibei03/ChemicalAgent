"""Skill 加载：元数据解析、正文、内容哈希、按需读文件、规则表。"""

from pathlib import Path

import pytest
from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.skill_loader import content_hash, list_files, load_rules, load_skill, read_file
from reactor_agent.spec.enums import WorkflowState

SKILL_TEXT = """---
name: demo
description: 演示用的 Skill
version: 1.2.0
used_in: [SELECT]
---

# 正文

这是正文。
"""


class Rules(BaseModel):
    limit: int


def make_skill(root: Path, text: str = SKILL_TEXT, name: str = "demo") -> Path:
    directory = root / name
    (directory / "references").mkdir(parents=True)
    (directory / "examples").mkdir()
    (directory / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")
    (directory / "references" / "b.md").write_text("乙\n", encoding="utf-8", newline="\n")
    (directory / "references" / "a.md").write_text("甲\n", encoding="utf-8", newline="\n")
    (directory / "rules.yaml").write_text("limit: 3\n", encoding="utf-8", newline="\n")
    return directory


def test_the_metadata_and_the_body_are_parsed(tmp_path):
    make_skill(tmp_path)
    skill = load_skill(tmp_path, "demo")
    assert (skill.name, skill.description, skill.version) == ("demo", "演示用的 Skill", "1.2.0")
    assert skill.used_in == (WorkflowState.SELECT,)
    assert skill.body.startswith("# 正文") and skill.body.endswith("这是正文。")
    assert "---" not in skill.body and "version" not in skill.body


def test_references_are_listed_in_order_and_read_on_demand(tmp_path):
    make_skill(tmp_path)
    skill = load_skill(tmp_path, "demo")
    assert list_files(skill, "references") == ("a.md", "b.md")
    assert list_files(skill, "examples") == ()
    assert list_files(skill, "nowhere") == ()
    assert read_file(skill, "references", "a.md") == "甲"


def test_the_hash_is_stable_and_changes_with_any_file_in_the_skill(tmp_path):
    directory = make_skill(tmp_path)
    first = content_hash(directory)
    assert content_hash(directory) == first
    (directory / "references" / "a.md").write_text("甲甲\n", encoding="utf-8", newline="\n")
    assert content_hash(directory) != first


def test_the_hash_changes_when_a_file_is_added_or_renamed(tmp_path):
    directory = make_skill(tmp_path)
    first = content_hash(directory)
    (directory / "references" / "b.md").rename(directory / "references" / "c.md")
    assert content_hash(directory) != first


def test_the_hash_does_not_depend_on_line_endings(tmp_path):
    lf = make_skill(tmp_path / "lf")
    crlf = make_skill(tmp_path / "crlf")
    for path in crlf.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert content_hash(lf) == content_hash(crlf)


def test_the_skill_carries_its_hash(tmp_path):
    directory = make_skill(tmp_path)
    assert load_skill(tmp_path, "demo").content_hash == content_hash(directory)


def test_the_rules_are_read_into_the_given_model(tmp_path):
    make_skill(tmp_path)
    assert load_rules(load_skill(tmp_path, "demo"), Rules) == Rules(limit=3)


def test_invalid_rules_are_a_schema_error_that_names_the_field(tmp_path):
    directory = make_skill(tmp_path)
    (directory / "rules.yaml").write_text("limit: many\n", encoding="utf-8")
    with pytest.raises(ReactorAgentError, match="limit") as caught:
        load_rules(load_skill(tmp_path, "demo"), Rules)
    assert caught.value.code is ErrorCode.SCHEMA


def test_missing_rules_are_a_schema_error(tmp_path):
    directory = make_skill(tmp_path)
    (directory / "rules.yaml").unlink()
    with pytest.raises(ReactorAgentError) as caught:
        load_rules(load_skill(tmp_path, "demo"), Rules)
    assert caught.value.code is ErrorCode.SCHEMA


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("没有元数据\n", "元数据"),
        ("---\nname: demo\nversion: 1\n---\n正文\n", "description"),
        ("---\nname: demo\ndescription: x\nversion: '1'\nused_in: [NOWHERE]\n---\n", "used_in"),
        ("---\nname: other\ndescription: x\nversion: '1'\nused_in: []\n---\n", "other"),
        ("---\nname: [\n---\n", "YAML"),
    ],
)
def test_a_broken_skill_file_is_a_schema_error_that_says_what_is_wrong(tmp_path, text, fragment):
    make_skill(tmp_path, text)
    with pytest.raises(ReactorAgentError, match=fragment) as caught:
        load_skill(tmp_path, "demo")
    assert caught.value.code is ErrorCode.SCHEMA


def test_a_skill_that_does_not_exist_is_a_schema_error(tmp_path):
    with pytest.raises(ReactorAgentError, match="nowhere") as caught:
        load_skill(tmp_path, "nowhere")
    assert caught.value.code is ErrorCode.SCHEMA
