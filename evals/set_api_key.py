"""设置并永久保存 LLM 的 API 密钥：在终端里输入一次，先测试连通，通过后写入用户级环境变量。

  python evals/set_api_key.py

流程：
  1. 用 getpass 读密钥（输入时不显示）。直接回车则只测试已经保存的那一个，不改动它。
  2. 用系统自己调用 LLM 的那条路径（DashScopeProvider，结构化输出）发一次最小请求，报告模型、耗时和
     用量。接口不通、密钥无效、模型没开通，都在这一步看到原因。
  3. 连通才把密钥写进用户级环境变量（HKEY_CURRENT_USER 的 Environment 键），写完读回比对。
     不通默认不保存，要保存得明确回答 y。

密钥不经过命令行参数、不写文件、不进日志、不回显，输出里只有它的长度。写入的是用户级变量，之后新
启动的进程能读到；已经打开的终端和程序要重开（evals/interactive.py 会直接读用户级变量，不用重开）。
系统本身（src/）仍然只从环境变量读密钥，这个入口只是替你设置那个环境变量。
"""

import ctypes
import getpass
import json
import sys
import time
import winreg
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from reactor_agent.cli import SETTINGS_FILE
from reactor_agent.errors import ReactorAgentError
from reactor_agent.llm.client import ChatProvider
from reactor_agent.llm.providers.dashscope import DashScopeProvider
from reactor_agent.spec.settings import LlmSettings, load_settings

ENVIRONMENT_KEY = "Environment"
# 通知资源管理器等程序“环境变量变了”，它们之后启动的进程才读得到新值。
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002
BROADCAST_TIMEOUT_MS = 5000

PROBE_SYSTEM = "这是一次连通性测试。只按要求的 JSON 格式回复。"
PROBE_USER = '回复 {"ok": true}。'
PROBE_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
REDACTED = "***"
PROBE_HINT = (
    "401 通常是密钥错误或失效；404 通常是模型名不对或没开通；连不上通常是网络或代理的问题。"
)
AFTER_SAVE_HINT = (
    "新打开的终端和新启动的程序能读到它；已经打开的终端和程序（包括正在运行的助手会话）要重开。"
    "`python evals/interactive.py` 会直接读这个用户级变量，不用重开。"
)


@dataclass(frozen=True)
class ProbeResult:
    """一次连通性测试的结果：接口有没有按要求回复，一句话说明，耗时。"""

    reachable: bool
    message: str
    elapsed_s: float


@dataclass(frozen=True)
class VariableStore:
    """用户级环境变量的读和写。真实的是注册表，测试里换成内存里的字典。"""

    read: Callable[[str], str | None]
    write: Callable[[str, str], None]


ProviderFactory = Callable[[LlmSettings, str], ChatProvider]
Ask = Callable[[str], str]


def read_user_variable(name: str) -> str | None:
    """读用户级环境变量。没有保存过返回 None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENVIRONMENT_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    return str(value)


def _broadcast_environment_change() -> None:
    """告诉系统用户级环境变量变了。超时或没有程序响应都不影响已经写入的值。"""
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        ENVIRONMENT_KEY,
        SMTO_ABORTIFHUNG,
        BROADCAST_TIMEOUT_MS,
        None,
    )


def write_user_variable(name: str, value: str) -> None:
    """写用户级环境变量并广播。直接写注册表，密钥不会出现在任何命令行里。"""
    access = winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENVIRONMENT_KEY, 0, access) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    _broadcast_environment_change()


def probe(provider: ChatProvider, secret: str) -> ProbeResult:
    """用系统调用 LLM 的路径发一次最小请求。错误信息里出现密钥的地方换成 ***。"""
    started = time.monotonic()
    try:
        reply = provider.generate(PROBE_SYSTEM, PROBE_USER, PROBE_SCHEMA)
    except ReactorAgentError as error:
        message = f"{error.message}\n  {PROBE_HINT}".replace(secret, REDACTED)
        return ProbeResult(False, message, time.monotonic() - started)
    elapsed = time.monotonic() - started
    usage = f"用量 {reply.prompt_tokens}+{reply.completion_tokens} tokens"
    try:
        json.loads(reply.text)
    except ValueError:
        message = f"模型 {provider.model} 有回复（{usage}），但结构化输出的回复不是合法的 JSON。"
        return ProbeResult(True, message, elapsed)
    return ProbeResult(True, f"模型 {provider.model} 回复了合法的 JSON（{usage}）。", elapsed)


def report(result: ProbeResult) -> None:
    """把测试结果打印出来。"""
    status = "连通" if result.reachable else "没有连通"
    print(f"测试结果：{status}（{result.elapsed_s:.1f} 秒）")
    print(f"  {result.message}")


def save_key(name: str, key: str, reachable: bool, ask_line: Ask, store: VariableStore) -> bool:
    """把密钥永久保存并读回比对；测试没通过时先问一次。返回有没有保存成功。"""
    if not reachable:
        answer = ask_line("连通测试没有通过。仍然保存这个密钥吗？[y/N]：")
        if answer.strip().lower() != "y":
            print("没有保存。")
            return False
    try:
        store.write(name, key)
    except OSError as error:
        print(f"写入用户级环境变量失败：{error}", file=sys.stderr)
        return False
    if store.read(name) != key:
        print("写入后读回的值与输入的不一致，没有保存成功。", file=sys.stderr)
        return False
    print(f"已永久保存到用户级环境变量 {name}（长度 {len(key)}，写入后读回一致）。")
    print(AFTER_SAVE_HINT)
    return True


def session(
    settings: LlmSettings,
    ask_secret: Ask,
    ask_line: Ask,
    make_provider: ProviderFactory,
    store: VariableStore,
) -> int:
    """读密钥、测试连通、保存。退出码：0 连通且（需要时）已保存，1 没连通或没保存，2 没有密钥。"""
    name = settings.api_key_env
    saved = store.read(name)
    print(f"要设置的用户级环境变量：{name}；接口 {settings.base_url}，模型 {settings.model}")
    if saved:
        print(f"{name} 已经保存过一个密钥（长度 {len(saved)}）。")
        print("直接回车只测试它的连通；输入新的密钥，测试后会覆盖它。")
    typed = ask_secret(f"请输入 {name}（输入时不显示）：").strip()
    key = typed or saved
    if not key:
        print("没有输入密钥，退出。", file=sys.stderr)
        return 2
    print(f"密钥已读入（长度 {len(key)}），正在测试连通……", flush=True)
    result = probe(make_provider(settings, key), key)
    report(result)
    if not typed:
        return 0 if result.reachable else 1
    stored = save_key(name, key, result.reachable, ask_line, store)
    return 0 if result.reachable and stored else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("需要在交互式终端里运行：密钥要在终端里输入。", file=sys.stderr)
        return 2
    store = VariableStore(read_user_variable, write_user_variable)
    settings = load_settings(SETTINGS_FILE).llm
    return session(settings, getpass.getpass, input, DashScopeProvider, store)


if __name__ == "__main__":
    raise SystemExit(main())
