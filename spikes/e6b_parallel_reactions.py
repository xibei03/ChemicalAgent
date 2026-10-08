"""E6b（0B 任务 5）：同一个基准组分的多个转化反应，HYSYS 怎么处理排序。

后面的阶段要支持"同一个基准组分有主、副两个反应，各有各的转化率"，所以要知道：
  Q1 三个转化反应（基准组分都是甲苯，各生成一种二甲苯，转化率 12%、26%、12%）放进同一个反应集，
     不动排序设置时，出口甲苯摩尔分率是 0.500（并行，各反应都对进料里的甲苯算）
     还是 0.573 = (1-0.12)(1-0.26)(1-0.12)（依次，后一个对前一个剩下的甲苯算）？
  Q2 排序对应哪个成员、取值什么含义？怎么把它设成并行、设成依次？
做法：沿用 e7_conversion_chain.py 的步骤函数建模型，只把反应换成三个。先读默认排序下的结果；
再找排序的接口：类型库里没有排序成员，用 GetIDsOfNames 探测名字，再从操作的 XML 导出里找到
反应集的 ReactionRanks，试着用 ApplyXMLForOperation 写回。写回可能破坏 Case，所以每个实验用新 Case。

用法：python spikes/e6b_parallel_reactions.py [--tag 名字]
输出：spikes/out/e6b_parallel_reactions_<tag>.txt
"""

import argparse
import re
from xml.etree import ElementTree

import pywintypes
from _common import Log, dialog_guard, new_instance, use_utf8, watch
from e7_conversion_chain import (
    COMPONENTS,
    Model,
    step_end_basis,
    step_feed,
    step_new_case,
    step_outlets,
)
from e7_conversion_chain import step_basis as basis

use_utf8()

# (反应名, 产物异构体, 转化率百分数)
REACTIONS = (("R-pX", "p-Xylene", 12.0), ("R-mX", "m-Xylene", 26.0), ("R-oX", "o-Xylene", 12.0))
PARALLEL_TOLUENE_FRACTION = 0.5
SEQUENTIAL_TOLUENE_FRACTION = (1 - 0.12) * (1 - 0.26) * (1 - 0.12)
# 第三个反应（12%）先算，前两个（12%、26%）在剩下的 88% 上并行
MIXED_TOLUENE_FRACTION = 1 - 0.12 - 0.12 * 0.88 - 0.26 * 0.88
FRACTION_TOLERANCE = 0.002
NAME_CANDIDATES = (
    "Rank",
    "Ranking",
    "Rankings",
    "ConversionRank",
    "ConversionRanking",
    "ConversionRankings",
    "RxnRank",
    "ReactionRank",
    "ReactionOrder",
    "Order",
    "Sequence",
    "Index",
    "UserSpecified",
    "Priority",
)
RANK_BLOCK = re.compile(r"<ReactionRanks .*?</ReactionRanks>", re.DOTALL)
RANK_VALUE = re.compile(r"(<ReactionRank [^>]*>\s*<Value>)[^<]*(</Value>)")
XML_DECLARATION = re.compile(r"^<\?xml[^>]*\?>\s*")


def step_reactions(model: Model) -> None:
    """三个转化反应，各生成一种二甲苯，按 R-pX、R-mX、R-oX 的顺序放进同一个反应集。"""
    reactions = model.manager.ReactionPackageManager.Reactions
    for name, isomer, conversion in REACTIONS:
        reaction = reactions.Add(name, "conversionrxn")
        for component, coefficient in (("Toluene", -2.0), ("Benzene", 1.0), (isomer, 1.0)):
            reaction.Reactants.Add(component).StoichiometricCoefficientValue = coefficient
        reaction.BaseComponent = model.package.Components.Item("Toluene")
        reaction.Conversion = conversion
        reaction.ReactionPhase = 0
    reaction_set = model.manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")
    for name, _isomer, _conversion in REACTIONS:
        reaction_set.ActiveReactions.Add(name)
    reaction_set.AssociateFluidPackage(model.package)
    model.reaction_set = reaction_set


def step_reactor(model: Model) -> None:
    reactor = model.flowsheet.Operations.Add("CRV-100", "ConversionReactorOp")
    reactor.Feeds.Add(model.feed)
    reactor.VapourProduct = model.vapour
    reactor.LiquidProduct = model.liquid
    reactor.ReactionSet = model.reaction_set
    model.reactor = reactor


def build_model(app) -> Model:
    """新建 Case，建好三个并行转化反应的模型。"""
    model = step_new_case(app)
    basis(model)
    step_reactions(model)
    step_end_basis(model)
    step_feed(model)
    step_outlets(model)
    step_reactor(model)
    return model


def eval_member(obj, dotted: str):
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def classify(toluene: float) -> str:
    if abs(toluene - PARALLEL_TOLUENE_FRACTION) < FRACTION_TOLERANCE:
        return "并行（0.500）"
    if abs(toluene - SEQUENTIAL_TOLUENE_FRACTION) < FRACTION_TOLERANCE:
        return "依次（0.573）"
    if abs(toluene - MIXED_TOLUENE_FRACTION) < FRACTION_TOLERANCE:
        return "第三个先算、前两个并行（0.546）"
    return "不是已知的三种"


def report(log: Log, model: Model, label: str) -> float:
    """读出口组成和反应器按反应的数组，返回出口甲苯摩尔分率。"""
    flows = dict(
        zip(COMPONENTS, model.vapour.ComponentMolarFlow.GetValues("kgmole/h"), strict=True)
    )
    total = sum(flows.values())
    toluene = flows["Toluene"] / total
    log.say(f"  [{label}] 出口摩尔分率 { {k: round(v / total, 4) for k, v in flows.items()} }")
    log.say(f"      出口甲苯摩尔分率 {toluene:.4f}：{classify(toluene)}")
    for member in ("ConversionValue", "RxnPercentConversionValue"):
        log.attempt(
            f"      reactor.{member}", lambda member=member: eval_member(model.reactor, member)
        )
    return toluene


def probe_dispatch_names(log: Log, model: Model) -> None:
    """用 IDispatch 的 GetIDsOfNames 探测对象上有没有排序相关的成员（类型库里没有的名字）。"""
    log.say("== Q2 探测排序成员的名字（GetIDsOfNames） ==")
    objects = (
        ("反应集", model.reaction_set),
        ("反应器", model.reactor),
        ("反应 R-pX", model.manager.ReactionPackageManager.Reactions.Item("R-pX")),
    )
    for label, obj in objects:
        found = []
        for name in NAME_CANDIDATES:
            try:
                obj._oleobj_.GetIDsOfNames(name)
            except pywintypes.com_error:
                continue
            found.append(name)
        log.say(f"  {label}: 存在的名字 {found or '没有'}")


def read_ranks(model: Model) -> list[str]:
    """从操作的 XML 里读反应集的排序值（按反应在反应集里的顺序）。"""
    text = str(model.case.ProvideXMLForOperation("CRV-100", 0))
    block = RANK_BLOCK.search(text)
    if not block:
        return []
    return re.findall(r"<ReactionRank [^>]*>\s*<Value>([^<]*)</Value>", block.group(0))


def describe_rank_xml(log: Log, model: Model) -> None:
    """操作的 XML 里排序在哪里、什么结构。"""
    log.say("== Q2 XML 里的排序 ==")
    text = str(model.case.ProvideXMLForOperation("CRV-100", 0))
    log.say(f"  XML 长度 {len(text)}，声明 {XML_DECLARATION.match(text).group(0).strip()!r}")
    root = ElementTree.fromstring(text.encode("cp1252", errors="replace"))
    parents = {child: parent for parent in root.iter() for child in parent}
    target = next(e for e in root.iter() if e.tag == "ReactionRanks")
    chain, node = [], target
    while node in parents:
        node = parents[node]
        chain.append(node.tag)
    log.say(f"  ReactionRanks 的祖先路径（由内到外）: {chain}")
    for rank_set in target:
        fields = {c.tag: (c.findtext("Value"), c.findtext("Status")) for c in rank_set}
        log.say(f"    {rank_set.tag}: {fields}")
    for member in ("TaggedName", "UniqueID"):
        log.attempt(f"反应集.{member}", lambda member=member: getattr(model.reaction_set, member))


def minimal_rank_xml(text: str, ranks: tuple[int, ...]) -> str:
    """只保留 CaseDescription 和通向 ReactionRanks 的那条祖先链，排序值换成 ranks。"""
    root = ElementTree.fromstring(text.encode("cp1252", errors="replace"))
    parents = {child: parent for parent in root.iter() for child in parent}
    target = next(e for e in root.iter() if e.tag == "ReactionRanks")
    values = iter(ranks)
    for rank in target.iter("ReactionRank"):
        rank.find("Value").text = str(next(values))
    current, node = target, target
    while parents[node] is not root:
        node = parents[node]
        copy = ElementTree.Element(node.tag, node.attrib)
        copy.append(current)
        current = copy
    new_root = ElementTree.Element(root.tag, root.attrib)
    new_root.append(root.find("CaseDescription"))
    new_root.append(current)
    return ElementTree.tostring(new_root, encoding="unicode")


def full_rank_xml(text: str, ranks: tuple[int, ...]) -> str:
    """整份操作 XML，只把排序值换掉，去掉 XML 声明（带 windows-1252 声明会被拒绝）。"""
    block = RANK_BLOCK.search(text)
    values = iter(ranks)
    new_block = RANK_VALUE.sub(lambda m: f"{m.group(1)}{next(values)}{m.group(2)}", block.group(0))
    return XML_DECLARATION.sub("", text[: block.start()] + new_block + text[block.end() :])


def feed_composition(model: Model) -> tuple[float, ...]:
    return tuple(round(v, 4) for v in model.feed.ComponentMolarFraction.Values)


def apply_ranks(log: Log, model: Model, ranks: tuple[int, ...], mode: str) -> None:
    """mode：full 把整份操作 XML 改了排序再写回；minimal 只写排序那一小段。"""
    text = str(model.case.ProvideXMLForOperation("CRV-100", 0))
    payload = full_rank_xml(text, ranks) if mode == "full" else minimal_rank_xml(text, ranks)
    log.say(f"      写回前：进料组成 {feed_composition(model)}，排序 {read_ranks(model)}")
    _, applied = log.attempt(
        f"ApplyXMLForOperation('CRV-100', 0, {mode} XML) 排序 {ranks}",
        lambda: model.case.ApplyXMLForOperation("CRV-100", 0, payload),
    )
    log.say(f"      写回后：返回 {applied!r}，进料组成 {feed_composition(model)}")
    log.say(f"      写回后排序 {read_ranks(model)}")


def probe_rank_values(log: Log, app) -> None:
    """Q2：改排序值，看出口甲苯摩尔分率怎么变。每个实验用一个新的 Case。"""
    log.say("== Q2 通过 XML 改排序值（每次一个新 Case） ==")
    experiments = (
        ("full", (0, 1, 2), "整份 XML 写回（对照）"),
        ("minimal", (0, 1, 2), f"依次：预测甲苯 {SEQUENTIAL_TOLUENE_FRACTION:.4f}"),
        ("minimal", (1, 1, 0), f"第三个先算，前两个并行：预测甲苯 {MIXED_TOLUENE_FRACTION:.4f}"),
        ("minimal", (2, 1, 0), f"倒序依次：预测甲苯 {SEQUENTIAL_TOLUENE_FRACTION:.4f}"),
        ("minimal", (5, 5, 5), "三个相同的非零值：预测并行 0.5000"),
    )
    for index, (mode, ranks, note) in enumerate(experiments):
        log.say(f"-- 实验 {index + 1}：{mode} {ranks}：{note} --")
        model = build_model(app)
        apply_ranks(log, model, ranks, mode)
        report(log, model, f"排序 {ranks}")
        model.case.Close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e6b_parallel_reactions_{args.tag}")
    with new_instance(log) as (app, pid), dialog_guard(log, pid):
        with watch(log, "建模"):
            model = build_model(app)
        log.say("== Q1 默认排序（反应按 R-pX、R-mX、R-oX 的顺序加入反应集） ==")
        report(log, model, "默认排序")
        probe_dispatch_names(log, model)
        describe_rank_xml(log, model)
        model.case.Close()
        probe_rank_values(log, app)


if __name__ == "__main__":
    main()
