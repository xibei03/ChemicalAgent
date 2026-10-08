"""E4：用代码新建 Case 和 Basis：流体包、物性包、组分，另存、关闭、重开。

要回答的问题：
  Q1 怎么新建空白 Case（SimulationCases.Add 的参数）？新 Case 里是什么状态？
  Q2 要不要把 Basis 的修改包在 StartBasisChange / EndBasisChange 里？
  Q3 怎么新建流体包并指定 Peng-Robinson？物性包的名字在 COM 里是什么字符串？
  Q4 组分怎么加（组分列表？流体包？）？库里的规范名是什么？
  Q5 组分库能不能按名称或分子式检索？
  Q6 另存、关闭、重新打开之后，Basis 还在吗？
做法：新开实例，逐步试，每一步成功和失败都记下来。组分名的写法放进一个临时的组分列表里试，试完删掉。

用法：python spikes/e4_basis.py [--tag 名字]
输出：spikes/out/e4_basis_<tag>.txt；另存的 Case 在临时目录，不提交。
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from _common import Log, first_ok, new_instance, use_utf8, watch

use_utf8()

# 设置时要用物性包的内部名（TypeName）"pengrob"；界面名和读到的名字都会被拒绝（E4b）
PROPERTY_PACKAGE_NAMES = ("pengrob", "Peng-Robinson", "PengRobinson")
# 名称写法：(用途, 候选写法)。每个候选在临时组分列表里试，成功就读回库里的名字
COMPONENT_VARIANTS = (
    ("甲烷", ("Methane", "methane", "CH4", "C1")),
    ("水", ("H2O", "Water", "water")),
    ("一氧化碳", ("CO", "CarbonMonoxide", "Carbon Monoxide")),
    ("二氧化碳", ("CO2", "CarbonDioxide", "Carbon Dioxide")),
    ("氢气", ("Hydrogen", "H2")),
    ("甲苯", ("Toluene", "toluene", "C7H8")),
    ("苯", ("Benzene", "benzene", "C6H6")),
    ("对二甲苯", ("p-Xylene", "P-Xylene", "pXylene", "p-xylene", "PXYLENE")),
    ("间二甲苯", ("m-Xylene", "M-Xylene")),
    ("邻二甲苯", ("o-Xylene", "O-Xylene")),
    ("碳", ("Carbon", "C", "carbon", "Graphite")),
    ("不存在的名字", ("NoSuchComponentXYZ",)),
)


def new_case(log: Log, app, directory: Path):
    """Q1：新建空白 Case。"""
    log.say("== Q1 新建空白 Case ==")
    cases = app.SimulationCases
    log.attempt("SimulationCases.Count（新建前）", lambda: cases.Count)
    target = str(directory / "e4_new.hsc")
    with watch(log, "SimulationCases.Add"):
        ok, case, _ = first_ok(
            log,
            "SimulationCases.Add",
            lambda: cases.Add("e4_new"),
            lambda: cases.Add(target),
            lambda: cases.Add(),
        )
    log.say(f"  Add 的返回类型: {type(case).__name__ if ok else '-'}")
    if not ok:
        return None
    log.attempt("SimulationCases.Count（新建后）", lambda: cases.Count)
    for member in ("FullName", "Visible", "IsDirty", "Title"):
        log.attempt(f"case.{member}", lambda member=member: getattr(case, member))
    log.attempt("app.ActiveDocument", lambda: app.ActiveDocument.FullName)
    manager = case.BasisManager
    for member in ("IsChangingBasis", "CanEndBasisChange"):
        log.attempt(f"BasisManager.{member}", lambda member=member: getattr(manager, member))
    log.attempt("FluidPackages.Count", lambda: manager.FluidPackages.Count)
    log.attempt("ComponentLists.Count", lambda: manager.ComponentLists.Count)
    log.attempt("ComponentLists.Names", lambda: list(manager.ComponentLists.Names))
    return case


def probe_component_names(log: Log, manager) -> None:
    """Q4、Q5：在临时组分列表里逐个试名字，看库里认哪些写法。"""
    log.say("== Q4、Q5 组分名的写法（临时组分列表） ==")
    ok, scratch, _ = first_ok(
        log,
        "ComponentLists.Add('probe-names')",
        lambda: manager.ComponentLists.Add("probe-names"),
        lambda: manager.ComponentLists.Add("probe-names", ""),
    )
    if not ok:
        return
    components = scratch.Components
    for purpose, variants in COMPONENT_VARIANTS:
        for variant in variants:
            before = int(components.Count)
            ok, _ = log.attempt(
                f"[{purpose}] Components.Add({variant!r})", lambda v=variant: components.Add(v)
            )
            if not ok:
                continue
            names = list(components.Names)
            index = len(names) - 1
            for member in ("IsSolid", "IsHypothetical", "Formula", "CAS_Number"):
                log.attempt(
                    f"      {names[index]}.{member}",
                    lambda member=member, index=index: getattr(components.Item(index), member),
                )
            log.say(
                f"      加入后 Count={components.Count}，最后一个 {names[-1]!r}，加之前 {before} 个"
            )
    log.attempt("临时组分列表的全部名字", lambda: list(components.Names))
    log.attempt(
        "ComponentLists.Remove('probe-names')", lambda: manager.ComponentLists.Remove("probe-names")
    )
    log.attempt("ComponentLists.Names（删除后）", lambda: list(manager.ComponentLists.Names))


def build_basis(log: Log, manager):
    """Q2、Q3：真正的组分列表和流体包。"""
    log.say("== Q2、Q3 组分列表和流体包 ==")
    log.attempt("IsChangingBasis", lambda: manager.IsChangingBasis)
    if not manager.IsChangingBasis:
        log.attempt("StartBasisChange()", manager.StartBasisChange)
        log.attempt("IsChangingBasis（开始后）", lambda: manager.IsChangingBasis)
    ok, component_list, _ = first_ok(
        log,
        "ComponentLists.Add('CL-1')",
        lambda: manager.ComponentLists.Add("CL-1"),
        lambda: manager.ComponentLists.Add("CL-1", ""),
    )
    if ok:
        for name in ("Methane", "H2O", "CO", "CO2", "Hydrogen", "Toluene", "Benzene", "p-Xylene"):
            log.attempt(
                f"CL-1.Components.Add({name!r})", lambda n=name: component_list.Components.Add(n)
            )
        log.attempt("CL-1 的组分", lambda: list(component_list.Components.Names))
    ok, package, _ = first_ok(
        log,
        "FluidPackages.Add('Basis-1')",
        lambda: manager.FluidPackages.Add("Basis-1"),
        lambda: manager.FluidPackages.Add("Basis-1", ""),
    )
    if not ok:
        return None
    log.attempt("fp.name", lambda: package.name)
    log.attempt("fp.ComponentList（初值）", lambda: package.ComponentList.name)
    if component_list is not None:
        log.attempt(
            "fp.ComponentList = CL-1", lambda: setattr(package, "ComponentList", component_list)
        )
        log.attempt("fp.ComponentList（设置后）", lambda: package.ComponentList.name)
    log.attempt("fp.PropertyPackageName（初值）", lambda: package.PropertyPackageName)
    for name in PROPERTY_PACKAGE_NAMES:
        ok, _ = log.attempt(
            f"fp.PropertyPackageName = {name!r}",
            lambda n=name: setattr(package, "PropertyPackageName", n),
        )
        log.attempt("  读回 PropertyPackageName", lambda: package.PropertyPackageName)
        if ok:
            break
    for member in ("name", "TypeName", "VisibleTypeName"):
        log.attempt(
            f"fp.PropertyPackage.{member}",
            lambda member=member: getattr(package.PropertyPackage, member),
        )
    log.attempt("fp.Components.Names", lambda: list(package.Components.Names))
    return package


def finish_and_reopen(log: Log, app, case, directory: Path) -> None:
    """Q2、Q6：结束 Basis 修改，另存，关闭，重开。"""
    log.say("== Q2、Q6 结束 Basis 修改、另存、关闭、重开 ==")
    manager = case.BasisManager
    log.attempt("CanEndBasisChange", lambda: manager.CanEndBasisChange)
    log.attempt("EndBasisChange()", manager.EndBasisChange)
    log.attempt("IsChangingBasis（结束后）", lambda: manager.IsChangingBasis)
    log.attempt("Flowsheet.MaterialStreams.Count", lambda: case.Flowsheet.MaterialStreams.Count)
    log.attempt("Solver.CanSolve", lambda: case.Solver.CanSolve)
    path = directory / "e4_saved.hsc"
    log.attempt("case.SaveAs(path)", lambda: case.SaveAs(str(path)))
    log.attempt("case.FullName（另存后）", lambda: case.FullName)
    log.say(
        f"  文件 {path.name} 存在: {path.exists()}，"
        f"{path.stat().st_size // 1024 if path.exists() else 0} KB"
    )
    log.attempt("case.Close()", case.Close)
    with watch(log, "Open(另存的文件)"):
        ok, reopened = log.attempt("Open(另存的文件)", lambda: app.SimulationCases.Open(str(path)))
    if not ok:
        return
    manager = reopened.BasisManager
    log.attempt("重开后 FluidPackages.Names", lambda: list(manager.FluidPackages.Names))
    log.attempt(
        "重开后 PropertyPackageName", lambda: manager.FluidPackages.Item(0).PropertyPackageName
    )
    log.attempt("重开后 组分", lambda: list(manager.FluidPackages.Item(0).Components.Names))
    log.attempt("重开后 IsChangingBasis", lambda: manager.IsChangingBasis)
    log.attempt("reopened.Close()", reopened.Close)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e4_basis_{args.tag}")
    directory = Path(tempfile.mkdtemp(prefix="hysys_e4_")).resolve()
    try:
        with new_instance(log) as (app, _pid):
            case = new_case(log, app, directory)
            if case is None:
                return
            manager = case.BasisManager
            if not manager.IsChangingBasis:
                log.attempt("StartBasisChange()", manager.StartBasisChange)
            probe_component_names(log, manager)
            build_basis(log, manager)
            finish_and_reopen(log, app, case, directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
