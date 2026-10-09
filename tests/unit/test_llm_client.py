"""LLM 客户端：输出合法、输出非法后带着错误重问成功、重问仍非法抛 E_LLM、供应商的错误原样上抛。

供应商用桩替换，所以这里测的是 StructuredClient 自己的逻辑，不需要网络。
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.llm.client import (
    CORRECTION_TEMPLATE,
    MAX_ATTEMPTS,
    MAX_PROBLEMS_SHOWN,
    LlmError,
    RawReply,
    StructuredClient,
)
from reactor_agent.llm.system_prompt import load_system_prompt
from reactor_agent.spec.settings import Settings, load_settings

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
SYSTEM = "系统提示"
USER = "用户内容"


class Answer(BaseModel):
    kind: str
    count: int


class Scripted:
    """按脚本回答的供应商桩：依次返回给定的文字，或者抛出给定的错误。"""

    model = "stub-model"

    def __init__(self, replies: Sequence[str | ReactorAgentError]) -> None:
        self.replies = list(replies)
        self.requests: list[tuple[str, str, Mapping[str, object]]] = []

    def generate(self, system: str, user: str, schema: Mapping[str, object]) -> RawReply:
        self.requests.append((system, user, schema))
        reply = self.replies.pop(0)
        if isinstance(reply, ReactorAgentError):
            raise reply
        return RawReply(text=reply, prompt_tokens=100, completion_tokens=20)


def valid(**fields: object) -> str:
    return json.dumps({"kind": "a", "count": 1, **fields})


def test_a_valid_reply_is_returned_as_the_model_with_a_record_of_one_attempt():
    provider = Scripted([valid(count=7)])
    reply = StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert reply.value == Answer(kind="a", count=7)
    record = reply.record
    assert record.model == "stub-model" and record.system_prompt == SYSTEM
    assert len(record.attempts) == 1 and record.attempts[0].user_content == USER
    assert record.attempts[0].validation_error is None
    assert record.total_tokens == 120 and record.duration_ms >= 0


def test_the_provider_receives_the_prompts_and_the_json_schema_of_the_output_type():
    provider = Scripted([valid()])
    StructuredClient(provider).complete(SYSTEM, USER, Answer)
    system, user, schema = provider.requests[0]
    assert (system, user) == (SYSTEM, USER)
    assert schema == Answer.model_json_schema()


def test_an_invalid_reply_is_asked_again_with_the_error_and_the_previous_reply():
    bad = json.dumps({"kind": "a", "count": "many"})
    provider = Scripted([bad, valid(count=2)])
    reply = StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert reply.value.count == 2
    assert len(provider.requests) == MAX_ATTEMPTS
    second = provider.requests[1][1]
    assert second.startswith(USER) and bad in second and "count" in second
    first, last = reply.record.attempts
    assert first.validation_error and "count" in first.validation_error
    assert last.validation_error is None and last.user_content == second
    assert reply.record.total_tokens == 240


def test_text_that_is_not_json_is_invalid_and_gets_one_more_chance():
    provider = Scripted(["我不知道怎么回答", valid()])
    reply = StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert reply.value == Answer(kind="a", count=1)
    assert "我不知道怎么回答" in provider.requests[1][1]


def test_a_reply_that_is_still_invalid_after_the_second_ask_is_an_llm_error():
    provider = Scripted(["不是 JSON", json.dumps({"kind": 3})])
    with pytest.raises(ReactorAgentError) as caught:
        StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert caught.value.code is ErrorCode.LLM
    assert len(provider.requests) == MAX_ATTEMPTS
    assert "Answer" in caught.value.message
    assert "kind" in caught.value.details["校验发现的问题"]
    assert caught.value.details["最后一次的回复"] == json.dumps({"kind": 3})


def test_a_reply_that_stays_invalid_keeps_both_exchanges_and_the_usage_in_the_error():
    provider = Scripted(["不是 JSON", json.dumps({"kind": 3})])
    with pytest.raises(LlmError) as caught:
        StructuredClient(provider).complete(SYSTEM, USER, Answer)
    record = caught.value.record
    assert record.model == "stub-model" and record.system_prompt == SYSTEM
    assert [a.reply_text for a in record.attempts] == ["不是 JSON", json.dumps({"kind": 3})]
    assert all(a.validation_error for a in record.attempts)
    assert record.total_tokens == 240


def test_there_is_never_a_third_attempt():
    provider = Scripted(["x", "y", valid()])
    with pytest.raises(ReactorAgentError):
        StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert len(provider.replies) == 1


def test_an_error_from_the_provider_goes_straight_up_without_a_retry():
    provider = Scripted([ReactorAgentError(ErrorCode.LLM, "网络不通"), valid()])
    with pytest.raises(ReactorAgentError, match="网络不通"):
        StructuredClient(provider).complete(SYSTEM, USER, Answer)
    assert len(provider.requests) == 1


def test_a_long_list_of_problems_is_cut_short_in_the_correction():
    class Many(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int
        f: int
        g: int

    provider = Scripted(["{}", "{}"])
    with pytest.raises(ReactorAgentError) as caught:
        StructuredClient(provider).complete(SYSTEM, USER, Many)
    problems = caught.value.details["校验发现的问题"]
    assert problems.count("- ") == MAX_PROBLEMS_SHOWN + 1 and "另有 2 处" in problems


def test_the_correction_template_keeps_the_original_user_content():
    text = CORRECTION_TEMPLATE.format(user=USER, reply="回复", problem="问题")
    assert text.startswith(USER) and "回复" in text and "问题" in text


def test_the_shared_system_prompt_states_the_three_rules_every_call_point_needs():
    prompt = load_system_prompt()
    for rule in ("不做算术", "不能悄悄补上", "只按给定的结构输出"):
        assert rule in prompt
    assert len(prompt) < 600


def test_the_settings_file_has_everything_the_client_needs_and_no_key():
    settings = load_settings(SETTINGS_FILE)
    assert isinstance(settings, Settings)
    assert settings.llm.api_key_env == "DASHSCOPE_API_KEY" and settings.llm.timeout_s > 0
    text = SETTINGS_FILE.read_text(encoding="utf-8")
    assert "sk-" not in text
