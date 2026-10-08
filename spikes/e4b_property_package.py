"""E4b：怎么给流体包指定物性包（Peng-Robinson）。

E4 里 `fp.PropertyPackageName = "<名字>"` 对四种写法都抛 E_INVALIDARG（-2147024809）。
这里换思路逐个试：
  A  FluidPackages.Add(name, Type) 的 Type 传 PropertyPackageType_enum 的数值、枚举名、物性包名
  B  先设物性包、后设组分列表；先设组分列表、后设物性包
  C  PropertyPackageName 的其他写法（HYSYS 界面上的名字、读到的名字的变体）
每种写法用一个新的流体包，试完看 PropertyPackageName、CanEndBasisChange，然后删掉。

用法：python spikes/e4b_property_package.py [--tag 名字]
输出：spikes/out/e4b_property_package_<tag>.txt
"""

import argparse

from _common import Log, new_instance, use_utf8, watch

use_utf8()

PR_ENUM = 5891
TYPE_CANDIDATES = (PR_ENUM, str(PR_ENUM), "ppkg_PR", "Peng-Robinson", "PengRobinson", "PR")
NAME_CANDIDATES = (
    "Peng-Robinson",
    "PengRobinson",
    "Peng Robinson",
    "PR",
    "Peng-Robinson (Aspen)",
    "EOS: Peng-Robinson",
    "ppkg_PR",
    "5891",
    "HYSYS: Peng-Robinson",
    "COMThermo: Peng-Robinson",
    "pengrob",  # 物性包的内部名（TypeName），E4b 里唯一成功的写法
)


def report(log: Log, label: str, package, manager) -> None:
    log.attempt(f"{label}: PropertyPackageName", lambda: package.PropertyPackageName)
    log.attempt(f"{label}: PropertyPackage.TypeName", lambda: package.PropertyPackage.TypeName)
    log.attempt(f"{label}: CanEndBasisChange", lambda: manager.CanEndBasisChange)


def drop(log: Log, manager, name: str) -> None:
    log.attempt(f"FluidPackages.Remove({name!r})", lambda: manager.FluidPackages.Remove(name))


def try_add_types(log: Log, manager) -> None:
    log.say("== A FluidPackages.Add(name, Type)，Type 试各种写法 ==")
    for index, candidate in enumerate(TYPE_CANDIDATES):
        name = f"FP-A{index}"
        ok, package = log.attempt(
            f"FluidPackages.Add({name!r}, {candidate!r})",
            lambda name=name, candidate=candidate: manager.FluidPackages.Add(name, candidate),
        )
        if ok:
            report(log, f"  [{name}]", package, manager)
            drop(log, manager, name)


def try_names(log: Log, manager, component_list) -> None:
    log.say("== B、C PropertyPackageName 的各种写法（有组分列表 / 无组分列表） ==")
    for with_list in (False, True):
        name = f"FP-B{int(with_list)}"
        ok, package = log.attempt(
            f"FluidPackages.Add({name!r})", lambda name=name: manager.FluidPackages.Add(name)
        )
        if not ok:
            continue
        if with_list:
            log.attempt(
                "fp.ComponentList = CL-1",
                lambda package=package: setattr(package, "ComponentList", component_list),
            )
        for candidate in NAME_CANDIDATES:
            ok, _ = log.attempt(
                f"  [{name}] PropertyPackageName = {candidate!r}",
                lambda candidate=candidate, package=package: setattr(
                    package, "PropertyPackageName", candidate
                ),
            )
            if ok:
                report(log, f"  [{name}] 成功后", package, manager)
                break
        drop(log, manager, name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e4b_property_package_{args.tag}")
    with new_instance(log) as (app, _pid):
        with watch(log, "SimulationCases.Add"):
            case = app.SimulationCases.Add("e4b")
        manager = case.BasisManager
        log.attempt("IsChangingBasis", lambda: manager.IsChangingBasis)
        _, component_list = log.attempt(
            "ComponentLists.Add('CL-1')", lambda: manager.ComponentLists.Add("CL-1")
        )
        for name in ("Methane", "H2O", "CO", "CO2", "Hydrogen"):
            log.attempt(f"CL-1 加 {name}", lambda name=name: component_list.Components.Add(name))
        try_add_types(log, manager)
        try_names(log, manager, component_list)
        log.attempt("FluidPackages.Names（试完后）", lambda: list(manager.FluidPackages.Names))
        log.attempt("case.Close()", case.Close)


if __name__ == "__main__":
    main()
