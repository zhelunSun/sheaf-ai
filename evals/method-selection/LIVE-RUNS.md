# 真实模型运行与复用

`run_experiment.py`、`protocol.md`、`lock.json` 保留首次冻结版本。网络执行是额外的显式
入口，默认 dry run，不读密钥、不调用模型。当前只接 Paratera，不自动切供应商或模型。
首轮调用边界见 [live_protocol.md](live_protocol.md)，接口修订边界见
[repair_protocol.md](repair_protocol.md)。本轮只发送仓内虚构材料，不发送用户知识库。

## 可重用的命令

仓库根目录运行；`--run-dir` 对应一份预算和源码锁。续跑必须保持模型和预算相同。
凭据默认从本机 `.workbuddy/models.json` 中明确对应 Paratera 的 DeepSeek-V4-Pro
配置读取；这是凭据条目，不是实际请求的模型。实际模型由 `--model` 显式固定。
也可使用 `--key-env PARATERA_API_KEY`，不支持其他供应商密钥回退。

```powershell
# 只准备配置检查，无网络；替换输出目录名称后再使用。
python evals/method-selection/run_live.py --model DeepSeek-V3.2-Instruct --run-dir NEW_RUN_DIRECTORY
# 显式付费调用：先探针，再续跑。
python evals/method-selection/run_live.py --model DeepSeek-V3.2-Instruct --run-dir NEW_RUN_DIRECTORY --execute --probe-only
python evals/method-selection/run_live.py --model DeepSeek-V3.2-Instruct --run-dir NEW_RUN_DIRECTORY --execute
```

以上保留首轮严格裸 JSON 协议以供诊断，不建议把该协议中已知的 ID 提示缺口复制到新
实验。后续新的干净协议应复用 `execute_request` 的传输/收据逻辑，并显式定义 ID 和解析
契约。本轮开发修订可用以下命令复现；两目录共同消耗原预算，不重复调用原文基线：

```powershell
python evals/method-selection/run_live_repair.py --parent-run PARENT_V1_RUN_DIRECTORY --run-dir NEW_REPAIR_DIRECTORY --execute
```

对本轮已完成的目录重跑，相同请求全部使用封存响应，`new_requests=0`。这是离线重放，
不是一次新的重复实验。想测模型随机性必须显式开新的预算/运行，而不能拿缓存当新样本。

## 故障怎样处理

- HTTP 错误、超时、模型 ID/usage 不一致：原样保存能安全保存的返回，停止后续调用；
  不自动重试，不调高预算。API 异常文字和 headers 不落盘，避免密钥泄漏。
- intent 存在而 result 缺失：供应商可能已经处理，状态不确定。人工核对，不自动重发。
- 原始正文不是有效卡片或引用错误：保留失败，不能人工补字段、改 quote 后冒充模型输出。
- 代码/输入/协议改变：新版本、新目录；不重写旧锁。请求 ID 相同但内容不同也拒绝复用。
- 150000 token 是运营守卫，不是经验证的供应商账单硬限额；预留算法不是 tokenizer。
  没有验证人民币单价，所以金额仍为 unknown；如需硬金额限制，应另配供应商账户限额。

## 文件怎样读

| 文件 | 用途 |
|---|---|
| `manifest.json` | 固定模型、预算、输入/代码版本；不包含密钥 |
| `calls/*.intent.json` | 发送前持久化的确切请求 |
| `calls/*.result.json` | 状态、原始供应商正文、usage、耗时、校验 hash |
| `*-plan.json` | 确切请求和准备阶段失败；回答计划保留真实上下文 |
| `*-provider-responses.json` | 修订版未经语义修补的模型文本 |
| `*-parsed-responses.json` | 仅外层格式处理后的文本，不冒充原文 |
| `normalization-audit.json` | 每条是否去除完整代码块，前后文本 hash |
| `result.json` | 原评分器的逐题结果；修订版明确 post-hoc 标记 |
| `usage.json` | 新调用、复用调用、两轮累计、各组独立部署 token 成本 |

正确方法、正确证据状态、引用定位和来源覆盖是分开的指标；不能从一个总准确率推断
所有维度都可靠，也不把引用可定位当作语义支持。来源引用错误不会被格式解析修复。

## 复利来自哪里

新增样本可复用请求/收据/预算/失败分母/评分流程，变化无需重做供应商接入。已有失败
可变成无网络回归测试，节省 API 调试。旧数据只作开发诊断；新方法效果仍需新来源组、
固定 token 约束和预先定义的指标。当前不是覆盖所有供应商和所有任务的通用评测平台。
