"""HYSYS Backend 的隔离不变量：COM 异常的名字、单位字符串和空值哨兵各自只出现在一个文件里。

tests/test_code_health.py 查依赖方向和规模，不查这几条，所以单独检查。
后面的阶段往 src/ 里加代码时，这几条仍然要成立。
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reactor_agent"
COM_ERRORS_FILE = "com_errors.py"
VARIABLES_FILE = "variables.py"
COM_ERROR_NAME = re.compile(r"com_error(?!s)")
UNIT_STRINGS = frozenset({"C", "bar", "kPa", "kgmole/h", "kg/h", "kW"})
# 个别字符串碰巧和单位字符串同名，但不是单位。每一处写明原因，同样的字符串出现在别的文件里仍然报错。
NOT_A_UNIT = {("recipes/gibbs.py", "C"): "碳的分子式，不是摄氏度（D18）"}
SENTINEL_MAGNITUDE = 32767


def source_files() -> Iterator[Path]:
    yield from sorted(SRC.rglob("*.py"))


def constants(path: Path) -> Iterator[object]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant):
            yield node.value


def test_com_error_is_named_only_in_the_file_that_translates_it():
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in source_files()
        if path.name != COM_ERRORS_FILE and COM_ERROR_NAME.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"com_error 这个名字（含注释）只能出现在 {COM_ERRORS_FILE}：{offenders}"


def test_unit_strings_appear_only_in_the_file_that_reads_and_writes_quantities():
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {value!r}"
        for path in source_files()
        if path.name != VARIABLES_FILE
        for value in constants(path)
        if isinstance(value, str) and value in UNIT_STRINGS
        if (path.relative_to(SRC).as_posix(), value) not in NOT_A_UNIT
    ]
    assert not offenders, f"HYSYS 的单位字符串只能出现在 {VARIABLES_FILE}：{offenders}"


def test_every_exception_for_a_string_that_is_not_a_unit_is_still_needed():
    for relative, value in NOT_A_UNIT:
        assert value in set(constants(SRC / relative)), (relative, value)


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
    values = list(constants(backend / VARIABLES_FILE))
    assert {value for value in values if isinstance(value, str)} >= UNIT_STRINGS
    assert any(isinstance(v, float) and abs(v) == SENTINEL_MAGNITUDE for v in values)
