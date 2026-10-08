"""E6c（0B 任务 5 的补充）：反应集的排序（Conversion Rankings）能不能用 COM 读写。

e6b 的结果：类型库里没有排序成员；flags=0 调 ApplyXMLForOperation 返回 False，还弄坏了 Case。
要回答的问题：
  Q1 ProvideXMLForOperation 的 flags 是位掩码（opt_SupplyMonikers=8 等）。不同 flags 导出的 XML
     里，排序节点是什么样，带 8 时有没有 moniker？
  Q2 BackDoor 能不能按 moniker 读到排序？rxnset.rdf 里排序的内部变量是 :Index.400.[]，
     反应集对象自己有 Moniker 属性，两者怎么拼？
做法：沿用 e6b 的三个并行转化反应的模型，只读。写入的实验在 e6b 里做。

用法：python spikes/e6c_rank_channels.py [--tag 名字]
输出：spikes/out/e6c_rank_channels_<tag>.txt
"""

import argparse
import re

import pywintypes
from _common import Log, dialog_guard, new_instance, use_utf8, watch
from e6b_parallel_reactions import build_model

use_utf8()

XML_FLAGS = (0, 1, 2, 8, 9, 16, 128, 129, 2048, 4096, 8192, 8 + 2048)
RANK_ELEMENT = re.compile(r"<ReactionRank\b[^>]*>.*?</ReactionRank>", re.DOTALL)
RANK_INDICES = (0, 1, 2)


def object_monikers(log: Log, model) -> dict[str, object]:
    """反应集、反应器、反应的 Moniker 和 UniqueID 属性。"""
    reaction = model.manager.ReactionPackageManager.Reactions.Item("R-pX")
    found: dict[str, object] = {}
    for label, obj in (
        ("反应集", model.reaction_set),
        ("反应器", model.reactor),
        ("反应", reaction),
    ):
        for member in ("Moniker", "UniqueID"):
            ok, value = log.attempt(
                f"{label}.{member}", lambda obj=obj, member=member: getattr(obj, member)
            )
            if ok:
                found[f"{label}.{member}"] = value
    return found


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


def candidate_monikers(found: dict[str, object]) -> list[str]:
    """用反应集的 Moniker 和 UniqueID 拼排序变量的 moniker，每种拼法各试 0 号反应。"""
    bases = [str(found[key]) for key in ("反应集.Moniker", "反应集.UniqueID") if key in found]
    forms = []
    for base in bases:
        forms += [f"{base}:Index.400.[0]", f"{base}.Index.400.[0]", f"{base}:Index.400.[]"]
    return forms


def describe_wrapper(wrapper) -> str:
    parts = []
    for member in ("IsValid", "Tag", "Index1", "Index2", "Index3"):
        try:
            parts.append(f"{member}={getattr(wrapper, member)!r}")
        except pywintypes.com_error as exc:
            parts.append(f"{member}=抛 com_error({exc.args[0]})")
    return "，".join(parts)


def probe_back_door(log: Log, app, found: dict[str, object]) -> None:
    """Q2：BackDoor 的几种取法，按 moniker 读排序。"""
    log.say("== Q2 BackDoor ==")
    ok, back_door = log.attempt("app.BackDoor", lambda: app.BackDoor)
    if not ok:
        return
    for moniker in candidate_monikers(found):
        for getter in ("BackDoorVariable", "BackDoorRealVariable"):
            ok, wrapper = log.attempt(
                f"{getter}({moniker!r})", lambda g=getter, m=moniker: getattr(back_door, g)(m)
            )
            if ok and wrapper is not None:
                log.say(f"      {describe_wrapper(wrapper)}")
                log.attempt("      .Variable", lambda w=wrapper: w.Variable)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e6c_rank_channels_{args.tag}")
    with new_instance(log) as (app, pid), dialog_guard(log, pid):
        with watch(log, "建模"):
            model = build_model(app)
        found = object_monikers(log, model)
        xml_by_flags(log, model)
        probe_back_door(log, app, found)
        model.case.Close()


if __name__ == "__main__":
    main()
