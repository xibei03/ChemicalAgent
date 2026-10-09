"""三个调用点（选型、写规格、写解读）共用的系统提示，读自 llm/prompts/system.md。"""

from pathlib import Path

from reactor_agent.errors import ErrorCode, ReactorAgentError

SYSTEM_PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "system.md"


def load_system_prompt() -> str:
    """读系统提示。文件是随代码一起发布的，读不到是安装有问题，不是运行时的 I/O 故障。"""
    try:
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ReactorAgentError(
            ErrorCode.SCHEMA, f"读不了系统提示 {SYSTEM_PROMPT_FILE}：{error}"
        ) from error
