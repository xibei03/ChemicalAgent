"""三个考核场景的独立参照值（不依赖 HYSYS）。

用途：评测体系中 V9 合理性检查的参照来源，以及 docs/MASTER_PLAN.md 第 17 节的期望结果。

方法：理想气体化学平衡。平衡常数由标准生成 Gibbs 自由能（JANAF 表值，按温度线性插值）计算；
场景 1 另用常用关联式 K_SMR = exp(-26830/T + 30.114) [bar^2]、K_WGS = exp(4400/T - 4.036) 交叉核对。

注意：
    1. 这些是量级核对用的参照值，不是 HYSYS 的结果。HYSYS 的物性数据和状态方程会带来小的偏差。
    2. 热力学数据是手工录入的 JANAF 表值，纳入评测前请与原表核对。

依赖 numpy 和 scipy（pip install -e ".[oracle]"）。运行：python evals/oracle/reference_estimates.py
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from scipy.optimize import fsolve

GAS_CONSTANT_KJ_PER_MOL_K = 8.314462e-3
KELVIN_OFFSET = 273.15
NORMAL_MOLAR_VOLUME_NM3_PER_KMOL = 22.414
ATMOSPHERE_BAR = 1.01325

MOLAR_MASS_KG_PER_KMOL = {
    "C": 12.011,
    "H2O": 18.015,
    "CH4": 16.043,
    "NH3": 17.031,
    "toluene": 92.141,
    "benzene": 78.114,
    "xylene": 106.167,
}

# 标准生成 Gibbs 自由能 (kJ/mol)，气相，标准态 1 bar。首列是温度 (K)。
_GIBBS_OF_FORMATION_TABLE = """
T_K      CH4       H2O        CO        CO2
800     -2.115  -203.496  -182.497  -395.586
900      8.616  -198.083  -191.416  -395.748
1000    19.492  -192.590  -200.275  -395.886
1100    30.472  -187.033  -209.075  -396.001
1200    41.524  -181.425  -217.819  -396.098
1300    52.626  -175.774  -226.509  -396.177
1400    63.761  -170.089  -235.149  -396.240
1500    74.918  -164.376  -243.740  -396.288
1600    86.088  -158.639  -252.284  -396.323
1700    97.265  -152.883  -260.784  -396.344
1800   108.445  -147.111  -269.242  -396.353
"""

# 标准生成焓，以及 1600 K 和 1700 K 的显焓 H(T) - H(298 K)，单位 kJ/mol。用于粗估场景 3 的热负荷。
_ENTHALPY_TABLE = """
species  formation  sensible_1600K  sensible_1700K
CO       -110.527      42.385          45.945
H2          0.0        39.541          42.835
H2O      -241.826      52.908          57.758
CO2      -393.522      67.569          73.480
CH4       -74.873      86.910          95.853
C           0.0        25.66           28.08
"""


def _parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """把空白分隔的文本表解析成表头和数据行。"""
    header, *rows = (line.split() for line in text.strip().splitlines())
    return header, rows


def _load_gibbs_table() -> tuple[tuple[float, ...], dict[str, tuple[float, ...]]]:
    """返回温度序列，以及每个组分在这些温度下的生成 Gibbs 自由能。"""
    header, rows = _parse_table(_GIBBS_OF_FORMATION_TABLE)
    columns = list(zip(*([float(cell) for cell in row] for row in rows), strict=True))
    return columns[0], dict(zip(header[1:], columns[1:], strict=True))


def _load_enthalpy_table() -> dict[str, tuple[float, float, float]]:
    """返回每个组分的（生成焓，1600 K 显焓，1700 K 显焓）。"""
    _, rows = _parse_table(_ENTHALPY_TABLE)
    return {row[0]: (float(row[1]), float(row[2]), float(row[3])) for row in rows}


JANAF_TEMPERATURES_K, JANAF_GIBBS_OF_FORMATION_KJ_PER_MOL = _load_gibbs_table()
ENTHALPY_DATA_KJ_PER_MOL = _load_enthalpy_table()
LIQUID_WATER_ENTHALPY_OF_FORMATION_KJ_PER_MOL = -285.830
LIQUID_WATER_HEAT_CAPACITY_KJ_PER_MOL_K = 0.0753
CARBON_HEAT_CAPACITY_KJ_PER_MOL_K = 0.0085
REFERENCE_TEMPERATURE_C = 25.0

EquilibriumConstants = Callable[[float], tuple[float, float]]


def gibbs_of_formation(species: str, temperature_k: float) -> float:
    """按温度线性插值 JANAF 表，返回标准生成 Gibbs 自由能 (kJ/mol)。"""
    table = JANAF_GIBBS_OF_FORMATION_KJ_PER_MOL[species]
    return float(np.interp(temperature_k, JANAF_TEMPERATURES_K, table))


def equilibrium_constant(delta_gibbs_kj_per_mol: float, temperature_k: float) -> float:
    """由反应的标准 Gibbs 自由能变计算平衡常数。"""
    return float(np.exp(-delta_gibbs_kj_per_mol / (GAS_CONSTANT_KJ_PER_MOL_K * temperature_k)))


def format_values(values: Mapping[str, float], digits: int = 4) -> str:
    """把"名称 → 数值"格式化成一行文本。"""
    return ", ".join(f"{name} {value:.{digits}f}" for name, value in values.items())


# --------------------------------------------------------------------------- 场景 1
def reforming_constants_from_janaf(temperature_k: float) -> tuple[float, float]:
    """重整反应 (bar^2) 和变换反应的平衡常数，由 JANAF 数据计算。"""
    gibbs = {name: gibbs_of_formation(name, temperature_k) for name in ("CH4", "H2O", "CO", "CO2")}
    k_reforming = equilibrium_constant(gibbs["CO"] - gibbs["CH4"] - gibbs["H2O"], temperature_k)
    k_shift = equilibrium_constant(gibbs["CO2"] - gibbs["CO"] - gibbs["H2O"], temperature_k)
    return k_reforming, k_shift


def reforming_constants_from_correlation(temperature_k: float) -> tuple[float, float]:
    """重整反应 (bar^2) 和变换反应的平衡常数，由常用关联式计算。"""
    k_reforming = float(np.exp(-26830 / temperature_k + 30.114))
    k_shift = float(np.exp(4400 / temperature_k - 4.036))
    return k_reforming, k_shift


@dataclass(frozen=True)
class ReformingResult:
    """甲烷蒸汽重整的平衡结果，基准为 1 mol CH4 进料。"""

    k_reforming: float
    k_shift: float
    methane_conversion: float
    outlet_to_inlet_mole_ratio: float
    wet_mole_fractions: dict[str, float]
    dry_mole_fractions: dict[str, float]
    h2_to_co: float


def reforming_outlet_moles(
    steam_to_carbon: float, reforming_extent: float, shift_extent: float
) -> dict[str, float]:
    """由两个反应的进度得到出口各组分的摩尔数，基准为 1 mol CH4。"""
    return {
        "CH4": 1 - reforming_extent,
        "H2O": steam_to_carbon - reforming_extent - shift_extent,
        "CO": reforming_extent - shift_extent,
        "H2": 3 * reforming_extent + shift_extent,
        "CO2": shift_extent,
    }


def solve_reforming(
    temperature_c: float,
    pressure_bar: float,
    steam_to_carbon: float = 2.7,
    constants: EquilibriumConstants = reforming_constants_from_janaf,
) -> ReformingResult:
    """联立求解重整反应和变换反应的平衡。"""
    k_reforming, k_shift = constants(temperature_c + KELVIN_OFFSET)

    def residual(extents: np.ndarray) -> list[float]:
        moles = reforming_outlet_moles(steam_to_carbon, extents[0], extents[1])
        total = sum(moles.values())
        log = {name: np.log(value) for name, value in moles.items()}
        reforming = (
            log["CO"] + 3 * log["H2"] - log["CH4"] - log["H2O"] + 2 * np.log(pressure_bar / total)
        )
        shift = log["CO2"] + log["H2"] - log["CO"] - log["H2O"]
        return [float(reforming - np.log(k_reforming)), float(shift - np.log(k_shift))]

    extents = _first_physical_root(residual, steam_to_carbon)
    moles = reforming_outlet_moles(steam_to_carbon, extents[0], extents[1])
    total = sum(moles.values())
    dry_total = total - moles["H2O"]
    return ReformingResult(
        k_reforming=k_reforming,
        k_shift=k_shift,
        methane_conversion=extents[0],
        outlet_to_inlet_mole_ratio=total / (1 + steam_to_carbon),
        wet_mole_fractions={name: value / total for name, value in moles.items()},
        dry_mole_fractions={
            name: value / dry_total for name, value in moles.items() if name != "H2O"
        },
        h2_to_co=moles["H2"] / moles["CO"],
    )


def _first_physical_root(
    residual: Callable[[np.ndarray], list[float]], steam_to_carbon: float
) -> tuple[float, float]:
    """从多个初值出发求解，返回第一个所有摩尔数为正的解。"""
    for reforming_guess in np.linspace(0.05, 0.95, 19):
        for shift_share in (0.2, 0.4, 0.6, 0.8):
            with np.errstate(all="ignore"):
                root = fsolve(
                    residual, [reforming_guess, reforming_guess * shift_share], xtol=1e-13
                )
                moles = reforming_outlet_moles(steam_to_carbon, root[0], root[1])
                converged = np.allclose(residual(root), 0, atol=1e-8)
            if converged and min(moles.values()) > 0:
                return float(root[0]), float(root[1])
    raise RuntimeError("没有找到物理上有意义的平衡解")


def print_scenario_1() -> None:
    """场景 1：甲烷蒸汽重整，两个出口温度工况。"""
    pressure_bar, steam_to_carbon = 13.5, 2.7
    print("=== 场景 1  甲烷蒸汽重整：CH4:H2O = 1:2.7（摩尔），13.5 bar，出口 710 / 600 °C ===")
    sources = (
        ("JANAF", reforming_constants_from_janaf),
        ("关联式", reforming_constants_from_correlation),
    )
    for source_name, constants in sources:
        for temperature_c in (710.0, 600.0):
            result = solve_reforming(temperature_c, pressure_bar, steam_to_carbon, constants)
            print(
                f"[{source_name}] {temperature_c:.0f} °C  K_smr={result.k_reforming:.4g} bar^2  "
                f"K_wgs={result.k_shift:.4g}  CH4 转化率={result.methane_conversion * 100:.1f}%  "
                f"H2/CO={result.h2_to_co:.2f}  n_out/n_in={result.outlet_to_inlet_mole_ratio:.4f}"
            )
            print("    湿基:", format_values(result.wet_mole_fractions))
            print("    干基:", format_values(result.dry_mole_fractions))
    for temperature_c in (710.0, 600.0):  # 敏感性：若 13.5 bar 是表压
        gauge = solve_reforming(temperature_c, pressure_bar + ATMOSPHERE_BAR)
        conversion_percent = gauge.methane_conversion * 100
        print(f"[JANAF，按表压计] {temperature_c:.0f} °C  CH4 转化率={conversion_percent:.1f}%")
    _print_reforming_flow_basis(methane_kmol_h=1000.0, steam_to_carbon=steam_to_carbon)


def _print_reforming_flow_basis(methane_kmol_h: float, steam_to_carbon: float) -> None:
    """打印假设的进料流量基准及其折算的年处理量。"""
    operating_hours_per_year = 8000
    methane_per_ammonia = 0.442  # 化学计量下每摩尔合成氨消耗的甲烷
    normal_flow_nm3_h = methane_kmol_h * NORMAL_MOLAR_VOLUME_NM3_PER_KMOL
    ammonia_kt_per_year = (
        methane_kmol_h
        / methane_per_ammonia
        * MOLAR_MASS_KG_PER_KMOL["NH3"]
        * operating_hours_per_year
        / 1e6
    )
    print(
        f"流量基准: CH4 {methane_kmol_h:.0f} kmol/h = {normal_flow_nm3_h:.0f} Nm3/h = "
        f"{methane_kmol_h * MOLAR_MASS_KG_PER_KMOL['CH4'] / 1000:.2f} t/h；"
        f"蒸汽 {steam_to_carbon * methane_kmol_h:.0f} kmol/h；"
        f"合计 {(1 + steam_to_carbon) * methane_kmol_h:.0f} kmol/h"
    )
    annual_normal_flow_1e8_nm3 = normal_flow_nm3_h * operating_hours_per_year / 1e8
    print(
        f"年量（{operating_hours_per_year} h）: CH4 {annual_normal_flow_1e8_nm3:.2f} 亿 Nm3/a；"
        f"折合合成氨约 {ammonia_kt_per_year:.0f} kt/a"
    )


# --------------------------------------------------------------------------- 场景 2
def print_scenario_2() -> None:
    """场景 2：甲苯歧化，按计量关系直接计算。"""
    feed_kg_h, conversion = 10000.0, 0.50
    xylene_split = {"对二甲苯": 0.24, "间二甲苯": 0.52, "邻二甲苯": 0.24}  # 假设
    print("\n=== 场景 2  甲苯歧化：10000 kg/h，转化率 50%，二甲苯 对:间:邻 = 24:52:24（假设） ===")
    feed_kmol_h = feed_kg_h / MOLAR_MASS_KG_PER_KMOL["toluene"]
    reacted_kmol_h = feed_kmol_h * conversion
    outlet = {
        "甲苯": (feed_kmol_h - reacted_kmol_h, MOLAR_MASS_KG_PER_KMOL["toluene"]),
        "苯": (reacted_kmol_h / 2, MOLAR_MASS_KG_PER_KMOL["benzene"]),
    }
    for isomer, share in xylene_split.items():
        outlet[isomer] = (reacted_kmol_h / 2 * share, MOLAR_MASS_KG_PER_KMOL["xylene"])
    total_kmol_h = sum(flow for flow, _ in outlet.values())
    print(f"进料甲苯 {feed_kmol_h:.2f} kmol/h；出口合计 {total_kmol_h:.2f} kmol/h（总摩尔数不变）")
    for name, (flow_kmol_h, molar_mass) in outlet.items():
        print(
            f"   {name}: {flow_kmol_h:7.2f} kmol/h   x={flow_kmol_h / total_kmol_h:.3f}   "
            f"{flow_kmol_h * molar_mass:7.0f} kg/h"
        )
    print(f"   出口质量合计 {sum(flow * mass for flow, mass in outlet.values()):.0f} kg/h")


# --------------------------------------------------------------------------- 场景 3
@dataclass(frozen=True)
class SlurryFeed:
    """水煤浆进料，煤按纯碳处理。"""

    carbon_kmol_h: float
    water_kmol_h: float


@dataclass(frozen=True)
class GasificationResult:
    """气化平衡结果。固体碳过量，活度取 1。"""

    k_carbon_steam: float
    k_boudouard: float
    k_methanation: float
    gas_kmol_h: dict[str, float]
    unreacted_carbon_kmol_h: float


def slurry_feed(normal_flow_nm3_h: float, carbon_mass_fraction: float) -> SlurryFeed:
    """把"标准体积流量 + 质量浓度"换算成碳和水的摩尔流量。"""
    total_kmol_h = normal_flow_nm3_h / NORMAL_MOLAR_VOLUME_NM3_PER_KMOL
    carbon_kmol_per_kg = carbon_mass_fraction / MOLAR_MASS_KG_PER_KMOL["C"]
    water_kmol_per_kg = (1 - carbon_mass_fraction) / MOLAR_MASS_KG_PER_KMOL["H2O"]
    carbon_mole_fraction = carbon_kmol_per_kg / (carbon_kmol_per_kg + water_kmol_per_kg)
    return SlurryFeed(
        carbon_kmol_h=total_kmol_h * carbon_mole_fraction,
        water_kmol_h=total_kmol_h * (1 - carbon_mole_fraction),
    )


def solve_gasification(
    feed: SlurryFeed, temperature_c: float, pressure_bar: float
) -> GasificationResult:
    """求解 C-H-O 体系在固体碳过量时的气相平衡。"""
    temperature_k = temperature_c + KELVIN_OFFSET
    gibbs = {name: gibbs_of_formation(name, temperature_k) for name in ("CH4", "H2O", "CO", "CO2")}
    # 三个独立反应依次是：C + H2O = CO + H2，C + CO2 = 2 CO，C + 2 H2 = CH4
    k_carbon_steam = equilibrium_constant(gibbs["CO"] - gibbs["H2O"], temperature_k)
    k_boudouard = equilibrium_constant(2 * gibbs["CO"] - gibbs["CO2"], temperature_k)
    k_methanation = equilibrium_constant(gibbs["CH4"], temperature_k)
    oxygen_kmol_h, hydrogen_kmol_h = feed.water_kmol_h, 2 * feed.water_kmol_h

    def residual(log_moles: np.ndarray) -> list[float]:
        co, h2, h2o, co2, ch4 = np.exp(log_moles)
        pressure_over_total = pressure_bar / (co + h2 + h2o + co2 + ch4)
        return [
            float(np.log(co * h2 / h2o * pressure_over_total / k_carbon_steam)),
            float(np.log(co * co / co2 * pressure_over_total / k_boudouard)),
            float(np.log(ch4 / (h2 * h2) / pressure_over_total / k_methanation)),
            float((co + h2o + 2 * co2) / oxygen_kmol_h - 1),  # 氧元素守恒
            float((2 * h2 + 2 * h2o + 4 * ch4) / hydrogen_kmol_h - 1),  # 氢元素守恒
        ]

    water = feed.water_kmol_h
    guess = np.log([water * 0.97, water * 0.95, water * 0.01, water * 0.005, water * 0.01])
    root = fsolve(residual, guess, xtol=1e-13)
    if not np.allclose(residual(root), 0, atol=1e-8):
        raise RuntimeError("气化平衡没有收敛")
    gas_kmol_h = dict(
        zip(("CO", "H2", "H2O", "CO2", "CH4"), (float(v) for v in np.exp(root)), strict=True)
    )
    unreacted = feed.carbon_kmol_h - gas_kmol_h["CO"] - gas_kmol_h["CO2"] - gas_kmol_h["CH4"]
    if unreacted <= 0:
        raise RuntimeError("碳不过量，固体碳活度为 1 的假设不成立")
    return GasificationResult(k_carbon_steam, k_boudouard, k_methanation, gas_kmol_h, unreacted)


def external_heat_mw(
    feed: SlurryFeed,
    result: GasificationResult,
    feed_temperature_c: float,
    outlet_temperature_c: float,
) -> float:
    """粗估把进料加热并反应到出口状态所需的外供热 (MW)。"""
    weight = (outlet_temperature_c + KELVIN_OFFSET - 1600) / 100
    outlet_enthalpy = {
        name: formation + at_1600k + weight * (at_1700k - at_1600k)
        for name, (formation, at_1600k, at_1700k) in ENTHALPY_DATA_KJ_PER_MOL.items()
    }
    outlet_mj_h = sum(flow * outlet_enthalpy[name] for name, flow in result.gas_kmol_h.items())
    outlet_mj_h += result.unreacted_carbon_kmol_h * outlet_enthalpy["C"]
    temperature_rise_k = feed_temperature_c - REFERENCE_TEMPERATURE_C
    water_enthalpy = (
        LIQUID_WATER_ENTHALPY_OF_FORMATION_KJ_PER_MOL
        + LIQUID_WATER_HEAT_CAPACITY_KJ_PER_MOL_K * temperature_rise_k
    )
    carbon_enthalpy = CARBON_HEAT_CAPACITY_KJ_PER_MOL_K * temperature_rise_k
    feed_mj_h = feed.water_kmol_h * water_enthalpy + feed.carbon_kmol_h * carbon_enthalpy
    return (outlet_mj_h - feed_mj_h) / 3600


def print_scenario_3() -> None:
    """场景 3：水煤浆气化，煤按纯碳处理，按题面不加氧气。"""
    feed_temperature_c, outlet_temperature_c, pressure_bar = 40.0, 1400.0, 40.0
    print(
        "\n=== 场景 3  水煤浆气化：80000 Nm3/h（总摩尔流量），62 wt%，1400 °C，40 bar，无氧气 ==="
    )
    feed = slurry_feed(normal_flow_nm3_h=80000.0, carbon_mass_fraction=0.62)
    carbon_t_h = feed.carbon_kmol_h * MOLAR_MASS_KG_PER_KMOL["C"] / 1000
    water_t_h = feed.water_kmol_h * MOLAR_MASS_KG_PER_KMOL["H2O"] / 1000
    print(
        f"进料: C {feed.carbon_kmol_h:.0f} kmol/h"
        f"（{carbon_t_h:.1f} t/h，约 {carbon_t_h * 24:.0f} t/d）；"
        f"H2O {feed.water_kmol_h:.0f} kmol/h（{water_t_h:.1f} t/h）；"
        f"C:H2O = {feed.carbon_kmol_h / feed.water_kmol_h:.2f}"
    )
    result = solve_gasification(feed, outlet_temperature_c, pressure_bar)
    gas = result.gas_kmol_h
    total_gas = sum(gas.values())
    gasified = gas["CO"] + gas["CO2"] + gas["CH4"]
    print(
        f"K(C+H2O)={result.k_carbon_steam:.4g} bar，K(C+CO2)={result.k_boudouard:.4g} bar，"
        f"K(C+2H2)={result.k_methanation:.4g} 1/bar"
    )
    print("出口气体 kmol/h:", format_values(gas, 1), f"；合计 {total_gas:.0f}")
    print(
        "出口气体摩尔分率:", format_values({name: flow / total_gas for name, flow in gas.items()})
    )
    print(
        f"未反应固体碳 {result.unreacted_carbon_kmol_h:.0f} kmol/h"
        f"（占进料碳 {result.unreacted_carbon_kmol_h / feed.carbon_kmol_h * 100:.0f}%）"
    )
    print(
        f"CO 收率（出口 CO / 进料 C）= {gas['CO'] / feed.carbon_kmol_h * 100:.1f}%；"
        f"碳转化率 = {gasified / feed.carbon_kmol_h * 100:.1f}%；"
        f"水量决定的 CO 收率上限 = {feed.water_kmol_h / feed.carbon_kmol_h * 100:.1f}%"
    )
    heat_mw = external_heat_mw(feed, result, feed_temperature_c, outlet_temperature_c)
    print(f"所需外供热（粗估）= {heat_mw:.0f} MW；真实气化炉由氧气部分氧化提供")


if __name__ == "__main__":
    print_scenario_1()
    print_scenario_2()
    print_scenario_3()
