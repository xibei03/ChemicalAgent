"""E13b（0C 任务 5）：备选路线之二，文件和脚本。最小任务：在空白 Case 里加一台转化反应器。

HYSYS 的安装目录 Template\\*.scp 是 HYSYS 自带的脚本文件（脚本录制回放的格式）：
  Message "FlowSht.1" "CreateFromPFD TraySectionObject"      向对象发消息
  Specify "FlowSht.1" ":Selection.400" "ObjectType:..."      给内部变量赋数值
  SpecifyText / AttachObject / ResponseMessage Yes / Call    赋文字、连接物流、自动回答对话框、
                                                             调另一个脚本
类型库里 Application.PlayScript(文件) 可以回放这种文件。

要回答的问题：
  Q1 文本路线：把已有 Case 的 XML 导出，导入一个空白 Case（Basis 和反应已建好），
     反应器和物流会不会被创建出来，连接和求解结果呢？Case 级和操作级、flags 0 和 128 各试一次
  Q2 脚本路线：PlayScript 回放一个手写的脚本，能不能在空白 Case 里加出一台转化反应器？
  Q3 脚本路线能不能写 COM 写不了的内部变量？反应集排序（E6c 里所有 COM 通道都走不通）用
     Specify "<反应集路径>" ":Index.400.<序号>" <值> 试一下，
     看出口甲苯摩尔分率是否变成依次进行的 0.5731。
Q2、Q3 各做两遍：Case 隐藏（COM 新建的默认状态）和 case.Visible = True（成为界面里的活动文档）。
每个实验一个新实例，防止一个实验弄坏实例、影响后面的实验。
每条路线记：是否可行、耗时、可重复性、结果能否由程序验证。

用法：python spikes/e13b_file_script.py [--tag 名字] [--only 实验名]
输出：spikes/out/e13b_file_script_<tag>.txt
"""

import argparse
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8
from chain_kit import new_case_with_basis, status_counts
from e6b_parallel_reactions import (
    MIXED_TOLUENE_FRACTION,
    SEQUENTIAL_TOLUENE_FRACTION,
    build_model,
    read_ranks,
    report,
)
from e7_conversion_chain import (
    step_basis,
    step_end_basis,
    step_new_case,
    step_reaction,
    step_reaction_set,
)
from e11_robustness import kill_after

use_utf8()

DONOR_CASE = OUT_DIR / "e7_conversion_chain_run3.hsc"
COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
SAFETY_NET_S = 180.0
REACTION_SET_PATH = "FluidPkgMgr.300/RxnPackageManager.300/RxnSet.300(Conv-Set)"
REACTOR_SELECTION = 'Specify "FlowSht.1" ":Selection.400"   "ObjectType:ConversionReactorOpObject"'
REACTOR_SCRIPTS = {
    # 仿 Template\*.scp 里加塔设备的写法
    "template-style": (
        "Description Add a conversion reactor",
        'Message "FlowSht.1" "EnterBuild"',
        "ResponseMessage Yes",
        'Message "FlowSht.1" "CreatePFDAndView"',
        REACTOR_SELECTION,
        'Message "FlowSht.1" "CreateFromPFD ConversionReactorOpObject"',
    ),
    # 仿 Template\*.scp 里加物流的写法（CreateAndView）
    "create-and-view": (
        "Description Add a conversion reactor",
        REACTOR_SELECTION,
        'Message "FlowSht.1" "CreateAndView"',
    ),
}
RANK_EXPERIMENTS = (
    ("依次 (0,1,2)", (0, 1, 2), SEQUENTIAL_TOLUENE_FRACTION),
    ("第三个先算 (1,1,0)", (1, 1, 0), MIXED_TOLUENE_FRACTION),
)


def write_script(folder: Path, name: str, lines: tuple[str, ...]) -> Path:
    """脚本文件：纯 ASCII、CRLF 换行（和 HYSYS 自带的 .scp 一致）。"""
    path = folder / name
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return path


def operations_and_streams(case) -> str:
    flowsheet = case.Flowsheet
    return f"操作 {list(flowsheet.Operations.Names)}，物流 {list(flowsheet.MaterialStreams.Names)}"


def blank_case_with_basis(app):
    """空白 Case，Basis、反应和反应集与供体相同（用 G0 的步骤函数建），还没有流程图对象。"""
    model = step_new_case(app)
    step_basis(model)
    step_reaction(model)
    step_reaction_set(model)
    step_end_basis(model)
    return model


def describe_flowsheet(log: Log, case) -> None:
    """XML 导入之后，流程图里有什么、连了什么、有没有求解。"""
    flowsheet = case.Flowsheet
    log.say(f"      之后 {operations_and_streams(case)}；状态 {status_counts(case)}")
    if "CRV-100" not in list(flowsheet.Operations.Names):
        return
    reactor = flowsheet.Operations.Item("CRV-100")
    feed = flowsheet.MaterialStreams.Item("Feed")
    log.attempt("      CRV-100.TypeName", lambda: reactor.TypeName)
    log.attempt("      CRV-100 的进料", lambda: list(reactor.Feeds.Names))
    log.attempt("      CRV-100.VapourProduct", lambda: reactor.VapourProduct.name)
    log.attempt("      CRV-100.ReactionSet", lambda: reactor.ReactionSet.name)
    log.attempt(
        "      Feed 的 T(C)、P(kPa)、质量流量(kg/h)",
        lambda: (
            feed.Temperature.GetValue("C"),
            feed.Pressure.GetValue("kPa"),
            feed.MassFlow.GetValue("kg/h"),
        ),
    )
    vapour = flowsheet.MaterialStreams.Item("Vap")
    log.attempt(
        "      Vap 的摩尔分率", lambda: [round(v, 4) for v in vapour.ComponentMolarFraction.Values]
    )


def xml_experiment(log: Log, app, dialogs: list[str], scope: str, flags: int) -> None:
    """Q1：一次 XML 导入实验。"""
    folder = Path(tempfile.mkdtemp(prefix="e13b_")).resolve()
    donor_path = folder / "donor.hsc"
    shutil.copyfile(DONOR_CASE, donor_path)
    donor = app.SimulationCases.Open(str(donor_path))
    case_xml = str(donor.ProvideXMLForCase(flags))
    operation_xml = str(donor.ProvideXMLForOperation("CRV-100", flags))
    log.say(f"  供体：Case XML {len(case_xml)} 字符，操作 XML {len(operation_xml)} 字符")
    donor.Close()
    model = blank_case_with_basis(app)
    log.say(f"  导入前（空白 Case，Basis 和反应已建）：{operations_and_streams(model.case)}")
    before, start = len(dialogs), time.time()
    if scope == "case":
        log.attempt("ApplyXML", lambda: model.case.ApplyXML(flags, case_xml))
    else:
        log.attempt(
            "ApplyXMLForOperation",
            lambda: model.case.ApplyXMLForOperation("CRV-100", flags, operation_xml),
        )
    log.say(
        f"      用时 {time.time() - start:.2f} 秒；"
        f"弹窗 {len(dialogs) - before} 个 {sorted(set(dialogs[before:]))}"
    )
    describe_flowsheet(log, model.case)
    model.case.Close()
    shutil.rmtree(folder, ignore_errors=True)


def script_add_reactor(log: Log, app, dialogs: list[str], visible: bool, style: str) -> None:
    """Q2：PlayScript 加转化反应器。style 选 REACTOR_SCRIPTS 里的一种写法。"""
    folder = Path(tempfile.mkdtemp(prefix="e13b_")).resolve()
    script = write_script(folder, "add_reactor.scp", REACTOR_SCRIPTS[style])
    basis = new_case_with_basis(app, "e13b_script", COMPONENTS)
    basis.manager.EndBasisChange()
    if visible:
        basis.case.Visible = True
        time.sleep(2.0)
    log.say(f"  case.Visible={basis.case.Visible}；回放前 {operations_and_streams(basis.case)}")
    before, start = len(dialogs), time.time()
    log.attempt(f"PlayScript({script.name})", lambda: app.PlayScript(str(script)))
    log.say(
        f"  用时 {time.time() - start:.2f} 秒；弹窗 {len(dialogs) - before} 个 "
        f"{dialogs[before:]}；回放后 {operations_and_streams(basis.case)}"
    )
    basis.case.Close()
    shutil.rmtree(folder, ignore_errors=True)


def script_set_ranks(
    log: Log, app, dialogs: list[str], visible: bool, app_hidden: bool = False
) -> None:
    """Q3：PlayScript 写反应集排序。app_hidden 为真时先隐藏整个 HYSYS 窗口。"""
    folder = Path(tempfile.mkdtemp(prefix="e13b_")).resolve()
    if app_hidden:
        app.Visible = False
        log.say(f"  app.Visible = {app.Visible}")
    for label, ranks, expected in RANK_EXPERIMENTS:
        log.say(f"-- {label}：预测出口甲苯摩尔分率 {expected:.4f} --")
        model = build_model(app)
        if visible:
            model.case.Visible = True
            time.sleep(2.0)
        lines = tuple(
            f'Specify "{REACTION_SET_PATH}" ":Index.400.{index}"   {float(rank):.12e}'
            for index, rank in enumerate(ranks)
        )
        script = write_script(folder, "ranks.scp", lines)
        log.say(f"  脚本内容 {list(lines)}")
        log.say(f"  回放前排序 {read_ranks(model)}")
        before, start = len(dialogs), time.time()
        log.attempt(f"PlayScript({script.name})", lambda script=script: app.PlayScript(str(script)))
        log.say(
            f"  用时 {time.time() - start:.2f} 秒；"
            f"弹窗 {len(dialogs) - before} 个 {dialogs[before:]}"
        )
        log.say(f"  回放后排序 {read_ranks(model)}")
        report(log, model, label)
        model.case.Close()
    shutil.rmtree(folder, ignore_errors=True)


EXPERIMENTS = {
    "xml-case-0": lambda log, app, d: xml_experiment(log, app, d, "case", 0),
    "xml-operation-0": lambda log, app, d: xml_experiment(log, app, d, "operation", 0),
    "xml-case-128": lambda log, app, d: xml_experiment(log, app, d, "case", 128),
    "xml-operation-128": lambda log, app, d: xml_experiment(log, app, d, "operation", 128),
    "script-reactor-hidden": lambda log, app, d: script_add_reactor(
        log, app, d, False, "template-style"
    ),
    "script-reactor-visible": lambda log, app, d: script_add_reactor(
        log, app, d, True, "template-style"
    ),
    "script-reactor-visible-create-and-view": lambda log, app, d: script_add_reactor(
        log, app, d, True, "create-and-view"
    ),
    "script-ranks-hidden": lambda log, app, d: script_set_ranks(log, app, d, False),
    "script-ranks-visible": lambda log, app, d: script_set_ranks(log, app, d, True),
    "script-ranks-app-hidden-case-visible": lambda log, app, d: script_set_ranks(
        log, app, d, True, app_hidden=True
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run2")
    parser.add_argument("--only", default=None, choices=list(EXPERIMENTS))
    args = parser.parse_args()
    log = Log(f"e13b_file_script_{args.tag}")
    for name, experiment in EXPERIMENTS.items():
        if args.only and name != args.only:
            continue
        log.say(f"######## {name} ########")
        try:
            with (
                new_instance(log) as (app, pid),
                dialog_guard(log, pid, include_hidden=True) as dialogs,
            ):
                safety = kill_after(log, pid, SAFETY_NET_S, f"{name} 安全网")
                experiment(log, app, dialogs)
                safety.cancel()
        except Exception:  # 探针：任何失败都要连同堆栈记进日志，再做下一个实验
            log.say(traceback.format_exc())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
