"""真正调用 LLM 的冒烟测试，只此一个：模型的实际表现由评测（evals/run_evals.py）来衡量。

默认不运行。需要密钥：在自己的终端里设置环境变量之后运行 `pytest -m llm tests/llm`。
"""

import os

import pytest
from pydantic import BaseModel

from reactor_agent.cli import SETTINGS_FILE, create_llm_client
from reactor_agent.spec.settings import load_settings

pytestmark = pytest.mark.llm


class Pong(BaseModel):
    word: str
    number: int


def test_a_real_call_returns_a_validated_instance_with_a_record():
    settings = load_settings(SETTINGS_FILE).llm
    if not os.environ.get(settings.api_key_env):
        pytest.skip(f"没有设置环境变量 {settings.api_key_env}，在自己的终端里设置后再运行")
    client = create_llm_client(settings)
    reply = client.complete(
        "你只按给定的结构输出。", "word 填 pong，number 填 3。不要做别的。", Pong
    )
    assert reply.value.word.lower() == "pong" and reply.value.number == 3
    record = reply.record
    assert record.model == settings.model and record.total_tokens > 0
    assert record.attempts[0].reply_text and settings.api_key_env not in record.system_prompt
