"""E6c（0B 任务 5 的补充）：反应集的排序（Conversion Rankings）能不能用 COM 读写，排序是什么含义。

e6b 的结果：类型库里没有排序成员；flags=0 调 ApplyXMLForOperation 返回 False，还弄坏了 Case。
要回答的问题：
  Q1 ProvideXMLForOperation 的 flags 是位掩码（opt_SupplyMonikers=8 等）。不同 flags 导出的 XML
     里，排序节点是什么样，带 8 时有没有 moniker？
  Q2 BackDoor 能不能按 moniker 读到排序？moniker 的写法用进料的温度校准（它的值已知）。
  Q3 能不能用 BackDoor 的变量把排序写进去？
  Q4 带 flags 的 ApplyXMLForOperation 能不能把排序写进去？它到底能改哪些变量？
  Q5 ActiveReactions.Add 的第二个参数会不会被当成排序？
  Q6 示例 Case 是 AspenTech 在界面里建的，里面有非零、互不相同的排序值。从它的排序值和各反应
     实际起作用的转化率，能不能看出排序的含义？（不需要自己写入排序。）
做法：沿用 e6b 的三个并行转化反应的模型。读的实验共用一个 Case；每个写的实验用一个新 Case。

用法：python spikes/e6c_rank_channels.py [--tag 名字]
输出：spikes/out/e6c_rank_channels_<tag>.txt
"""

import argparse
import re
import shutil
import tempfile
from pathlib import Path

import pythoncom
import pywintypes
from _common import Log, dialog_guard, new_instance, use_utf8, watch
from e6b_parallel_reactions import (
    MIXED_TOLUENE_FRACTION,
    REACTIONS,
    SEQUENTIAL_TOLUENE_FRACTION,
    basis,
    build_model,
    feed_composition,
    full_rank_xml,
    minimal_rank_xml,
    read_ranks,
    report,
    step_end_basis,
    step_feed,
    step_new_case,
    step_outlets,
    step_reactor,
)

use_utf8()

XML_FLAGS = (0, 1, 2, 8, 9, 16, 128, 129, 2048, 4096, 8192, 8 + 2048)
APPLY_FLAGS = (8, 9, 128, 129, 137)
FULL_XML_FLAGS = (1, 2, 16, 128, 144)
CASE_LEVEL_FLAGS = (0, 128, 137)
RANK_ELEMENT = re.compile(r"<ReactionRank\b[^>]*>.*?</ReactionRank>", re.DOTALL)
RANK_COUNT = 3
MONIKER_FORMS = (":Index.400.{i}", ":Index.400.[{i}]", ".Index.400.{i}")
FEED_TEMPERATURE_SUFFIXES = (":Temperature.501.0", ".Temperature.501.0", ":Temperature.0")
WRITE_EXPERIMENTS = (
    ((0.0, 1.0, 2.0), f"依次：预测甲苯 {SEQUENTIAL_TOLUENE_FRACTION:.4f}"),
    ((1.0, 1.0, 0.0), f"第三个先算，前两个并行：预测甲苯 {MIXED_TOLUENE_FRACTION:.4f}"),
    ((2.0, 1.0, 0.0), f"倒序依次：预测甲苯 {SEQUENTIAL_TOLUENE_FRACTION:.4f}"),
    ((5.0, 5.0, 5.0), "三个相同的非零值：预测并行 0.5000"),
)
DELTA_P_NODE = re.compile(
    r'(<DeltaP OwnerType="ConversionReactorOpObject" OwnerName="CRV-100" Type="Param">\s*<Value>)'
    r"[^<]*(</Value>)"
)
FEED_TEMPERATURE_NODE = re.compile(
    r'(<Temperature OwnerType="MaterialStreamObject" OwnerName="Feed" Type="Param">\s*<Value>)'
    r"[^<]*(</Value>)"
)
SAMPLE_CASE = Path(
    r"C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc"
)
SAMPLE_REACTORS = ("Reformer", "Combustor")
RATIO_TOLERANCE = 1e-3


def reaction_set_path(model) -> str:
    """反应集的 UniqueID，拼 moniker 时当所有者路径用。"""
    return str(model.reaction_set.UniqueID)


def display_name(unknown) -> str:
    """对象的 Moniker 属性是 IMoniker，取它的显示名。"""
    moniker = unknown.QueryInterface(pythoncom.IID_IMoniker)
    return moniker.GetDisplayName(pythoncom.CreateBindCtx(0), None)


def xml_by_flags(log: Log, model) -> None:
    """Q1：不同 flags 导出的操作 XML，长度和排序节点的原文。"""
    log.say("== Q1 ProvideXMLForOperation 的 flags ==")
    for flags in XML_FLAGS:
        ok, _length = log.attempt(
            f"ProvideXMLForOperation('CRV-100', {flags}) 的长度",
            lambda flags=flags: len(str(model.case.ProvideXMLForOperation("CRV-100", flags))),
        )
        if not ok:
            continue
        xml = str(model.case.ProvideXMLForOperation("CRV-100", flags))
        elements = RANK_ELEMENT.findall(xml)
        log.say(
            f"      排序节点 {len(elements)} 个；第一个原文: {elements[0] if elements else '无'}"
        )


def describe_variable(variable) -> str:
    """BackDoor 返回的变量当前的已知性、值、状态。"""
    parts = []
    for member in ("IsKnown", "Value", "State", "CanModify"):
        try:
            parts.append(f"{member}={getattr(variable, member)!r}")
        except pywintypes.com_error as exc:
            parts.append(f"{member}=抛 com_error({exc.args[0]})")
    return "，".join(parts)


def rank_variable(back_door, owner: str, form: str, index: int):
    """按 moniker 取排序变量（BackDoorRealVariable 返回的包装的 Variable）。"""
    moniker = owner + form.format(i=index)
    return back_door.BackDoorRealVariable(moniker).Variable


def read_through_back_door(log: Log, app, model) -> None:
    """Q2：三种 moniker 写法，按序号读排序变量。"""
    log.say("== Q2 BackDoor 读排序 ==")
    back_door = app.BackDoor
    owner = reaction_set_path(model)
    for form in MONIKER_FORMS:
        for index in range(RANK_COUNT):
            ok, variable = log.attempt(
                f"BackDoorRealVariable(<反应集>{form.format(i=index)}).Variable",
                lambda form=form, index=index: rank_variable(back_door, owner, form, index),
            )
            if ok:
                log.say(f"      {describe_variable(variable)}")


def calibrate_back_door(log: Log, app, model) -> None:
    """Q2：用值已知的进料温度（380 °C）校准 moniker 的写法，看 BackDoor 是否解析得了任何变量。"""
    log.say("== Q2 用进料温度校准 BackDoor 的 moniker ==")
    back_door = app.BackDoor
    log.say(f"  进料温度真实值 {model.feed.Temperature.GetValue('C')} C")
    owners = {
        "UniqueID": str(model.feed.UniqueID),
        "IMoniker 显示名": display_name(model.feed.Moniker),
    }
    for label, owner in owners.items():
        for suffix in FEED_TEMPERATURE_SUFFIXES:
            log.attempt(
                f"  {label} + {suffix}：(IsKnown, Value)",
                lambda owner=owner, suffix=suffix: describe_variable(
                    back_door.BackDoorRealVariable(owner + suffix).Variable
                ),
            )
    log.attempt(
        "  IMoniker 对象直接当参数",
        lambda: back_door.BackDoorRealVariable(model.feed.Moniker) is None,
    )
    log.attempt(
        "  BackDoorVariablesAndObjects(显示名, [':Temperature.501.0'], ['T'])",
        lambda: back_door.BackDoorVariablesAndObjects(
            owners["IMoniker 显示名"], (":Temperature.501.0",), ("T",)
        ),
    )
    feed_moniker = model.feed.Moniker.QueryInterface(pythoncom.IID_IMoniker)
    for delimiter in (":", "!", ".", "/"):
        composite = feed_moniker.ComposeWith(
            pythoncom.CreateItemMoniker(delimiter, "Temperature.501.0"), False
        )
        log.attempt(
            f"  复合 IMoniker（分隔符 {delimiter!r}）当参数，BackDoor 是否接受",
            lambda composite=composite: back_door.BackDoorRealVariable(composite) is not None,
        )


def write_through_back_door(log: Log, app) -> None:
    """Q3：每个实验一个新 Case，用 BackDoor 变量写排序，读 XML 里的排序和出口组成。"""
    log.say("== Q3 BackDoor 写排序（每次一个新 Case） ==")
    for ranks, note in WRITE_EXPERIMENTS:
        log.say(f"-- 写 {ranks}：{note} --")
        model = build_model(app)
        owner = reaction_set_path(model)
        for index, rank in enumerate(ranks):
            log.attempt(
                f"  第 {index} 号 SetValue({rank})",
                lambda owner=owner, index=index, rank=rank: rank_variable(
                    app.BackDoor, owner, MONIKER_FORMS[0], index
                ).SetValue(rank),
            )
        log.say(f"      写后 XML 里的排序 {read_ranks(model)}")
        report(log, model, f"排序 {ranks}")
        model.case.Close()


def apply_with_flags(log: Log, app) -> None:
    """Q4：同一个 flags 导出、同一个 flags 写回，只含排序的最小 XML，排序改成 (0,1,2)。"""
    log.say("== Q4 带 flags 的 ApplyXMLForOperation，最小 XML（每次一个新 Case） ==")
    for flags in APPLY_FLAGS:
        log.say(f"-- flags={flags}，排序 (0, 1, 2)：预测甲苯 {SEQUENTIAL_TOLUENE_FRACTION:.4f} --")
        model = build_model(app)
        text = str(model.case.ProvideXMLForOperation("CRV-100", flags))
        payload = minimal_rank_xml(text, (0, 1, 2))
        log.say(f"      写回前：进料组成 {feed_composition(model)}，排序 {read_ranks(model)}")
        _, applied = log.attempt(
            f"ApplyXMLForOperation('CRV-100', {flags}, 最小 XML)",
            lambda case=model.case, payload=payload, flags=flags: case.ApplyXMLForOperation(
                "CRV-100", flags, payload
            ),
        )
        log.say(f"      写回后：返回 {applied!r}，进料组成 {feed_composition(model)}")
        log.say(f"      写回后排序 {read_ranks(model)}")
        report(log, model, f"flags={flags}")
        model.case.Close()


def apply_full_xml_to_other_variables(log: Log, app) -> None:
    """Q4：整份操作 XML 写回，压降、进料温度、排序都改。看各 flags 弄坏 Case 与否、改得动什么。"""
    log.say("== Q4 整份操作 XML 写回：压降改 50、进料温度改 400、排序改 (0,1,2) ==")
    for flags in FULL_XML_FLAGS:
        log.say(f"-- flags={flags} --")
        model = build_model(app)
        text = str(model.case.ProvideXMLForOperation("CRV-100", flags))
        edited = DELTA_P_NODE.sub(r"\g<1>50\g<2>", text)
        edited = FEED_TEMPERATURE_NODE.sub(r"\g<1>400\g<2>", edited)
        payload = full_rank_xml(edited, (0, 1, 2))
        _, applied = log.attempt(
            f"ApplyXMLForOperation('CRV-100', {flags}, 整份 XML)",
            lambda case=model.case, flags=flags, payload=payload: case.ApplyXMLForOperation(
                "CRV-100", flags, payload
            ),
        )
        log.say(f"      返回 {applied!r}")
        log.attempt(
            "  写后压降 kPa（50 才算写进去）",
            lambda model=model: model.reactor.PressureDrop.GetValue("kPa"),
        )
        log.attempt(
            "  写后进料温度 C（400 才算写进去）",
            lambda model=model: model.feed.Temperature.GetValue("C"),
        )
        log.say(f"      写后排序 {read_ranks(model)}")
        report(log, model, f"flags={flags}")
        model.case.Close()


def apply_case_level(log: Log, app) -> None:
    """Q4：Case 级的 ApplyXML（返回 void）带最小排序 XML。"""
    log.say("== Q4 Case 级 ApplyXML，最小 XML，排序改成 (0,1,2) ==")
    for flags in CASE_LEVEL_FLAGS:
        log.say(f"-- flags={flags} --")
        model = build_model(app)
        text = str(model.case.ProvideXMLForOperation("CRV-100", flags))
        payload = minimal_rank_xml(text, (0, 1, 2))
        log.attempt(
            f"ApplyXML({flags}, 最小 XML)",
            lambda case=model.case, flags=flags, payload=payload: case.ApplyXML(flags, payload),
        )
        log.say(f"      写后：进料组成 {feed_composition(model)}，排序 {read_ranks(model)}")
        report(log, model, f"Case 级 flags={flags}")
        model.case.Close()


def build_with_active_arguments(app, ranks: tuple[int, ...], log: Log):
    """三个转化反应，ActiveReactions.Add 的第二个参数传 ranks。"""
    model = step_new_case(app)
    basis(model)
    reactions = model.manager.ReactionPackageManager.Reactions
    for name, isomer, conversion in REACTIONS:
        reaction = reactions.Add(name, "conversionrxn")
        for component, coefficient in (("Toluene", -2.0), ("Benzene", 1.0), (isomer, 1.0)):
            reaction.Reactants.Add(component).StoichiometricCoefficientValue = coefficient
        reaction.BaseComponent = model.package.Components.Item("Toluene")
        reaction.Conversion = conversion
        reaction.ReactionPhase = 0
    reaction_set = model.manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")
    for (name, _isomer, _conversion), rank in zip(REACTIONS, ranks, strict=True):
        log.attempt(
            f"  ActiveReactions.Add({name!r}, {rank})",
            lambda name=name, rank=rank: reaction_set.ActiveReactions.Add(name, rank),
        )
    reaction_set.AssociateFluidPackage(model.package)
    model.reaction_set = reaction_set
    step_end_basis(model)
    step_feed(model)
    step_outlets(model)
    step_reactor(model)
    return model


def active_reactions_second_argument(log: Log, app) -> None:
    """Q5：ActiveReactions.Add(name, 数) 的第二个参数。"""
    log.say("== Q5 ActiveReactions.Add 的第二个参数 ==")
    for ranks in ((1, 2, 3), (3, 2, 1)):
        log.say(f"-- 第二个参数 {ranks} --")
        model = build_with_active_arguments(app, ranks, log)
        log.say(f"      XML 里的排序 {read_ranks(model)}")
        report(log, model, f"第二个参数 {ranks}")
        model.case.Close()


def sample_rank_evidence(log: Log, app) -> None:
    """Q6：示例 Case 里转化反应器的排序值、指定转化率和实际起作用的转化率。"""
    log.say("== Q6 示例 Case（AspenTech 在界面里建的）的排序 ==")
    folder = Path(tempfile.mkdtemp(prefix="e6c_sample_")).resolve()
    copy = folder / SAMPLE_CASE.name
    shutil.copyfile(SAMPLE_CASE, copy)
    case = app.SimulationCases.Open(str(copy))
    for name in SAMPLE_REACTORS:
        reactor = case.Flowsheet.Operations.Item(name)
        text = str(case.ProvideXMLForOperation(name, 0))
        reaction_set_name = str(reactor.ReactionSet.name)
        block = next(
            b
            for b in re.findall(r"<ReactionRanks .*?</ReactionRanks>", text, re.DOTALL)
            if f'OwnerName="{reaction_set_name}"' in b
        )
        ranks = [
            float(v) for v in re.findall(r"<ReactionRank [^>]*>\s*<Value>([^<]*)</Value>", block)
        ]
        names = list(reactor.ReactionSet.ActiveReactions.Names)
        specified = list(reactor.ConversionValue)
        effective = list(reactor.RxnPercentConversionValue)
        log.say(f"  {name}：反应集 {reaction_set_name}，反应 {names}")
        log.say(f"      排序 {ranks}，指定转化率 {specified}，实际起作用的转化率 {effective}")
        judge_sample(log, ranks, specified, effective)
    case.Close()
    log.say(f"  示例副本目录 {folder}")


def judge_sample(
    log: Log, ranks: list[float], specified: list[float], effective: list[float]
) -> None:
    """排序值最小的反应先算；之后每个排序值的反应对剩下的基准组分按指定转化率算。"""
    first = min(ranks)
    consumed = sum(e for r, e in zip(ranks, effective, strict=True) if r == first)
    remainder_fraction = 1.0 - consumed / 100.0
    log.say(f"      排序最小的反应共消耗基准组分 {consumed:.4f}%，剩下 {remainder_fraction:.6f}")
    for rank, spec, eff in zip(ranks, specified, effective, strict=True):
        if rank == first:
            continue
        ratio = eff / spec
        verdict = "吻合" if abs(ratio - remainder_fraction) < RATIO_TOLERANCE else "不吻合"
        log.say(f"      排序 {rank:g} 的反应：实际/指定 = {ratio:.6f}，与剩余比例比较：{verdict}")
    if len(set(ranks)) == 1:
        log.say("      排序值全相同：各反应的实际/指定应当等于 1（并行）")
        ratios = [round(e / s, 6) for s, e in zip(specified, effective, strict=True)]
        log.say(f"      实际/指定 = {ratios}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run3")
    args = parser.parse_args()
    log = Log(f"e6c_rank_channels_{args.tag}")
    with new_instance(log) as (app, pid), dialog_guard(log, pid):
        with watch(log, "建模"):
            model = build_model(app)
        xml_by_flags(log, model)
        read_through_back_door(log, app, model)
        calibrate_back_door(log, app, model)
        model.case.Close()
        write_through_back_door(log, app)
        apply_with_flags(log, app)
        apply_full_xml_to_other_variables(log, app)
        apply_case_level(log, app)
        active_reactions_second_argument(log, app)
        sample_rank_evidence(log, app)


if __name__ == "__main__":
    main()
