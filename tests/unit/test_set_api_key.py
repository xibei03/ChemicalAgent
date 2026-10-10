"""密钥设置入口：先测连通再保存、密钥不回显不打印、不通默认不保存、写入后读回比对。

提供者和变量存储都用假的，不需要终端、密钥或网络；注册表的读写用一个随机名字的临时变量验证。
"""

import sys
import uuid
import winreg
from collections.abc import Mapping

import pytest
import set_api_key

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.llm.client import RawReply
from reactor_agent.spec.settings import LlmSettings, load_settings

SETTINGS: LlmSettings = load_settings(set_api_key.SETTINGS_FILE).llm
VARIABLE = SETTINGS.api_key_env
SECRET = "sk-secret-value-123456"
OLD_SECRET = "sk-old-value-654321"


class FakeProvider:
    """按脚本回复或抛错的提供者，记录收到的请求。"""

    model = "fake-model"

    def __init__(
        self, reply: RawReply | ReactorAgentError, events: list[str] | None = None
    ) -> None:
        self.reply = reply
        self.events = events if events is not None else []
        self.requests: list[tuple[str, str, Mapping[str, object]]] = []

    def generate(self, system: str, user: str, schema: Mapping[str, object]) -> RawReply:
        self.events.append("probe")
        self.requests.append((system, user, schema))
        if isinstance(self.reply, ReactorAgentError):
            raise self.reply
        return self.reply


class Console:
    """假的终端和变量存储：按脚本回答，记录谁被问了什么、用什么密钥建了提供者。"""

    def __init__(
        self,
        typed: str = SECRET,
        reply: RawReply | ReactorAgentError | None = None,
        answers: tuple[str, ...] = (),
        saved: str | None = None,
    ) -> None:
        self.typed = typed
        self.events: list[str] = []
        ok = RawReply(text='{"ok": true}', prompt_tokens=20, completion_tokens=5)
        self.provider = FakeProvider(reply or ok, self.events)
        self.answers = list(answers)
        self.variables: dict[str, str] = {} if saved is None else {VARIABLE: saved}
        self.keys_used: list[str] = []
        self.written: list[tuple[str, str]] = []
        self.refuse_to_store = False
        self.store_ignores_writes = False

    def ask_secret(self, _prompt: str) -> str:
        return self.typed

    def ask_line(self, _prompt: str) -> str:
        return self.answers.pop(0)

    def make_provider(self, _settings: LlmSettings, key: str) -> FakeProvider:
        self.keys_used.append(key)
        return self.provider

    def read(self, name: str) -> str | None:
        return self.variables.get(name)

    def write(self, name: str, value: str) -> None:
        if self.refuse_to_store:
            raise PermissionError("拒绝访问")
        self.events.append("write")
        self.written.append((name, value))
        if not self.store_ignores_writes:
            self.variables[name] = value

    def session(self) -> int:
        store = set_api_key.VariableStore(self.read, self.write)
        return set_api_key.session(
            SETTINGS, self.ask_secret, self.ask_line, self.make_provider, store
        )


def llm_error(message: str) -> ReactorAgentError:
    return ReactorAgentError(ErrorCode.LLM, message)


def test_a_reachable_key_is_saved_after_the_probe_and_read_back(capsys):
    console = Console()
    assert console.session() == 0
    assert console.written == [(VARIABLE, SECRET)]
    out = capsys.readouterr().out
    assert "连通" in out and f"长度 {len(SECRET)}" in out and "读回一致" in out


def test_the_key_is_never_printed(capsys):
    console = Console()
    console.session()
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_the_probe_goes_through_the_provider_with_a_json_schema_and_the_typed_key():
    console = Console()
    console.session()
    assert console.keys_used == [SECRET]
    [(_system, _user, schema)] = console.provider.requests
    assert schema["type"] == "object" and schema["required"] == ["ok"]


def test_the_key_is_tested_before_it_is_written():
    console = Console()
    console.session()
    assert console.events == ["probe", "write"]


def test_an_unreachable_key_is_not_saved_by_default(capsys):
    console = Console(reply=llm_error("LLM 接口返回 401（AuthenticationError）"), answers=("",))
    assert console.session() == 1
    assert console.written == []
    out = capsys.readouterr().out
    assert "没有连通" in out and "401" in out and "没有保存" in out


def test_an_unreachable_key_is_saved_only_after_an_explicit_yes(capsys):
    console = Console(reply=llm_error("连不上 LLM 接口"), answers=("y",))
    assert console.session() == 1
    assert console.written == [(VARIABLE, SECRET)]
    assert "已永久保存" in capsys.readouterr().out


def test_a_key_echoed_in_an_error_message_is_redacted(capsys):
    console = Console(reply=llm_error(f"Incorrect API key provided: {SECRET}"), answers=("",))
    console.session()
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert set_api_key.REDACTED in captured.out


def test_a_reply_that_is_not_json_is_reachable_but_flagged():
    provider = FakeProvider(RawReply(text="好的", prompt_tokens=1, completion_tokens=1))
    result = set_api_key.probe(provider, SECRET)
    assert result.reachable and "不是合法的 JSON" in result.message


def test_pressing_enter_tests_the_saved_key_and_does_not_rewrite_it(capsys):
    console = Console(typed="", saved=OLD_SECRET)
    assert console.session() == 0
    assert console.keys_used == [OLD_SECRET] and console.written == []
    assert f"长度 {len(OLD_SECRET)}" in capsys.readouterr().out


def test_pressing_enter_with_an_unreachable_saved_key_exits_with_one():
    console = Console(typed="", saved=OLD_SECRET, reply=llm_error("连不上"))
    assert console.session() == 1
    assert console.written == []


def test_a_new_key_replaces_the_saved_one_after_a_successful_probe():
    console = Console(saved=OLD_SECRET)
    assert console.session() == 0
    assert console.variables[VARIABLE] == SECRET


def test_an_unreachable_new_key_leaves_the_saved_one_untouched():
    console = Console(saved=OLD_SECRET, reply=llm_error("401"), answers=("",))
    console.session()
    assert console.variables[VARIABLE] == OLD_SECRET


def test_no_key_at_all_exits_with_two_and_does_nothing(capsys):
    console = Console(typed="   ")
    assert console.session() == 2
    assert console.keys_used == [] and console.written == []
    assert "没有输入密钥" in capsys.readouterr().err


def test_a_value_that_does_not_read_back_is_reported_as_not_saved(capsys):
    console = Console()
    console.store_ignores_writes = True
    assert console.session() == 1
    assert "不一致" in capsys.readouterr().err


def test_a_registry_write_failure_is_reported_not_raised(capsys):
    console = Console()
    console.refuse_to_store = True
    assert console.session() == 1
    assert "拒绝访问" in capsys.readouterr().err


def test_without_a_terminal_it_refuses_instead_of_waiting_for_input(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert set_api_key.main() == 2
    assert "交互式终端" in capsys.readouterr().err


@pytest.fixture
def temporary_variable(monkeypatch):
    """随机名字的用户级变量，用完删除；不广播环境变量变更，免得打扰别的程序。"""
    monkeypatch.setattr(set_api_key, "_broadcast_environment_change", lambda: None)
    name = f"REACTOR_AGENT_TEST_{uuid.uuid4().hex}"
    yield name
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, set_api_key.ENVIRONMENT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass  # 测试里没有写成功就没有可删的，不是清理的失败


def test_a_user_variable_is_written_to_the_registry_and_read_back(temporary_variable):
    assert set_api_key.read_user_variable(temporary_variable) is None
    set_api_key.write_user_variable(temporary_variable, SECRET)
    assert set_api_key.read_user_variable(temporary_variable) == SECRET
    set_api_key.write_user_variable(temporary_variable, OLD_SECRET)
    assert set_api_key.read_user_variable(temporary_variable) == OLD_SECRET
