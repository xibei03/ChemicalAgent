"""E9（0C 任务 2）：Gibbs 反应器，纯气相，不建反应、不挂反应集，用纯自由能最小化模式。

模型：任务 1（E8）的进料和组分，Gibbs 反应器 GBR-100，带能流，出口温度 710 °C。
五个组分、三种元素恰好对应两个独立反应，结果应当与 E8 的平衡反应器 710 °C 工况很接近。
同一个 Case 里再做三个对照：
  ERV-100  平衡反应器 710 °C（E8 的做法，同一个 Case 里直接对比）
  GBR-MULTI  把进料拆成甲烷和水蒸气两股，分别接进 Gibbs 反应器，出口 710 °C
  GBR-GADI / ERV-EADI  都不接能流（绝热），比较两种反应器算出的出口温度

要回答的问题：
  Q1 Gibbs 模式怎么设置（ReactorType 默认值）？不挂反应集能不能求解？与参照值、平衡反应器差多少？
  Q2 多股进料怎么接（Feeds.Add 调用几次）？结果与单股混合进料一致吗？
  Q3 绝热模式（不接能流）能求解吗？出口温度是计算值吗？与平衡反应器一致吗？

用法：python spikes/e9_gibbs_gas.py [--tag 名字]
输出：spikes/out/e9_gibbs_gas_<tag>.txt；Case 另存为同名 .hsc。
"""

import argparse
import traceback

from _common import OUT_DIR, Log, new_instance, use_utf8, watch
from chain_kit import (
    Basis,
    add_reactor,
    make_feed,
    mass_balance_error,
    new_case_with_basis,
    read_stream,
    status_counts,
)
from e8_equilibrium_chain import (
    COMPONENTS,
    FEED_FLOW_KMOL_H,
    FEED_FRACTIONS,
    FEED_PRESSURE_KPA,
    FEED_TEMPERATURE_C,
    FRACTION_TOLERANCE,
    REFERENCE,
    Train,
    build_train,
    conversion_of_methane,
    step_reactions,
)

use_utf8()

GIBBS_TYPE = "GibbsReactorOp"
CLOSE_TOLERANCE = 0.005  # Gibbs 与平衡反应器、多股与单股，摩尔分率最大差的容差
ADIABATIC_TEMPERATURE_TOLERANCE_C = 5.0


def build_gibbs_train(flowsheet, basis: Basis, tag: str, feeds, with_energy: bool) -> Train:
    """Gibbs 反应器：多股进料、两股出料、可选的能流，不挂反应集。"""
    vapour = flowsheet.MaterialStreams.Add(f"Vap{tag}")
    liquid = flowsheet.MaterialStreams.Add(f"Liq{tag}")
    energy = flowsheet.EnergyStreams.Add(f"Q{tag}") if with_energy else None
    reactor = add_reactor(flowsheet, f"GBR{tag}", GIBBS_TYPE, feeds, vapour, liquid, energy)
    return Train(reactor, feeds[0], vapour, liquid, energy)


def single_feed(flowsheet, basis: Basis, name: str):
    return make_feed(
        flowsheet,
        basis,
        name,
        FEED_TEMPERATURE_C,
        FEED_PRESSURE_KPA,
        FEED_FRACTIONS,
        FEED_FLOW_KMOL_H,
    )


def split_feeds(flowsheet, basis: Basis, suffix: str) -> tuple[object, object]:
    """把进料拆成甲烷和水蒸气两股，条件与单股进料相同。"""
    methane = make_feed(
        flowsheet,
        basis,
        f"FeedCH4{suffix}",
        FEED_TEMPERATURE_C,
        FEED_PRESSURE_KPA,
        {"Methane": 1.0},
        FEED_FLOW_KMOL_H * FEED_FRACTIONS["Methane"],
    )
    steam = make_feed(
        flowsheet,
        basis,
        f"FeedH2O{suffix}",
        FEED_TEMPERATURE_C,
        FEED_PRESSURE_KPA,
        {"H2O": 1.0},
        FEED_FLOW_KMOL_H * FEED_FRACTIONS["H2O"],
    )
    return methane, steam


def describe(log: Log, label: str, train: Train, basis: Basis, feeds) -> dict[str, object]:
    outlet = read_stream(train.vapour, basis.components)
    error = mass_balance_error(feeds, train.vapour, train.liquid)
    shown = {k: round(v, 4) for k, v in outlet["fractions"].items()}
    log.say(f"  -- {label} --")
    log.say(
        f"    气相 T={outlet['T_C']:.2f} C，F={outlet['kmol_h']:.2f} kgmole/h，"
        f"液相 F={train.liquid.MolarFlow.GetValue('kgmole/h'):.4f}；质量守恒误差 {error:.2e}"
    )
    log.say(f"    摩尔分率 {shown}；CH4 转化率 {conversion_of_methane(outlet):.1%}")
    if train.energy is not None:
        log.say(f"    能流热负荷 {train.energy.HeatFlow.GetValue('kW'):.1f} kW")
    return outlet


def max_difference(first: dict[str, object], second: dict[str, object]) -> float:
    return max(abs(first["fractions"][k] - second["fractions"][k]) for k in first["fractions"])


def run_main(log: Log, flowsheet, basis: Basis, reaction_set) -> tuple[bool, dict[str, object]]:
    """Q1：Gibbs 纯自由能最小化，710 °C，与参照值和同一个 Case 里的平衡反应器对比。"""
    log.say("== Q1 Gibbs 反应器，不挂反应集，出口 710 C ==")
    gibbs = build_gibbs_train(
        flowsheet, basis, "-100", (single_feed(flowsheet, basis, "Feed-G"),), True
    )
    log.say(f"  ReactorType 默认值 {gibbs.reactor.ReactorType}（3 = Gibbs Reactions Only）")
    log.attempt("  ReactionSet（没挂）", lambda: gibbs.reactor.ReactionSet)
    log.say(f"  连接完、没规定出口温度时的状态 {status_counts(basis.case)}")
    gibbs.vapour.Temperature.SetValue(710.0, "C")
    gibbs_out = describe(log, "Gibbs 710 C", gibbs, basis, (gibbs.feed,))
    equilibrium = build_train(flowsheet, basis, "-E", reaction_set, with_energy=True)
    equilibrium.vapour.Temperature.SetValue(710.0, "C")
    equilibrium_out = describe(
        log, "平衡反应器 710 C（对照）", equilibrium, basis, (equilibrium.feed,)
    )
    fractions, total = REFERENCE[710.0]
    worst_reference = max(abs(gibbs_out["fractions"][k] - v) for k, v in fractions.items())
    worst_equilibrium = max_difference(gibbs_out, equilibrium_out)
    ok_reference = worst_reference <= FRACTION_TOLERANCE
    ok_equilibrium = worst_equilibrium <= CLOSE_TOLERANCE
    log.say(
        f"    [{'通过' if ok_reference else '未通过'}] 与参照值最大偏差 {worst_reference:.4f} "
        f"≤ {FRACTION_TOLERANCE}；总流量 {gibbs_out['kmol_h']:.1f}（参照约 {total:.0f}）"
    )
    log.say(
        f"    [{'通过' if ok_equilibrium else '未通过'}] 与平衡反应器最大偏差 "
        f"{worst_equilibrium:.5f} ≤ {CLOSE_TOLERANCE}"
    )
    log.say(f"  流程图状态 {status_counts(basis.case)}")
    return ok_reference and ok_equilibrium, gibbs_out


def run_multi_feed(log: Log, flowsheet, basis: Basis, single: dict[str, object]) -> bool:
    """Q2：两股进料分别接进 Gibbs 反应器。"""
    log.say("== Q2 多股进料：甲烷一股、水蒸气一股（GBR-MULTI） ==")
    feeds = split_feeds(flowsheet, basis, "-M")
    train = build_gibbs_train(flowsheet, basis, "-MULTI", feeds, True)
    log.attempt("  Feeds.Names", lambda: list(train.reactor.Feeds.Names))
    train.vapour.Temperature.SetValue(710.0, "C")
    outlet = describe(log, "两股进料 710 C", train, basis, feeds)
    diff = max_difference(outlet, single)
    passed = diff <= CLOSE_TOLERANCE
    log.say(
        f"    [{'通过' if passed else '未通过'}] 与单股进料最大偏差 {diff:.5f} ≤ {CLOSE_TOLERANCE}"
    )
    return passed


def run_adiabatic(log: Log, flowsheet, basis: Basis, reaction_set) -> bool:
    """Q3：Gibbs 和平衡反应器都不接能流，比较出口温度。"""
    log.say("== Q3 绝热（不接能流）：GBR-GADI 与 ERV-EADI ==")
    gibbs = build_gibbs_train(
        flowsheet, basis, "-GADI", (single_feed(flowsheet, basis, "Feed-GA"),), False
    )
    gibbs_out = describe(log, "Gibbs 绝热", gibbs, basis, (gibbs.feed,))
    equilibrium = build_train(flowsheet, basis, "-EADI", reaction_set, with_energy=False)
    equilibrium_out = describe(
        log, "平衡反应器绝热（对照）", equilibrium, basis, (equilibrium.feed,)
    )
    diff_t = abs(gibbs_out["T_C"] - equilibrium_out["T_C"])
    diff_x = max_difference(gibbs_out, equilibrium_out)
    passed = diff_t <= ADIABATIC_TEMPERATURE_TOLERANCE_C and diff_x <= CLOSE_TOLERANCE
    log.say(
        f"    [{'通过' if passed else '未通过'}] 出口温度差 {diff_t:.2f} C "
        f"≤ {ADIABATIC_TEMPERATURE_TOLERANCE_C}，摩尔分率最大差 {diff_x:.5f} ≤ {CLOSE_TOLERANCE}"
    )
    log.say(
        f"    出口温度是计算值: State={gibbs.vapour.Temperature.State}，"
        f"CanModify={gibbs.vapour.Temperature.CanModify}"
    )
    log.say(f"  流程图状态 {status_counts(basis.case)}")
    return passed


def run_once(log: Log, save_path) -> bool:
    with new_instance(log) as (app, _pid):
        with watch(log, "建 Basis"):
            basis = new_case_with_basis(app, "e9_gibbs", COMPONENTS)
        reaction_set = step_reactions(log, basis)  # 只给对照用的平衡反应器；Gibbs 反应器不挂它
        basis.manager.EndBasisChange()
        flowsheet = basis.case.Flowsheet
        ok_main, single = run_main(log, flowsheet, basis, reaction_set)
        ok_multi = run_multi_feed(log, flowsheet, basis, single)
        ok_adiabatic = run_adiabatic(log, flowsheet, basis, reaction_set)
        basis.case.SaveAs(str(save_path))
        log.say(f"  Case 已另存为 {save_path}")
        basis.case.Close()
        return ok_main and ok_multi and ok_adiabatic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e9_gibbs_gas_{args.tag}")
    try:
        passed = run_once(log, OUT_DIR / f"e9_gibbs_gas_{args.tag}.hsc")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    log.say(f"== E9 {'通过' if passed else '未通过'}：主工况、多股进料、绝热三项={passed} ==")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
