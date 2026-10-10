# ChemicalAgent

化工 Agent 考核 demo：用自然语言描述一个反应过程，系统判断该用哪种反应器并说明理由，在本机的 Aspen HYSYS V15 里建模、求解，返回经过验证的结果。

进度、设计决定和交接记录在 `docs/progress.md`；HYSYS 接口的事实台账和探索日志在 `docs/HYSYS_INTEGRATION.md`；架构基线在 `docs/MASTER_PLAN.md`。

## 用法

```
reactor-agent run --spec <规格文件>                  按规格文件建模、求解、验证（需要 HYSYS）
reactor-agent run --text-file <描述.txt> --dry-run   读一段描述：选型、写规格，打印规格、假设和建模步骤，不碰 HYSYS
reactor-agent run --text-file <描述.txt>             读一段描述，一直做到建模、求解、验证（需要 HYSYS 和密钥）
reactor-agent trace <task_id>                        打印一次运行的时间线
```

描述文件是 UTF-8 文本，例子在 `evals/inputs/`。较长的描述用文件，不要作为带引号的命令行参数传入：中文长句很容易被 shell 改坏（命令行也接受 `reactor-agent run "<描述>"`）。

文字描述的流程是：选型（规则和 LLM 对照）→ LLM 把描述写成 `TaskSpec`（数值和单位照原文抄，缺失和假设显式声明）→ 代码做单位换算、组成归一化、组分名解析和业务规则检查，通过了冻结成 `ModelSpec`，没通过带着问题清单交回给 LLM 重写（最多 2 轮）→ Recipe 编译出建模步骤。`--dry-run` 在这里停下并打印：选型结论、换算后的规格、假设清单、建模步骤。缺少不可以假设的关键信息（进料的温度、压力、组成，转化率）时，终态是 `NEEDS_INPUT`（退出码 4），并列出缺什么。运行目录里有 `artifacts/`（`selection.json`、`task_spec.json`、`spec_issues.json`、`model_spec.json`、`plan.json`）、`llm/`（每次 LLM 调用的提示和回复全文）和 `trace.jsonl`。

## 密钥

LLM 用阿里云百炼的 Qwen（配置在 `config/settings.yaml`）。系统只从环境变量 `DASHSCOPE_API_KEY` 读密钥，不写进文件、不进日志。

**设置并永久保存**：在终端里输入一次（不回显），先用系统自己调用 LLM 的那条路径测试连通，通过了才写入用户级环境变量并读回比对。之后新打开的终端和程序都能读到：

```
python evals/set_api_key.py
```

**交互入口**：用菜单运行三个场景的干跑、评测，或者对你输入的一段描述干跑；环境变量里没有密钥时先读 `set_api_key.py` 保存的用户级变量，再不行才询问：

```
python evals/interactive.py
```

也可以自己设置环境变量（PowerShell，输入时不回显）：

```
$key = Read-Host -AsSecureString 'DASHSCOPE_API_KEY'; $env:DASHSCOPE_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password
```

## 开发

```
ruff format --check .
ruff check .
mypy src
pytest                                  # 默认不含需要 HYSYS 和 LLM 的测试
pytest -m hysys tests/integration       # 需要本机的 HYSYS
pytest -m llm tests/llm                 # 需要密钥
python evals/run_evals.py               # 选型和规格评测，结果写进 docs/EVAL_RESULTS.md（需要密钥）
python tests/test_code_health.py        # 各模块行数、最长的函数、嵌套最深的函数
```
