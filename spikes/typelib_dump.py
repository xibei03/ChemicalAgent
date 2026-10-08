"""任务 6：导出 HYSYS 类型库，整理接口和成员，检索与反应相关的名字。

要回答的问题：
  Q1 类型库里有哪些接口、枚举、组件类？
  Q2 三种反应器、反应、反应集对应哪些接口，成员各是什么？
  Q3 哪些集合对象有 Add 方法，参数是什么？
  Q4 有没有 BackDoor、XML、Script 之类的降级通道？
  Q5 早绑定包装能生成吗？生成之后的类里有没有这些成员？

做法：
  1. gencache.EnsureModule 为类型库生成早绑定包装（后面的探针可以用它）。
  2. 用 pythoncom.LoadRegTypeLib 读类型信息，把接口、成员签名整理成文本，
     因为类型信息里有参数名、类型和可选标记，生成的包装代码里没有这些。
  3. 用生成的包装类核对几个关键接口的成员。

输出（UTF-8，脚本自己写，每个文件都小于 1 MB）：
  spikes/out/typelib_members.txt       每个接口一行：接口名、基接口、全部成员名
  spikes/out/typelib_reaction_api.txt  反应、反应器、流体包、物流、变量等相关接口的完整签名
  spikes/out/typelib_hits.txt          十个关键词的检索结果（带签名）
  spikes/out/typelib_enums.txt         枚举的取值
  spikes/out/typelib_dump.txt          本脚本的运行记录
"""

import re
import time
from collections import Counter
from dataclasses import dataclass, field

import pythoncom
import win32com
import win32com.client
from _common import OUT_DIR, Log, use_utf8

use_utf8()

TLB_GUID = "{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}"
TLB_LCID, TLB_MAJOR, TLB_MINOR = 0, 3, 2
KEYWORDS = (
    "Reaction",
    "ReactionSet",
    "Equilibrium",
    "Conversion",
    "Gibbs",
    "Reactor",
    "Add",
    "BackDoor",
    "XML",
    "Script",
)
MAX_HITS_PER_KEYWORD = 400
# 在这么多个接口里都出现的成员是各类对象共有的基础成员（名称、类型名、父对象等），完整签名里省略
COMMON_MIN_INTERFACES = 150
# 后面探针和 Backend 最可能用到的接口：反应、反应器、反应集、流体包、物流、求解器、集合
RELEVANT_INTERFACE = re.compile(
    r"react|rxn|gibbs|equilib|conversion|kinetic|basis|fluidpack|stream|solver|"
    r"^(operations|flowsheet|simulationcase|simulationcases|components?|application)$",
    re.IGNORECASE,
)
# 有这些成员的接口是"变量"一类的对象（温度、压力、流量等），一并列出
VARIABLE_MEMBERS = frozenset({"SetValue", "GetValue", "IsKnown"})
WRAPPER_CHECK = ("ReactionSets", "Reactions", "Operations", "FluidPackages", "SimulationCases")

TKIND = {0: "enum", 1: "record", 2: "module", 3: "interface", 4: "dispatch", 5: "coclass"}
TKIND_ALIAS = 6
INVOKE = {1: "call", 2: "get", 4: "put", 8: "putref"}
BASE_METHODS = frozenset(
    {
        "QueryInterface",
        "AddRef",
        "Release",
        "GetTypeInfoCount",
        "GetTypeInfo",
        "GetIDsOfNames",
        "Invoke",
    }
)
VT_NAMES = {
    0: "void",
    2: "short",
    3: "long",
    4: "float",
    5: "double",
    6: "currency",
    7: "date",
    8: "BSTR",
    9: "IDispatch",
    10: "SCODE",
    11: "bool",
    12: "VARIANT",
    13: "IUnknown",
    16: "char",
    17: "byte",
    18: "ushort",
    19: "ulong",
    20: "int64",
    21: "uint64",
    22: "int",
    23: "uint",
    24: "void",
    25: "HRESULT",
    30: "LPSTR",
    31: "LPWSTR",
}
VT_PTR, VT_SAFEARRAY, VT_USERDEFINED = 26, 27, 29
PARAM_OUT, PARAM_RETVAL, PARAM_OPTIONAL = 2, 8, 16


@dataclass
class TypeRecord:
    name: str
    kind: str
    bases: list[str] = field(default_factory=list)
    members: list[tuple[str, str]] = field(default_factory=list)


def type_name(info, desc) -> str:
    """把 TYPEDESC 译成可读的类型名。"""
    if isinstance(desc, int):
        return VT_NAMES.get(desc & 0xFFF, f"vt{desc & 0xFFF}")
    vt, extra = desc[0], desc[1]
    if vt == VT_PTR:
        return type_name(info, extra) + "*"
    if vt == VT_SAFEARRAY:
        return f"SAFEARRAY({type_name(info, extra)})"
    if vt == VT_USERDEFINED:
        try:
            return info.GetRefTypeInfo(extra).GetDocumentation(-1)[0]
        except pythoncom.com_error:
            return f"userdefined#{extra}"
    return VT_NAMES.get(vt, f"vt{vt}")


def describe_param(info, name: str, elem) -> str:
    flags = elem[1]
    text = f"{name}: {type_name(info, elem[0])}"
    marks = [m for bit, m in ((PARAM_OUT, "out"), (PARAM_RETVAL, "retval")) if flags & bit]
    if flags & PARAM_OPTIONAL:
        marks.append("opt")
    return text + (f" [{','.join(marks)}]" if marks else "")


def describe_function(info, fd) -> tuple[str, str] | None:
    """一个函数描述：(成员名, 签名)。IUnknown 和 IDispatch 的基础方法返回 None。"""
    names = info.GetNames(fd.memid)
    if names[0] in BASE_METHODS:
        return None
    params = [
        describe_param(info, names[i + 1] if i + 1 < len(names) else f"arg{i}", elem)
        for i, elem in enumerate(fd.args)
    ]
    signature = f"{INVOKE.get(fd.invkind, fd.invkind)} {names[0]}"
    if params:
        signature += f"({', '.join(params)})"
    return names[0], f"{signature} -> {type_name(info, fd.rettype[0])}"


def ref_name(info, href: int) -> str:
    return info.GetRefTypeInfo(href).GetDocumentation(-1)[0]


def read_type(tlb, index: int) -> TypeRecord:
    name = tlb.GetDocumentation(index)[0]
    info = tlb.GetTypeInfo(index)
    attr = info.GetTypeAttr()
    record = TypeRecord(name, TKIND.get(attr.typekind, f"kind{attr.typekind}"))
    record.bases = [ref_name(info, info.GetRefTypeOfImplType(k)) for k in range(attr.cImplTypes)]
    for j in range(attr.cFuncs):
        described = describe_function(info, info.GetFuncDesc(j))
        if described:
            record.members.append(described)
    for k in range(attr.cVars):
        var = info.GetVarDesc(k)
        var_name = info.GetNames(var.memid)[0]
        if record.kind == "enum":
            record.members.append((var_name, f"{var_name}={var.value}"))
        else:
            record.members.append(
                (var_name, f"var {var_name}: {type_name(info, var.elemdescVar[0])}")
            )
    return record


def heading(rec: TypeRecord) -> str:
    return f"[{rec.kind}] {rec.name}" + (f" : {', '.join(rec.bases)}" if rec.bases else "")


def write_members(records: list[TypeRecord]) -> None:
    """每个接口一行，只写成员名，便于 grep；带签名的版本见 write_reaction_api 和 hits。"""
    with (OUT_DIR / "typelib_members.txt").open("w", encoding="utf-8") as out:
        for rec in sorted(records, key=lambda r: (r.kind, r.name)):
            if rec.kind == "enum":
                continue
            names = " ".join(dict.fromkeys(name for name, _ in rec.members))
            out.write(f"{heading(rec)}  ::  {names}\n" if names else f"{heading(rec)}\n")
    with (OUT_DIR / "typelib_enums.txt").open("w", encoding="utf-8") as out:
        for rec in sorted(records, key=lambda r: r.name):
            if rec.kind == "enum":
                out.write(f"{rec.name}: {', '.join(text for _, text in rec.members)}\n")


def write_reaction_api(records: list[TypeRecord]) -> int:
    """相关接口的完整签名，省略各类对象共有的基础成员。返回写出的接口个数。"""
    interfaces = [r for r in records if r.kind in ("dispatch", "interface")]
    counts = Counter(text for r in interfaces for _, text in r.members)
    common = {text for text, n in counts.items() if n >= COMMON_MIN_INTERFACES}
    chosen = [
        r
        for r in sorted(interfaces, key=lambda r: r.name)
        if RELEVANT_INTERFACE.search(r.name) or VARIABLE_MEMBERS & {n for n, _ in r.members}
    ]
    with (OUT_DIR / "typelib_reaction_api.txt").open("w", encoding="utf-8") as out:
        out.write(f"# 省略在 {COMMON_MIN_INTERFACES} 个以上接口里都有的基础成员\n\n")
        for rec in chosen:
            own = [text for _, text in rec.members if text not in common]
            omitted = len(rec.members) - len(own)
            out.write(f"{heading(rec)}  （省略基础成员 {omitted} 个）\n")
            out.writelines(f"    {text}\n" for text in own)
    return len(chosen)


def hits_for(records: list[TypeRecord], keyword: str) -> list[str]:
    key = keyword.lower()
    lines: list[str] = []
    for rec in records:
        if key in rec.name.lower():
            lines.append(
                f"[{rec.kind}] {rec.name}" + (f" : {', '.join(rec.bases)}" if rec.bases else "")
            )
        for member_name, text in rec.members:
            lowered = member_name.lower()
            matched = lowered.startswith(key) if keyword == "Add" else key in lowered
            if matched and rec.kind != "enum":
                lines.append(f"    {rec.name}.{text}")
    return lines


def write_hits(log: Log, records: list[TypeRecord]) -> None:
    with (OUT_DIR / "typelib_hits.txt").open("w", encoding="utf-8") as out:
        for keyword in KEYWORDS:
            lines = hits_for(records, keyword)
            log.say(f"  关键词 {keyword!r}: {len(lines)} 行命中")
            out.write(
                f"===== {keyword}（{len(lines)} 行，最多写 {MAX_HITS_PER_KEYWORD} 行）=====\n"
            )
            out.writelines(f"{line}\n" for line in lines[:MAX_HITS_PER_KEYWORD])


def check_wrapper(log: Log) -> None:
    """生成早绑定包装，并核对几个关键接口的成员。"""
    start = time.time()
    ok, module = log.attempt(
        "gencache.EnsureModule",
        lambda: win32com.client.gencache.EnsureModule(TLB_GUID, TLB_LCID, TLB_MAJOR, TLB_MINOR),
    )
    log.say(f"  用时 {time.time() - start:.1f} 秒；gen_py 目录 {win32com.__gen_path__}")
    if not ok or module is None:
        log.conclude("早绑定包装没有生成成功")
        return
    log.say(f"  模块 {module.__name__}，文件 {getattr(module, '__file__', '?')}")
    log.say(
        f"  CLSIDToClassMap {len(module.CLSIDToClassMap)} 个，"
        f"CLSIDToPackageMap {len(module.CLSIDToPackageMap)} 个，"
        f"VTablesToClassMap {len(module.VTablesToClassMap)} 个"
    )
    for name in WRAPPER_CHECK:
        cls = getattr(module, name, None)
        members = [m for m in dir(cls) if not m.startswith("_")] if cls else []
        log.say(f"  包装类 {name}: {'存在' if cls else '没有'}，公开成员 {len(members)} 个")
        if cls:
            log.say(f"      含 Add: {'Add' in members}；成员: {members[:30]}")


def main() -> None:
    log = Log("typelib_dump")
    tlb = pythoncom.LoadRegTypeLib(TLB_GUID, TLB_MAJOR, TLB_MINOR, TLB_LCID)
    log.say(f"== 类型库 {TLB_GUID} v{TLB_MAJOR}.{TLB_MINOR}，类型数 {tlb.GetTypeInfoCount()} ==")
    records: list[TypeRecord] = []
    for index in range(tlb.GetTypeInfoCount()):
        try:
            records.append(read_type(tlb, index))
        except pythoncom.com_error as exc:
            log.say(f"  第 {index} 个类型读取失败: {exc}")
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.kind] = counts.get(rec.kind, 0) + 1
    log.say(f"  各种类的数量: {counts}")
    write_members(records)
    log.say(f"  typelib_reaction_api.txt 写了 {write_reaction_api(records)} 个接口")
    adders = sorted(r.name for r in records if any(n == "Add" for n, _ in r.members))
    log.say(f"  有 Add 成员的接口共 {len(adders)} 个")
    write_hits(log, records)
    for path in sorted(OUT_DIR.glob("typelib_*.txt")):
        log.say(f"  {path.name}: {path.stat().st_size / 1024:.0f} KB")
    log.say("== 早绑定包装 ==")
    check_wrapper(log)


if __name__ == "__main__":
    main()
