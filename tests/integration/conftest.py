"""集成测试的夹具：整个测试会话只启动一次 HYSYS，每个测试用自己的 Case。"""

import faulthandler

import pytest

from reactor_agent.backends.hysys_com.backend import HysysComBackend
from reactor_agent.spec.enums import CaseMode, ToolName
from reactor_agent.spec.tool_args import CloseCaseArgs, ConnectArgs, EnsureCaseArgs
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor


@pytest.fixture(scope="session")
def backend():
    """会话级的 Backend：测试结束时结束自己启动的 HYSYS 实例。"""
    # 退出 HYSYS 时进程在 Quit() 调用中途消失，Windows 报 RPC 异常 0x800706ba，Backend 已经
    # 处理了它，但 pytest 的 faulthandler 会把它当作致命错误打印出来。它在配置阶段才启用，
    # 所以在这里关掉。
    faulthandler.disable()
    hysys = HysysComBackend()
    yield hysys
    dialogs = hysys.dialog_messages()
    hysys.shutdown()
    assert dialogs == (), f"测试期间 HYSYS 弹出过对话框，正常的建模流程不应该这样：{dialogs}"


@pytest.fixture(scope="session")
def executor(backend):
    """已经连接好 HYSYS 的 ToolExecutor。测试只通过它调用工具。"""
    executor = ToolExecutor(register_tools(backend))
    result = executor.call(ToolName.SESSION_CONNECT, ConnectArgs(visible=False))
    assert result.ok, result.error
    return executor


@pytest.fixture
def case_path(tmp_path, request):
    """每个测试一个新的 Case 路径；测试结束时关闭 Case，不保存。"""
    return tmp_path / f"{request.node.name.replace('[', '_').replace(']', '')}.hsc"


@pytest.fixture
def fresh_case(executor, case_path):
    """新建空白 Case 并返回它的路径；测试结束时关闭。"""
    result = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=case_path, mode=CaseMode.NEW))
    assert result.ok, result.error
    yield case_path
    executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))


@pytest.fixture(autouse=True)
def reconnect_if_hysys_crashed(backend, executor):
    """HYSYS 偶尔自己崩溃（台账 L33）。上一个测试把它弄没了就重新连接，让一次崩溃只影响一个测试。"""
    if not backend.is_running():
        backend.shutdown()
        result = executor.call(ToolName.SESSION_CONNECT, ConnectArgs(visible=False))
        assert result.ok, result.error
