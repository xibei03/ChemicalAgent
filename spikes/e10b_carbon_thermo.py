"""E10b（0C 任务 3 的诊断）：Gibbs 反应器里碳的结果为什么不对，看组分库里碳的热力学数据。

e10 的结果：只要进料含固体碳，Gibbs 反应器的结果就与温度无关（1000 至 1600 °C 完全相同），
并且是“全部氧变成 CO、全部氢变成 CH4、氢气为 0”，明显不是 1400 °C 的平衡。
假设：库里的碳（IsSolid 为 True）的生成焓或生成 Gibbs 能不是石墨的 0，
而是别的参考态（比如碳原子气体），
这样碳的化学势特别高，自由能最小化就会把碳尽可能多地转成 CO 和 CH4。

做法：读六个组分的 HeatOfFormation、在几个温度下的 EvaluateGibbs 和 EvaluateIdealH，
对照已知的标准值：298.15 K 的 Gibbs 生成能（kJ/mol）石墨 0、H2 0、CO -137.2、CO2 -394.4、
H2O(g) -228.6、CH4 -50.5，碳原子气体 +671.3。

用法：python spikes/e10b_carbon_thermo.py [--tag 名字]
输出：spikes/out/e10b_carbon_thermo_<tag>.txt
"""

import argparse

from _common import Log, new_instance, use_utf8
from chain_kit import new_case_with_basis

use_utf8()

COMPONENTS = ("Carbon", "H2O", "CO", "Hydrogen", "CO2", "Methane")
TEMPERATURES_K = (298.15, 1000.0, 1673.15, 2000.0)
# 标准 Gibbs 生成能 kJ/mol（298.15 K，教科书值），用来判断单位和参考态
STANDARD_GIBBS_KJ_MOL = {
    "Carbon": 0.0,
    "H2O": -228.6,
    "CO": -137.2,
    "Hydrogen": 0.0,
    "CO2": -394.4,
    "Methane": -50.5,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e10b_carbon_thermo_{args.tag}")
    with new_instance(log) as (app, _pid):
        basis = new_case_with_basis(app, "e10b", COMPONENTS)
        for name in COMPONENTS:
            component = basis.package.Components.Item(name)
            standard = STANDARD_GIBBS_KJ_MOL[name]
            log.say(
                f"-- {name}（IsSolid={component.IsSolid}，标准 Gibbs 生成能约 {standard} kJ/mol）--"
            )
            log.attempt(
                "  HeatOfFormation（kJ/kgmole）",
                lambda component=component: component.HeatOfFormation.GetValue("kJ/kgmole"),
            )
            log.attempt(
                "  Gibbs / 理想气体焓的有效温度范围 K",
                lambda component=component: (
                    component.GibbsTminValue,
                    component.GibbsTmaxValue,
                    component.IdealHTminValue,
                    component.IdealHTmaxValue,
                ),
            )
            for temperature in TEMPERATURES_K:
                log.attempt(
                    f"  EvaluateGibbs({temperature} K)",
                    lambda component=component, temperature=temperature: component.EvaluateGibbs(
                        temperature
                    ),
                )
            for temperature in (298.15, 1673.15):
                log.attempt(
                    f"  EvaluateIdealH({temperature} K)",
                    lambda component=component, temperature=temperature: component.EvaluateIdealH(
                        temperature
                    ),
                )
        carbon = basis.package.Components.Item("Carbon")
        log.say("-- 碳的蒸气压数据（判断固体的化学势有没有被修正） --")
        for temperature in (298.15, 1673.15):
            for method in ("EvaluateVPsublim", "EvaluateAntoine"):
                log.attempt(
                    f"  {method}({temperature} K)",
                    lambda method=method, temperature=temperature: getattr(carbon, method)(
                        temperature
                    ),
                )
        for member in (
            "VPsublimTminValue",
            "VPsublimTmaxValue",
            "AntoineTminValue",
            "AntoineTmaxValue",
        ):
            log.attempt(f"  {member}", lambda member=member: getattr(carbon, member))
        log.attempt(
            "  临界温度 K / 临界压力 kPa",
            lambda: (
                carbon.CriticalTemperature.GetValue("K"),
                carbon.CriticalPressure.GetValue("kPa"),
            ),
        )
        log.attempt("  碳：SolidDensity", lambda: carbon.SolidDensityValue)
        log.attempt(
            "  碳：SolidCp 有效温度范围 K",
            lambda: (
                basis.package.Components.Item("Carbon").SolidCpTminValue,
                basis.package.Components.Item("Carbon").SolidCpTmaxValue,
            ),
        )
        basis.case.Close()


if __name__ == "__main__":
    main()
