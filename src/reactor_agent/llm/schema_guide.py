"""从 pydantic 模型渲染给 LLM 看的字段说明。

百炼的结构化输出只用 Schema 约束生成，不把 Schema 放进提示（台账 L39、E19：提示的 token 数不含
Schema），所以字段的 description 模型是看不见的。这里把它们渲染成一份文字，由调用方放进上下文。
每个出现过的模型只写一次；字段的类型用中文写，枚举列出全部取值。
"""

import types
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Union, get_args, get_origin

from pydantic import BaseModel

TYPE_NAMES: Mapping[type, str] = MappingProxyType(
    {str: "文字", float: "数", int: "整数", bool: "是/否"}
)
NULL_TEXT = "null"


def _inner_types(annotation: object) -> list[object]:
    """注解里的各个类型：展开 X | None 和 tuple[X, ...]。"""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType, tuple):
        return [
            inner
            for arg in get_args(annotation)
            if arg is not Ellipsis
            for inner in _inner_types(arg)
        ]
    return [annotation]


def _models_in(annotation: object) -> list[type[BaseModel]]:
    return [
        item
        for item in _inner_types(annotation)
        if isinstance(item, type) and issubclass(item, BaseModel)
    ]


def _type_text(annotation: object) -> str:
    """字段类型的中文写法，如“Quantity 或 null”“FeedTask 的数组”。"""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        parts = [arg for arg in get_args(annotation) if arg is not type(None)]
        text = " 或 ".join(_type_text(arg) for arg in parts)
        return f"{text} 或 {NULL_TEXT}" if len(parts) != len(get_args(annotation)) else text
    if origin is tuple:
        return f"{_type_text(get_args(annotation)[0])} 的数组"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "取值：" + "、".join(str(member.value) for member in annotation)
    if isinstance(annotation, type):
        return TYPE_NAMES.get(annotation, annotation.__name__)
    return str(annotation)


def _collect(model: type[BaseModel], found: dict[type[BaseModel], None]) -> None:
    if model in found:
        return
    found[model] = None
    for info in model.model_fields.values():
        for nested in _models_in(info.annotation):
            _collect(nested, found)


def _block(model: type[BaseModel]) -> str:
    summary = (model.__doc__ or model.__name__).strip().splitlines()[0]
    lines = [f"### {model.__name__}：{summary}"]
    for name, info in model.model_fields.items():
        lines.append(f"- `{name}`（{_type_text(info.annotation)}）：{info.description or ''}")
    return "\n".join(lines)


def render_field_guide(model: type[BaseModel]) -> str:
    """模型和它用到的全部嵌套模型的字段说明，按用到的顺序，每个模型一节。"""
    found: dict[type[BaseModel], None] = {}
    _collect(model, found)
    return "\n\n".join(_block(item) for item in found)
