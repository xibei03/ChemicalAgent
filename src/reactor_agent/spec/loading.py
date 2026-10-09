"""把配置文件和规格文件读成模型的公共部分。

读文件、按扩展名解析 YAML 或 JSON、把校验错误变成带字段路径的领域错误。规格文件和组分表都用它，
所以出错时的说法一致：文件读不了是 E_IO，内容不合法是 E_SCHEMA。
"""

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from reactor_agent.errors import ErrorCode, ReactorAgentError

ModelT = TypeVar("ModelT", bound=BaseModel)
WHOLE_DOCUMENT = "（整份文件）"


def read_utf8(path: Path, *, encoding: str = "utf-8") -> str:
    """读 UTF-8 文本文件。读不了是 E_IO；不是 UTF-8 是 E_SCHEMA（原样重试没有意义）。"""
    try:
        return path.read_text(encoding=encoding)
    except UnicodeDecodeError as error:
        raise ReactorAgentError(ErrorCode.SCHEMA, f"{path.name} 不是 UTF-8 编码的文本") from error
    except OSError as error:
        raise ReactorAgentError(ErrorCode.IO, f"读不了文件 {path}：{error}") from error


def read_document(path: Path) -> object:
    """读 YAML 或 JSON 文件（按扩展名），返回解析出的对象。"""
    text = read_utf8(path)
    try:
        return json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        message = f"{path.name} 不是合法的 YAML 或 JSON：{error}"
        raise ReactorAgentError(ErrorCode.SCHEMA, message) from error


def read_text_file(path: Path) -> str:
    """读用户给的文字描述（有无 BOM 都行）。读不了是 E_IO，不合法或为空是 E_SCHEMA。"""
    text = read_utf8(path, encoding="utf-8-sig").strip()
    if not text:
        raise ReactorAgentError(ErrorCode.SCHEMA, f"{path.name} 是空的，没有可模拟的描述")
    return text


def field_path(location: tuple[int | str, ...]) -> str:
    """把 pydantic 的出错位置写成固定的字段路径，如 feeds[0].temperature_c。"""
    path = ""
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path or WHOLE_DOCUMENT


def parse_model(model: type[ModelT], document: object, source: str) -> ModelT:
    """校验解析出来的对象。失败时消息里点出第一处问题，细节里列出每个字段的问题。"""
    try:
        return model.model_validate(document)
    except ValidationError as error:
        problems = {field_path(item["loc"]): item["msg"] for item in error.errors()}
        where, why = next(iter(problems.items()))
        message = f"{source} 的内容不合法：{where}：{why}（共 {len(problems)} 处）"
        raise ReactorAgentError(ErrorCode.SCHEMA, message, problems) from error
