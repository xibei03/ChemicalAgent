"""HYSYS Backend 的隔离不变量：COM 异常的名字、带单位的读写和空值哨兵各自只出现在一个文件里。

tests/test_code_health.py 查依赖方向和规模，不查这几条，所以单独检查。
后面的阶段往 src/ 里加代码时，这几条仍然要成立。

带单位的读写看调用，不看字符串：固体碳的分子式和摄氏度的单位同名，只看字符串会误报（D18）。
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reactor_agent"
COM_ERRORS_FILE = "com_errors.py"
VARIABLES_FILE = "variables.py"
COM_ERROR_NAME = re.compile(r"com_error(?!s)")
# 带单位读写的 COM 方法：GetValue(unit)、SetValue(value, unit)、GetValues(unit)、
# SetValues(values, unit)。
UNIT_METHODS = frozenset({"GetValue", "SetValue", "GetValues", "SetValues"})
UNIT_STRINGS = frozenset({"C", "bar", "kPa", "kgmole/h", "kg/h", "kW"})
SENTINEL_MAGNITUDE = 32767


def source_files() -> Iterator[Path]:
    yield from sorted(SRC.rglob("*.py"))


def constants(path: Path) -> Iterator[object]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant):
            yield node.value


def unit_calls(source: str) -> Iterator[ast.Call]:
    """源码里对带单位读写方法的调用。"""
    for node in ast.walk(ast.parse(source)):
        is_method_call = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        if is_method_call and node.func.attr in UNIT_METHODS:
            yield node


def unit_strings_passed(call: ast.Call) -> list[object]:
    """这次调用直接传了哪些单位字符串。"""
    return [
        arg.value
        for arg in call.args
        if isinstance(arg, ast.Constant)
        and isinstance(arg.value, str)
        and arg.value in UNIT_STRINGS
    ]


def test_com_error_is_named_only_in_the_file_that_translates_it():
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in source_files()
        if path.name != COM_ERRORS_FILE and COM_ERROR_NAME.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"com_error 这个名字（含注释）只能出现在 {COM_ERRORS_FILE}：{offenders}"


def test_quantities_are_read_and_written_only_in_the_file_that_owns_the_units():
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{call.lineno}"
        for path in source_files()
        if path.name != VARIABLES_FILE
        for call in unit_calls(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"{sorted(UNIT_METHODS)} 只能在 {VARIABLES_FILE} 里调用：{offenders}"


def test_no_unit_string_is_passed_to_those_methods_outside_that_file():
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{call.lineno} {unit_strings_passed(call)}"
        for path in source_files()
        if path.name != VARIABLES_FILE
        for call in unit_calls(path.read_text(encoding="utf-8"))
        if unit_strings_passed(call)
    ]
    assert not offenders, f"HYSYS 的单位字符串只能由 {VARIABLES_FILE} 传出去：{offenders}"


def test_the_detector_sees_a_unit_string_passed_to_a_unit_method_and_ignores_other_strings():
    source = (
        'x.GetValue("C")\nformula = "C"\ny.Other("bar")\nz.SetValue(1.0, "kPa")\nGetValue("bar")'
    )
    found = [unit_strings_passed(call) for call in unit_calls(source)]
    assert found == [["C"], ["kPa"]]


def test_the_null_sentinel_appears_only_in_the_file_that_reads_and_writes_quantities():
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in source_files()
        if path.name != VARIABLES_FILE
        for value in constants(path)
        if isinstance(value, (int, float)) and abs(value) == SENTINEL_MAGNITUDE
    ]
    assert not offenders, f"HYSYS 的空值哨兵数只能出现在 {VARIABLES_FILE}：{offenders}"


def test_the_allowed_files_really_contain_what_the_checks_look_for():
    backend = SRC / "backends" / "hysys_com"
    assert COM_ERROR_NAME.search((backend / COM_ERRORS_FILE).read_text(encoding="utf-8"))
    variables = backend / VARIABLES_FILE
    called = {call.func.attr for call in unit_calls(variables.read_text(encoding="utf-8"))}
    assert called >= {"GetValue", "SetValue", "GetValues"}
    values = list(constants(variables))
    assert {value for value in values if isinstance(value, str)} >= UNIT_STRINGS
    assert any(isinstance(v, float) and abs(v) == SENTINEL_MAGNITUDE for v in values)
