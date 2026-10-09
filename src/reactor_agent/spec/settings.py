"""运行配置（config/settings.yaml）：LLM 供应商、模型、密钥所在的环境变量名、超时。

密钥本身不在文件里，只在环境变量里。路径由调用方传入，这里不猜路径。
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.loading import parse_model, read_document


class LlmSettings(FrozenModel):
    """LLM 的配置。"""

    provider: Literal["dashscope"]
    model: Annotated[str, Field(min_length=1)]
    base_url: Annotated[str, Field(min_length=1)]
    api_key_env: Annotated[str, Field(min_length=1)]
    timeout_s: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class Settings(FrozenModel):
    """config/settings.yaml 的全部内容。"""

    llm: LlmSettings


def load_settings(path: Path) -> Settings:
    """读配置文件。读不了是 E_IO，内容不合法是 E_SCHEMA。"""
    return parse_model(Settings, read_document(path), path.name)
