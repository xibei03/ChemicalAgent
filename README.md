# ChemicalAgent

化工 Agent 考核 demo：用自然语言描述一个反应过程，系统判断该用哪种反应器并说明理由，在本机的 Aspen HYSYS V15 里建模、求解，返回经过验证的结果。

进度、设计决定和交接记录在 `docs/progress.md`；HYSYS 接口的事实台账和探索日志在 `docs/HYSYS_INTEGRATION.md`；架构基线在 `docs/MASTER_PLAN.md`。

## 用法

```
reactor-agent run --spec <规格文件>              按规格文件建模、求解、验证（需要 HYSYS）
reactor-agent run --text-file <描述.txt> --dry-run   读一段描述，只做选型，不碰 HYSYS
reactor-agent trace <task_id>                    打印一次运行的时间线
```

描述文件是 UTF-8 文本，例子在 `evals/inputs/`。较长的描述用文件，不要作为带引号的命令行参数传入：中文长句很容易被 shell 改坏（命令行也接受 `reactor-agent run "<描述>"`）。选型的输出包括反应器类型、规则的推导、LLM 的理由、原文依据、备选类型和不选它们的原因；运行目录里有 `artifacts/selection.json`（完整结果）、`llm/`（每次 LLM 调用的提示和回复全文）和 `trace.jsonl`。

**目前文字描述只做到选型**（阶段 2A）；从描述生成规格并建模在阶段 2B、2C。

## 密钥

LLM 用阿里云百炼的 Qwen（配置在 `config/settings.yaml`）。密钥只从环境变量 `DASHSCOPE_API_KEY` 读，不写进文件、不进日志。在自己的终端里设置（PowerShell，输入时不回显）：

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
python evals/run_evals.py               # 选型评测，结果写进 docs/EVAL_RESULTS.md（需要密钥）
python tests/test_code_health.py        # 各模块行数、最长的函数、嵌套最深的函数
```
