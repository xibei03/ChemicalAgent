"""E9b：Gibbs 反应器的 ReactorType 取值和界面选项怎么对应。

界面上的选项（Support\\OdfRdfVariables.sdb 里的 gibbrctr.ReactionTypeEnum）按顺序是：
  "Gibbs Reactions Only"、"Specify Equilibrium Reactions"、"NO Reactions (=Separator)"
类型库里 GibbsReactorType_enum 是 gr_NoReactions=0、gr_SpecdRxnsOnly=2、gr_GibbsRxnsOnly=3。
新建的 Gibbs 反应器默认读出 3。要靠行为把数字和选项对起来：
  Q1 写 0、1、2、3 哪些写得进去？
  Q2 每个取值下，不挂反应集时出料怎么变？（"NO Reactions" 应当和进料组成相同；
     "Gibbs Reactions Only" 是自由能最小化；"Specify Equilibrium Reactions" 需要平衡反应）
  Q3 取 2 时挂上平衡反应集，结果是否与平衡反应器一致？
做法：打开参考 Case 的副本，对 R-Gibbs 逐个改 ReactorType，读出料和流程图状态，不保存。

用法：python spikes/e9b_gibbs_type.py [--case 路径] [--tag 名字]
输出：spikes/out/e9b_gibbs_type_<tag>.txt
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from _common import Log, new_instance, use_utf8, watch

use_utf8()

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CASE = REPO / "spikes" / "ref_cases" / "three_reactors.hsc"
COMPONENTS = ("Methane", "H2O", "CO", "CO2", "Hydrogen", "Toluene", "Benzene", "p-Xylene")
STATUS_FLAGS = {"OK": 1, "NotSolved": 2, "Warning": 4, "UnderSpecified": 8, "Error": 16}


def show_state(log: Log, case, reactor, label: str) -> None:
    vapour, liquid = reactor.VapourProduct, reactor.LiquidProduct
    fractions = dict(zip(COMPONENTS, vapour.ComponentMolarFraction.Values, strict=True))
    shown = {k: round(v, 4) for k, v in fractions.items() if abs(v) > 1e-9}
    vapour_flow = vapour.MolarFlow.GetValue("kgmole/h")
    liquid_flow = liquid.MolarFlow.GetValue("kgmole/h")
    log.say(
        f"  [{label}] ReactorType={reactor.ReactorType}；"
        f"气相 F={vapour_flow:.2f}，液相 F={liquid_flow:.2f}"
    )
    log.say(f"      气相摩尔分率 {shown}")
    log.attempt("      热负荷 kW", lambda: reactor.EnergyStream.HeatFlow.GetValue("kW"))
    counts = {name: case.GetFlowsheetStatus(flag) for name, flag in STATUS_FLAGS.items()}
    log.say(f"      流程图状态计数 {counts}")
    for name in ("NotSolved", "UnderSpecified", "Warning", "Error"):
        if counts[name]:
            objects = case.GetFlowsheetObjectTypeAndName(STATUS_FLAGS[name])
            log.say(f"      {name} 的对象: {objects}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e9b_gibbs_type_{args.tag}")
    scratch = Path(tempfile.mkdtemp(prefix="hysys_e9b_")).resolve()
    source = Path(args.case).resolve()
    copy = scratch / source.name
    shutil.copyfile(source, copy)
    try:
        with new_instance(log) as (app, _pid):
            with watch(log, "Open"):
                case = app.SimulationCases.Open(str(copy))
            reactor = case.Flowsheet.Operations.Item("R-Gibbs")
            feed = case.Flowsheet.MaterialStreams.Item("F-Gibbs")
            fractions = dict(zip(COMPONENTS, feed.ComponentMolarFraction.Values, strict=True))
            log.say(f"进料摩尔分率 { {k: round(v, 4) for k, v in fractions.items() if v > 0} }")
            show_state(log, case, reactor, "初始")
            log.say("== Q1、Q2 不挂反应集，逐个写 ReactorType ==")
            for value in (0, 1, 2, 3):
                log.attempt(
                    f"ReactorType = {value}",
                    lambda value=value: setattr(reactor, "ReactorType", value),
                )
                show_state(log, case, reactor, f"写 {value}")
            log.say("== Q3 ReactorType = 2，挂上平衡反应集 ==")
            reaction_set = case.BasisManager.ReactionPackageManager.ReactionSets.Item("Eq-Set")
            log.attempt("ReactorType = 2", lambda: setattr(reactor, "ReactorType", 2))
            log.attempt(
                "ReactionSet = Eq-Set", lambda: setattr(reactor, "ReactionSet", reaction_set)
            )
            show_state(log, case, reactor, "类型 2 + Eq-Set")
            log.attempt(
                "ReactorType = 3（再回到纯 Gibbs）", lambda: setattr(reactor, "ReactorType", 3)
            )
            show_state(log, case, reactor, "类型 3 + Eq-Set")
            log.attempt("case.Close()", case.Close)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
