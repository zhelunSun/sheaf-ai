# DeepSeek-V4-Flash 实验：接口跑通，开发集已饱和

工作分支 `codex/retrieval-abstention`，起点 `c9d2c82`。本轮只增加新的实验版本、真实
结果、测试和阶段文档；不覆盖旧 `DeepSeek-V3.2-Instruct` 结果，不改变生产默认模型。

## 1. API 与模型先独立验证

独立子智能体只读检查本机模型登记，并对候选接口各做一次小生成，不修改配置、不输出
密钥。Paratera 的认证模型列表返回 HTTP 200，列出 96 个模型，并包含
`DeepSeek-V4-Flash`。本机没有同名的 Paratera profile，但现有 Paratera 凭据对端点有效；
profile 是凭据记录，不限定 `--model`。

| 路径 | 实际请求模型 | 结果 | 解释 |
|---|---|---|---|
| Paratera | `DeepSeek-V4-Flash` | HTTP 200，实际 model ID 一致 | 可用于本轮实验 |
| SiliconFlow | `deepseek-ai/DeepSeek-V4-Flash` | HTTP 200，实际 model ID 一致 | 同名模型也可用，但不是本轮后端 |
| GLM Coding Plan | `glm-5` | HTTP 429 | 只记录失败，不猜测额度或策略原因 |

这些探针只证明当时能完成最小生成，不证明质量、稳定性、价格或生产适配。供应商单价和
账单未核实，因此所有实验金额保持 null。

## 2. 先保留一次真实失败

首个 Paratera Flash 轮使用默认输出控制。128-token 精确 JSON 探针成功；随后两个抽取
请求均为 HTTP 200，却把各自 4096 completion tokens 全部用于 reasoning，正文为空、
`finish_reason=length`。第三个抽取已有 intent、无 result，人工中止后状态不确定，未自动
重发。已完成三次调用共 9073 tokens，另有一次可能已计费但 usage 未知。

失败目录
`evals/method-selection-v2/runs/paratera-deepseek-v4-flash-20260905-v1/` 原样保留。
它证明“接口 HTTP 200”不等于“业务正文可用”，也说明 hidden reasoning 必须计入输出预算。

随后使用同一小探针、无重试检查三个控制参数：`reasoning_effort="none"` 和
`thinking={"type":"disabled"}` 均返回正常 JSON 且 reasoning token 为 0；
`enable_thinking=false` 仍报告 12 reasoning tokens。新 revision 选择第一个参数，把请求
选项和执行代码 hash 同时绑定进 manifest。这个修订解决传输/输出控制，不是算法改进。
当前 intent 绑定 logical request、manifest 和注入代码，但没有另存完整的 on-wire payload；
因此 0 reasoning tokens 是强一致性证据，不应夸大为逐字网络载荷证明。下个 runner revision
应在脱敏后保存 effective payload hash。

## 3. 新实验到底改变了什么

v1 的已知错误不是因为 JSON 不够漂亮，而是证据含义和作用域不清：无关方法的冲突会
污染当前方法，资源要求不满足被叫作来源冲突，未报告维度及实际测量范围容易丢失。

v2 使用六个全新虚构来源包、十二个问题，比较：

- `raw`：完整原始来源；
- `all_facts`：一次中立抽取形成的全部原子事实；
- `scoped_facts`：从同一事实集合中确定性保留当前任务 options 涉及的方法和 bundle 级
  缺失事实，不读取 gold，也不按答案状态过滤。

抽取把能力、要求、明确否定、测量结果和未报告维度分开，并另存适用条件、测量范围和
明确未测范围。三组使用同一个决策提示和模型。输入与 evaluator-only gold 物理分开；
回答全部收齐并核对 ID/hash/model/usage 后才评分。

样本作者已知道 v1 错误类型，所以证据等级是
`prospective_synthetic_development_only`，不是独立外部留出。

## 4. Paratera Flash 实际结果

修订轮实际完成 **43 次请求、27028 tokens**：1 次探针、6 次抽取和 36 次回答。所有
receipt 均为 HTTP 200，实际 model ID 为 `DeepSeek-V4-Flash`，provider 报告 reasoning
tokens 合计为 0。38 个响应原样解析，5 个只移除了完整 JSON 代码围栏。

| 表示 | 方法正确 | 状态正确 | 引用定位 | 必需来源 | 四项同时正确 | 独立使用总 token |
|---|---:|---:|---:|---:|---:|---:|
| 原文 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 5008 |
| 全量事实 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 13829 |
| 任务范围事实 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12303 |

事实构建本身使用 4157 tokens；事实组独立使用总量都承担全部构建成本。作用域过滤相对
全量事实节省 1526 tokens，约 11.0%，但仍是原文的 2.46 倍。这里的原文很短，不能把
这个成本关系推广到长文或高复用场景；三组也没有相同 token 输入。

人工逐题复核确认四个目标错误都被正确处理：

- 只问 D/N 时，C/M 的冲突没有污染选择；
- 8 GB 不满足 E 的 12 GB 要求且 F 不能本地运行，状态是 `explicit_negative`，不是 conflict；
- 防水未报告、视频未测量时状态是 `insufficient`，并引用明确缺失说明；
- version 1 与 version 2 的能力没有串用。

独立复核同时发现，自动“引用定位 12/12”高估了引用自足性。事实组部分短 quote 只包含
“L 支持透明 PNG”“H 测得 18 小时”或“每秒 120 项”，版本、测量维度、batch 等限定来自
结构化 statement/conditions，而不在该 quote 本身；`cannot run locally` 也没有在片段内
写出 Method F。它们在完整上下文中可追溯，但不能仅凭 quote 自证完整含义。下轮需要把
“字符串能定位”和“引用自身支持带限定语的判断”分成两个指标。

不过抽取仍把“Method C 的差异尚未裁决”归入 `unreported_dimension`，且
`not_evaluated_scope` 为空。它没有影响当前答案，却表明现有类型不能干净表达“争议存在、
尚无裁决”。自动评分只验证引用可定位与必需来源覆盖，不自动证明每个抽取标签语义正确；
这项人工发现必须保留。

机器结果见[评分](../evals/method-selection-v2/runs/paratera-deepseek-v4-flash-no-reasoning-20260905-v1/result.json)
和[用量](../evals/method-selection-v2/runs/paratera-deepseek-v4-flash-no-reasoning-20260905-v1/usage.json)。

## 5. 这次能说明什么，不能说明什么

可以确认：

- Paratera 当前能实际运行 Flash；关闭隐藏推理后，完整调用、封存、评分与重放链路可用；
- v1 暴露的条件、冲突作用域、缺失报告和连续引用问题已经成为可重复的回归资产；
- 任务范围过滤能减少全量事实上下文，但在本集合上没有质量差异。

不能确认：

- 结构事实优于原文。三组全对更可能说明任务对当前模型过易；
- Flash 优于旧 V3.2。模型、数据、提示和输出控制同时变化，不是公平代际比较；
- 11% token 差异在真实知识库一定转化为费用或延迟收益；
- 这套方法已通过用户验证、外部留出或科学新颖性检验。

因此本轮不是漂亮分数的终点，而是一个诊断：接口和语义门槛已经足够稳，可以停止在
当前十二题上继续局部调参；下一步应提高任务真实性和区分度。

## 6. 可复用资产与下一阶段

新增 runner 具备 fail-closed schema、gold 隔离、请求/执行指纹、预算、无自动重试、
不确定发送停止、原始响应和标准化审计。成功轮已在禁止网络的 transport 下完整重放，
43 个既有 receipt 被复用、没有发出新请求；实验树对本机四个凭据值逐文件扫描，匹配 0。

下一轮优先做“真实难度的结晶/表示实验”，而不是增加字段：

1. 由未参与当前实现的人独立编写较长、多噪声、多方法、多版本来源；当前十二题只回归。
2. 在相同输入 token 预算下比较原文 passage、全量事实和任务范围事实，拆开“清楚提示”
   与“结构/过滤”的贡献。
3. 增加一份人工语义账本，检查抽取类型与引用是否真正蕴含结论，而非只检查字符串定位。
4. 模拟同一来源库被查询 1、5、20 次，报告构建成本摊销、查询 token、错误率和更新代价。
5. 新数据若仍三组接近且事实组更贵，停止扩大这套 schema，转向增量动作策略的留出实验。

生产 SiliconFlow 默认仍保留 V3.2：本轮只验证了实验后端，未完成迁移兼容、价格、质量和
回退测试。后续若要升级产品默认，应单独注册 Flash、保留旧模型可选并跑生产契约回归，
不能让一次合成实验静默改变现有用户配置。

## 7. 工程门禁

- v2 定向测试 10/10 通过；全量回归 **1518 passed、20 skipped**。
- Ruff、新增差异检查与核心离线评测通过；后者仍只测确定性 fixture，不是 live benchmark。
- 隔离 sdist/wheel 构建通过；新 venv 中 metadata、CLI 和 MCP stdio smoke 均通过。
- 本机全局 setuptools 不满足项目声明的 `<77` 时，`--no-isolation` 构建按预期失败；使用
  pyproject 声明的隔离环境后成功。这是环境依赖门禁有效，不是隐藏源码失败。
- 未发布、未推送、未修改用户模型配置或生产默认供应商。
