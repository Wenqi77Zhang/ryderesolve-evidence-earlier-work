# 数据核对记录 · 2026-10-02

## 官方输入

用户提供的 [RydeResolve Sample Dataset — DISP-002](https://drive.google.com/file/d/1f6KAuu5ZFqBKHvsAVlg-ZC_FgHazbqNF/view) 为一份 Markdown，包含一个 No-Show Charge JSON 案例、Evidence Summary 和预期裁决。

导入时只提取 JSON，保留全部原始值，不修改记录以配合预期裁决。其数据是主办方样例，不能据此断言是真实运营数据。原文件中的姓名、车牌及历史档案也不代表经过独立核实的真实人员信息。

## 480 秒、470 秒与 360 秒

| 原始位置 | 记录 |
|---|---|
| /trip_data/driver_wait_start | 2026-09-13T08:43:00+08:00 |
| /trip_data/scheduled_time | 2026-09-13T08:45:00+08:00 |
| /app_events/5/timestamp | 2026-09-13T08:43:10+08:00（wait_timer_started） |
| /trip_data/cancellation_time | 2026-09-13T08:51:00+08:00 |
| /cancellation_policy/no_show_threshold_min | 8 |

按订单起点计算是 480 秒，按 App 事件起点计算是 470 秒，按预约时间到取消计算是 360 秒。原政策未说明 clock basis，也未说明提前到达的等待是否计入。模块报告 `WAIT_START_DISAGREEMENT / POLICY_CLOCK_BASIS_UNSPECIFIED / WAIT_START_BEFORE_SCHEDULED_PICKUP`，不会选定其中一种作为收费依据。

另一个细节：计时开始事件的文字写免费等待结束于 08:48，但 `wait_timer_expired` 的事件时间为 08:48:10。原始文字与时间均可回查；当前自动审计的时间冲突检查覆盖订单/App 起点，不解析任意自然语言中的时间承诺。

## 陈述、记录与推导

- `dispute_ticket.description` 证明乘客提出过该陈述，不直接证明司机未到场。该条在当前来源版本中是 `E-002`，类型为 party_statement。
- GPS 的索引 4、5、6、7 分别为 08:43、08:45、08:48、08:51：坐标与上车点相同，速度为 0。这是四条离散记录，不是连续每秒观测。
- App 事件中“通知已发出”不等于乘客已阅读；“8 分钟门槛达到”属于事件记录的结论性文字，不能覆盖独立时间计算。
- 聊天记录含 4 条司机消息、1 条未接通呼叫记录、1 条系统记录。没有乘客消息记录，不足以证明乘客没有在其他渠道尝试联系。
- 双方历史评分、投诉数和欺诈标记单列为 historical_context，不生成“本次说谎/可信”的事实结论。

## 答案隔离

主办方预期裁决为 uphold_charge，仅存放在 `evaluation/official_expected.json`，不打包进入运行时安装包，也没有 HTTP 读取接口。该标签可供 Judge 负责人对照，但不能解除政策歧义。

单个样例不构成判决准确率基准。当前测试验证数据与接口行为，不验证 LLM 裁决准确率或真实业务效果。

## 合成 Route Deviation

`SYN-ROUTE-001` 的人物、时间、坐标、聊天、费用及规则均由本项目为联调构造。文件、catalog、API 审计和网页都保留 synthetic 标签；规则标注 team_authored_synthetic_not_official_Ryde。

用 Haversine 公式（依据经纬度计算球面距离）累加采样线段，展示实际采样路线和给定参考路线的长度与比例。稀疏采样、真实道路及实时交通未建模。参考路线不宣称是最优导航路线。

v0.2 的计算先按已记录的行程开始/结束时间选择 GPS 点，保留被排除点的原始索引；缺少时间窗口、未观测到边界或存在同一时刻不同坐标时均会提示。没有插值补全路线，也不凭采样间隙大小直接判断异常驾驶。

金额使用 SGD 的整数分：实际扣费 1500 分、参考报价 1000 分、差值 500 分。该差值不等于已裁定退款金额。司机给出的交通理由在合成聊天中只是陈述，没有独立交通证据；Judge 应结合自设规则处理这一不确定性。

路线计算不会解除 `ROUTE_JUSTIFICATION_REQUIRES_REVIEW`；该提示要求下游审查改道理由和额外收费依据，并不代表所有路线争议都已被自动判定必须转人工。
