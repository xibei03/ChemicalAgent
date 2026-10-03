"""代码体检：把 CLAUDE.md 里可以由机器判断的规范变成测试。

检查的内容：模块之间的依赖方向；COM 库和 HYSYS 实现的使用范围；文件、函数、harness 的规模；
嵌套层数；读写文本文件是否写了编码；忽略检查的注释是否带规则码和原因；哪些模块可以点名反应器类型。
只读取 src/reactor_agent 下的源码，不需要 HYSYS，也不需要 LLM。

规则以 CLAUDE.md 为准。这里的上限和依赖表是给 AI 编程助手的硬约束，调整它们需要项目负责人决定。
直接运行本文件（python tests/test_code_health.py）会打印体检摘要，写交接报告时用。
"""

import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from pathlib import Path

PACKAGE = "reactor_agent"
SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / PACKAGE

MAX_FILE_CODE_LINES = 300
MAX_FUNCTION_CODE_LINES = 40
MAX_HARNESS_CODE_LINES = 600
MAX_NESTING_DEPTH = 3

# 装配点：可以导入任何模块，但不能被任何模块导入。
COMPOSITION_ROOT = "cli"

# 每个顶层模块允许导入的项目内模块。新增顶层模块时，先写进计划，再加到这张表里。
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "errors": frozenset(),
    "spec": frozenset({"errors"}),
    "backends": frozenset({"spec", "errors"}),
    "tools": frozenset({"backends", "spec", "errors"}),
    "recipes": frozenset({"spec", "errors"}),
    "validation": frozenset({"spec", "errors"}),
    "state": frozenset({"spec", "errors"}),
    "observability": frozenset({"spec", "errors"}),
    "llm": frozenset({"spec", "errors"}),
    "skill_loader": frozenset({"spec", "errors"}),
    "report": frozenset({"spec", "errors"}),
    "harness": frozenset(
        {
            "errors",
            "spec",
            "tools",
            "recipes",
            "validation",
            "state",
            "observability",
            "llm",
            "skill_loader",
            "report",
        }
    ),
}

COM_LIBRARIES = frozenset({"win32com", "pythoncom", "pywintypes"})
COM_ALLOWED_IN = ("backends", "hysys_com")

# 反应器类型的枚举。只有这几个模块可以点名具体的类型，其余模块一律通过注册表拿行为。
REACTOR_TYPE_ENUM = "ReactorType"
REACTOR_TYPE_BRANCHES_ALLOWED_IN = frozenset({"spec", "recipes", "backends"})

# 忽略检查的注释必须带规则码，后面再用一个注释写原因。写法见 CLAUDE.md 的"质量闸门"。
_SUPPRESSION = re.compile(r"#\s*(noqa|type:\s*ignore|ruff:\s*noqa|fmt:\s*(off|skip))")
_SUPPRESSION_WITH_REASON = re.compile(
    r"#\s*(noqa: [A-Z]+\d+(, ?[A-Z]+\d+)*|type: ignore\[[a-z-]+(, ?[a-z-]+)*\])\s+#\s*\S"
)
_BINARY_MODE = re.compile(r"^[rwxat+]*b[rwxat+]*$")
_TEXT_IO_CALLS = frozenset({"open", "read_text", "write_text"})

_IGNORED_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)
_DEFINITIONS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)


def source_files() -> list[Path]:
    """返回包内全部源文件，顺序固定。"""
    return sorted(SRC_ROOT.rglob("*.py"))


def relative_parts(path: Path) -> tuple[str, ...]:
    """文件相对包根目录的路径，去掉扩展名。例如 ("backends", "hysys_com", "session")。"""
    return path.relative_to(SRC_ROOT).with_suffix("").parts


def top_module(path: Path) -> str:
    """文件所属的顶层模块名。包根目录下的 __init__.py 返回空字符串。"""
    first = relative_parts(path)[0]
    return "" if first == "__init__" else first


def parse(path: Path) -> ast.Module:
    """把文件解析成语法树。"""
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def docstring_lines(tree: ast.Module) -> set[int]:
    """模块、类、函数的 docstring 占用的行号。"""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _DEFINITIONS) or not node.body:
            continue
        first = node.body[0]
        is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        )
        if is_docstring and first.end_lineno is not None:
            lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def code_lines(path: Path) -> set[int]:
    """含有代码的行号。空行、只有注释的行、docstring 都不算。"""
    text = path.read_text(encoding="utf-8-sig")
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in _IGNORED_TOKENS:
            lines.update(range(token.start[0], token.end[0] + 1))
    return lines - docstring_lines(ast.parse(text))


def imported_modules(path: Path) -> Iterator[tuple[int, tuple[str, ...]]]:
    """逐条给出文件里的导入：行号和被导入模块的完整路径（相对导入已换算成绝对路径）。"""
    package_parts = (PACKAGE, *relative_parts(path)[:-1])
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, tuple(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            base = package_parts[: len(package_parts) - node.level + 1] if node.level else ()
            module = tuple(node.module.split(".")) if node.module else ()
            for alias in node.names:
                yield node.lineno, (*base, *module, alias.name)


def project_dependencies(path: Path) -> Iterator[tuple[int, str]]:
    """文件导入了哪些项目内的顶层模块。"""
    for lineno, parts in imported_modules(path):
        if parts[0] == PACKAGE and len(parts) > 1:
            yield lineno, parts[1]


def function_sizes(path: Path) -> Iterator[tuple[str, int, int]]:
    """逐个给出文件里的函数：名字、起始行号、代码行数。"""
    lines = code_lines(path)
    for node in ast.walk(parse(path)):
        if isinstance(node, _FUNCTIONS) and node.end_lineno is not None:
            size = sum(1 for line in lines if node.lineno <= line <= node.end_lineno)
            yield node.name, node.lineno, size


def package_code_lines() -> dict[str, int]:
    """每个顶层模块的代码行数。"""
    totals: dict[str, int] = {}
    for path in source_files():
        name = top_module(path) or "__init__"
        totals[name] = totals.get(name, 0) + len(code_lines(path))
    return totals


def nesting_depth(node: ast.AST) -> int:
    """node 里面块语句（if/for/while/try/with/match）的最大嵌套层数。elif 不加深。"""
    deepest = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (*_FUNCTIONS, ast.ClassDef)):
            continue
        is_elif = isinstance(node, ast.If) and node.orelse == [child] and isinstance(child, ast.If)
        deeper = isinstance(child, _BLOCKS) and not is_elif
        deepest = max(deepest, nesting_depth(child) + deeper)
    return deepest


def text_io_without_encoding(path: Path) -> Iterator[int]:
    """文本方式读写文件却没有写 encoding 的调用所在的行号。"""
    for node in ast.walk(parse(path)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name not in _TEXT_IO_CALLS or any(k.arg == "encoding" for k in node.keywords):
            continue
        arguments = [*node.args, *(k.value for k in node.keywords if k.arg == "mode")]
        modes = [
            a.value for a in arguments if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        if name == "open" and any(_BINARY_MODE.match(mode) for mode in modes):
            continue
        yield node.lineno


def comments(path: Path) -> Iterator[tuple[int, str]]:
    """逐条给出文件里的注释：行号和注释文本。"""
    text = path.read_text(encoding="utf-8-sig")
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string


def location(path: Path, lineno: int | None = None) -> str:
    """报错时用的位置字符串。"""
    shown = path.relative_to(SRC_ROOT.parents[1]).as_posix()
    return shown if lineno is None else f"{shown}:{lineno}"


def test_every_top_level_module_is_planned():
    known = {*ALLOWED_IMPORTS, COMPOSITION_ROOT, ""}
    unknown = sorted({top_module(path) for path in source_files()} - known)
    assert not unknown, f"计划之外的顶层模块：{unknown}。先写进 MASTER_PLAN 和 ALLOWED_IMPORTS"


def test_import_directions():
    violations = []
    for path in source_files():
        owner = top_module(path)
        if owner in {"", COMPOSITION_ROOT}:
            continue
        allowed = ALLOWED_IMPORTS.get(owner, frozenset()) | {owner}
        for lineno, dependency in project_dependencies(path):
            if dependency not in allowed:
                violations.append(f"{location(path, lineno)}: {owner} 不允许导入 {dependency}")
    assert not violations, "依赖方向被破坏：\n" + "\n".join(violations)


def test_com_libraries_only_in_hysys_backend():
    violations = []
    for path in source_files():
        if relative_parts(path)[:2] == COM_ALLOWED_IN:
            continue
        for lineno, parts in imported_modules(path):
            if parts[0] in COM_LIBRARIES:
                violations.append(f"{location(path, lineno)}: 导入了 {parts[0]}")
    assert not violations, "COM 库只能出现在 backends/hysys_com 里：\n" + "\n".join(violations)


def test_files_are_small():
    oversized = [
        f"{location(path)}: {len(code_lines(path))} 行"
        for path in source_files()
        if len(code_lines(path)) > MAX_FILE_CODE_LINES
    ]
    assert not oversized, f"文件超过 {MAX_FILE_CODE_LINES} 行代码，把它拆开：\n" + "\n".join(
        oversized
    )


def test_functions_are_small():
    oversized = [
        f"{location(path, lineno)}: {name} 有 {size} 行"
        for path in source_files()
        for name, lineno, size in function_sizes(path)
        if size > MAX_FUNCTION_CODE_LINES
    ]
    assert not oversized, f"函数超过 {MAX_FUNCTION_CODE_LINES} 行代码，把它拆开：\n" + "\n".join(
        oversized
    )


def test_harness_stays_within_budget():
    size = package_code_lines().get("harness", 0)
    assert size <= MAX_HARNESS_CODE_LINES, (
        f"harness/ 有 {size} 行代码，预算是 {MAX_HARNESS_CODE_LINES}。"
        "明显超出说明设计变复杂了，先想有没有更简单的做法"
    )


def test_source_tree_is_not_empty():
    assert source_files(), f"{SRC_ROOT} 下没有源文件，体检测试什么都没有检查"


def test_package_root_imports_no_project_module():
    root = SRC_ROOT / "__init__.py"
    imported = [".".join(parts) for _, parts in imported_modules(root) if parts[0] == PACKAGE]
    assert not imported, (
        f"包的根 __init__.py 不导入项目内的模块，否则任何导入都会把它们带进来：{imported}"
    )


def test_hysys_backend_is_only_imported_by_composition_root():
    violations = []
    for path in source_files():
        if top_module(path) == COMPOSITION_ROOT or relative_parts(path)[:2] == COM_ALLOWED_IN:
            continue
        for lineno, parts in imported_modules(path):
            if parts[:3] == (PACKAGE, *COM_ALLOWED_IN):
                violations.append(f"{location(path, lineno)}: 导入了 HYSYS 的具体实现")
    assert not violations, "backends/hysys_com 只能由 cli 导入：\n" + "\n".join(violations)


def test_nesting_is_shallow():
    deep = [
        f"{location(path, node.lineno)}: {node.name} 嵌套了 {nesting_depth(node)} 层"
        for path in source_files()
        for node in ast.walk(parse(path))
        if isinstance(node, _FUNCTIONS) and nesting_depth(node) > MAX_NESTING_DEPTH
    ]
    assert not deep, f"嵌套超过 {MAX_NESTING_DEPTH} 层，用提前返回或者拆函数：\n" + "\n".join(deep)


def test_text_io_declares_encoding():
    missing = [
        location(path, lineno)
        for path in source_files()
        for lineno in text_io_without_encoding(path)
    ]
    assert not missing, '读写文本文件要写 encoding="utf-8"：\n' + "\n".join(missing)


def test_suppressions_carry_a_reason():
    bare = [
        f"{location(path, lineno)}: {comment}"
        for path in source_files()
        for lineno, comment in comments(path)
        if _SUPPRESSION.search(comment) and not _SUPPRESSION_WITH_REASON.search(comment)
    ]
    assert not bare, "忽略检查要写规则码和原因（# noqa: 规则码  # 原因）：\n" + "\n".join(bare)


def test_reactor_types_are_only_named_where_allowed():
    named = []
    for path in source_files():
        if top_module(path) in REACTOR_TYPE_BRANCHES_ALLOWED_IN:
            continue
        for node in ast.walk(parse(path)):
            if (
                isinstance(node, ast.Attribute)
                and getattr(node.value, "id", "") == REACTOR_TYPE_ENUM
            ):
                named.append(f"{location(path, node.lineno)}: {REACTOR_TYPE_ENUM}.{node.attr}")
    assert not named, "这些模块不应该点名具体的反应器类型，行为差别放进 Recipe：\n" + "\n".join(
        named
    )


def main() -> None:
    """打印体检摘要：各模块的行数、最长的函数、最深的嵌套、全部忽略注释。贴进交接报告。"""
    out = sys.stdout.write
    totals = package_code_lines()
    for name in sorted(totals):
        out(f"{name:<16}{totals[name]:>6}\n")
    out(f"{'合计':<14}{sum(totals.values()):>6}\n")
    functions = [
        (size, nesting_depth(node), location(path, node.lineno), node.name)
        for path in source_files()
        for node in ast.walk(parse(path))
        if isinstance(node, _FUNCTIONS)
        for name, lineno, size in function_sizes(path)
        if (name, lineno) == (node.name, node.lineno)
    ]
    out(f"\n最长的 5 个函数（上限 {MAX_FUNCTION_CODE_LINES} 行）\n")
    for size, _, where, name in sorted(functions, reverse=True)[:5]:
        out(f"  {size:>3} 行  {where} {name}\n")
    out(f"\n嵌套最深的 5 个函数（上限 {MAX_NESTING_DEPTH} 层）\n")
    for _, depth, where, name in sorted(functions, key=lambda item: item[1], reverse=True)[:5]:
        out(f"  {depth:>3} 层  {where} {name}\n")
    suppressions = [
        f"  {location(path, lineno)}: {comment}\n"
        for path in source_files()
        for lineno, comment in comments(path)
        if _SUPPRESSION.search(comment)
    ]
    out(f"\n忽略检查的注释共 {len(suppressions)} 处\n")
    for line in suppressions:
        out(line)


if __name__ == "__main__":
    main()
