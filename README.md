# RydeResolve Evidence/Data + tools

这是琪琪负责的 **Evidence/Data + tools** 模块，用于 Tencent Cloud Hackathon Singapore 2026 的 Digital Native / Ryde 赛道。它将案例整理成中性证据，保留原始来源，供双方 Advocate、Judge 和展示层接入。

当前为 **v0.2.0**，包含 **1 个主办方样例**（DISP-002 / No-Show Charge）及 **1 个明确标注的合成案例**（SYN-ROUTE-001 / Route Deviation）。实现使用 Python 3.12+；字段校验使用 jsonschema，版本记录在 constraints.txt；不同语言的队友可以通过 HTTP/JSON 接入。

## 第一次运行

在 Windows PowerShell 中进入仓库目录，依次运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ryderesolve_evidence serve --port 8765
```

打开 <http://127.0.0.1:8765>。选择案例后，可以点击 `E-xxx` / `P-xxx` 查看原始记录，检查数据冲突，并下载 Evidence Pack 或包含版本与原始证据的完整快照。按 `Ctrl+C` 停止服务。已有 `.venv` 时无需重复创建；升级后重新运行安装命令。

macOS/Linux 用 `.venv/bin/python` 替换上述 Python 路径。只读取/生成数据时，无需启动网页，也无需模型账号或 API key：

```powershell
.\.venv\Scripts\python.exe -m ryderesolve_evidence pack DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence prepare DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence audit DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence evidence DISP-002 E-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence route SYN-ROUTE-001
.\.venv\Scripts\python.exe -m ryderesolve_evidence export DISP-002 --out work\exports
```

## 先读哪份文件

- [给队友的接入说明](docs/INTEGRATION.md)：函数、HTTP、JSON 字段、引用规则。
- [项目基线](docs/PROJECT_BASELINE.md)：已确定的范围、接口约定、待确认项；后续工作以此续接。
- [官方数据核对](docs/SOURCE_AUDIT.md)：480 秒 / 470 秒差异、陈述来源、答案隔离与模拟数据边界。
- [验证记录](docs/VALIDATION.md)：本次实际执行结果与仍待团队联调的部分。
- [补强审查与待确认事项](docs/HARDENING_REVIEW.md)：已复现的问题、修复、能力边界以及下一步所需信息。
- [来源与署名](docs/PROVENANCE.md)：原始数据、合成数据和个人/团队/AI 辅助贡献的区分。

## 核心接口

`case_id`、`evidence_id`、`evidence_refs`、`policy_refs`、`decision` 保留原名。

```python
from ryderesolve_evidence import EvidenceTools

tools = EvidenceTools()
snapshot = tools.prepare_case("DISP-002")  # 一次读取，避免分别取 raw/pack/audit 时版本不一致
pack = snapshot["evidence_pack"]  # 原接口不变
source = tools.get_evidence("DISP-002", "E-002", expected_snapshot_id=snapshot["snapshot_id"])
```

Evidence Pack 仍为 `case_id / dispute_type / facts / policy`。每条事实只要求 `evidence_id / fact / source`。来源路径、证据类型、版本和核对结果放在独立查询结果中，不给原接口增加必填字段。

JSON Schema（机器可校验的字段规范）保存在 `ryderesolve_evidence/contracts/`。`decision` 暂为非空字符串，完整取值集合仍由团队共同确定。有效引用只能证明编号存在，不能证明模型对证据的解读正确。

旧的 `load_case → normalize_evidence(raw)` 方式仍可用。正式联调推荐 `prepare_case`：其 `snapshot_id` 同时绑定原始数据、规范化版本、证据映射和来源标签。仅保存 `source_sha256` 无法发现规范化代码改变后的旧引用。

## 当前边界

- 本仓库实现证据处理和只读工具；双方 Agent、Judge 的模型调用、回应轮次及最终展示仍需与队友集成。
- 官方 Markdown 的预期裁决单独存放在 `evaluation/official_expected.json`，运行时加载路径不读取该目录。
- 合成路线与规则属于联调用例；距离是采样折线计算，不能声称是地图最优路线或真实 Ryde 政策。
- 计时口径待主办方澄清；订单起点 480 秒、App 起点 470 秒、预约时间到取消 360 秒均保留，不自行选为收费依据。
- 本次开发由琪琪主导需求并由 Codex 辅助实现。尚无 CodeBuddy/WorkBuddy 实际使用证明；比赛要求的真实开发记录需要后续补足。

## GitHub 同步

远端应始终保持 **Private**。首次克隆及日常更新：

```powershell
gh repo clone Wenqi77Zhang/ryderesolve-evidence-tools
git pull --ff-only
```

在本地完成修改并测试后：

```powershell
git status
git add <本次修改的文件>
git diff --cached --check
git commit -m "Describe the evidence change"
git push origin main
gh repo view --json visibility,url
```

如果 Git 报 `Could not connect` 且明确指向本机代理 `127.0.0.1`，本次可用 `git -c http.proxy= push origin main` 或 `git -c http.proxy= pull --ff-only` 临时直连；该参数只影响当前命令，不改全局代理设置。

队友访问私有仓库需要你后续明确选择协作者。不要提交 `.venv`、密钥、真实乘客数据或个人邮箱内容。
