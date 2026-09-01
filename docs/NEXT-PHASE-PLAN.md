# Sheaf 下一阶段开发计划

> 当前阶段：核心算法证据
>
> 决策：先修复会让评测失真的核心契约，同时冻结离线评测资产；随后由失败样本
> 驱动算法加固。不是先堆复杂算法，也不是在错误实现上直接跑 benchmark。

## 1. 为什么这样排序

当前三条算法路径都已经有实现，但机制测试与真实效果之间仍有断层：

- 检索已覆盖生产 Entry 索引并冻结第一份 classical baseline，但还没有真实 embedding
  结果，而且当前混合配置没有胜过 keyword；
- 结晶验证了来源 ID 存在，却没有验证来源文本真的支持生成主张；
- 增量演化已闭合 span identity、来源折叠、纠错权限与 decision trace 契约，但生产
  SPLIT 原子执行器仍不存在。

如果先调融合权重、增加提示词或实现自动策略，得到的提升可能只是测试设计造成的。
因此当前阶段的第一目标是让“被测系统”与“实际产品路径”成为同一个系统。

### 2026-09-01 执行快照

本轮已经把几项会直接污染实验的风险变成代码门禁：

- Entry 已有独立语义索引、原子 manifest 和可诊断降级；快速离线评测现在走真实
  Entry index 和 retrieval service，不再注入最终语义分数；
- evidence use 已升级为 schema 3 的 `entry + claim + locator` 身份；`quote` 会在 Entry
  正文中唯一定位，`char_span` 会校验边界与文本，同一位置两种表达共享 identity；
  v1/v2 ledger 可按历史 algorithm/governance version 重放，并在下一次写入时迁移；
- `evidence-rule-v3` 只通过同一 `source_key`、可信版本化全文 `sha256` digest、或
  持久化的 `exact` / `near_duplicate` 关系形成 non-duplicate group；旧前缀 hash 和
  普通自声明 provenance 都不能覆盖去重；在可信 registry 建立前，这些 group 不发放
  独立确认奖励，有证据时 `independent_source_count` 保守为 1、corroboration bonus 为 0；
  v1/v2 历史评分保持原样重放；
- official correction 需要 primary 来源、覆盖当前 topic 与 fact key 的 authority
  scope，以及明确指向旧 Entry 的持久化 `corrects` relation；
- 结晶先校验原始 JSON，再构造卡片；非法 confidence、未解析引用、装饰性来源和
  错位 `related_to` 会失败关闭；
- G0-G3 的 model input 与 evaluator gold 已物理分离，case ID 改为不泄露动作的
  不透明编号，loader 和 mutation tests 共同检查分组可见字段。
- SPLIT/NOOP decision trace 已实现 preview、请求 hash、版本、证据、target head、状态
  与篡改检测；SPLIT 固定展开为共享 `decision_id` 的 UPDATE + CREATE，但只会调用外部
  `execute_atomic(...)` 协议。仓内没有 production atomic executor，只有 atomic fake
  测试，因此这仍是条件性协议而不是端到端能力。
- 检索评测已冻结 22 条 Entry、36 个 query；manifest 锁定 corpus/query/qrels hash，
  runner 在生成所有 ranking 后才加载 evaluator-only qrels。经典 local-LSA 的 dev
  选择为 `linear-0.25 @ 0.4`，留出指标是 Recall@5 `0.9375`、MRR `1.0`、nDCG@5
  `0.9498`、no-answer FPR `1.0`，没有优于 keyword；真实 embedding 因无凭据未跑。

这不是 M1-M6 已全部完成。下一阶段的硬问题收束为：无答案与实体歧义、真实
embedding、长文 passage、可信 provenance registry、实际 atomic split adapter、
Entry/卡片/向量索引的跨文件事务，以及真实 LLM 的结晶/演化实验。

## 2. 当前 P0 问题

### P0-A：检索评测与生产语义路径不一致（第一阶段已实现）

本轮之前，混合检索先搜索 KnowledgeCard 向量，再通过卡片 `source_ids` 映射回
Entry，未结晶来源只能参加关键词检索，CLI、MCP 和 HTTP 的默认路径也不一致。
现在三类接口已统一到 direct Entry hybrid path；向量索引需由
`sheaf search-index --rebuild` 显式引导首次构建，随后收藏流程增量维护。失败更新会
持久化 stale marker，旧索引仍可降级查询而不会伪装成完整覆盖。

完成标准：

- Entry 和 KnowledgeCard 使用明确分开的向量索引；
- 新增、重建、更新和删除 Entry 时，索引覆盖率和过期状态可观察；
- CLI、MCP、HTTP 共用同一个 retrieval service；
- embedding 不可用、索引为空和确实无结果具有不同诊断；
- 离线评测直接调用这条生产路径，不再注入最终语义分数冒充端到端结果。

### P0-B：证据复用粒度过粗（schema 3 span identity 已实现）

当前 ledger 已把两个概念分开：

- Entry 是否已经进入系统；
- 某段证据是否已经被用于某个主张。

schema 3 的证据使用身份绑定 `entry_id + claim identity + locator identity`。唯一
`quote` 与等价 `char_span` 解析成相同位置；无法定位、重复歧义、越界或文本不一致会
失败关闭。同一 Entry 的不同片段可以支持同一主张，但片段数不会增加证据强度。
无 locator 的 v1/v2 记录按 `whole_entry` 重放，精确请求重试仍由 idempotency key 和
request hash 负责。

### P0-C：SPLIT/NOOP 表示已闭合，production atomic adapter 仍开放

领域执行器仍只有 CREATE、UPDATE、MERGE、RETIRE、CONTEST，并且一次事件只产生一个
版本。现已冻结并实现上层边界：

- executor 保留原子领域动作，不把 SPLIT 做成含义重叠的新动作；
- policy 的 SPLIT 计划展开为共享 `decision_id` 的 UPDATE + CREATE；apply 前必须确认
  target head 未变化；
- NOOP 记录在 policy decision trace 中，不制造无意义的卡片版本；
- decision trace 使用 append-only hash chain、原子文件替换、幂等键和请求 hash；
- 只有调用方提供明确的 `execute_atomic(...)` 批处理协议时才执行 SPLIT，否则失败关闭。

仓内测试 fake 能证明 policy 只发一次包含两项操作的 batch，也能模拟失败时无半个
split；它不能证明现实存储具有原子事务。下一步必须实现真正的 evidence-memory
atomic adapter，并补进程中断与落盘失败测试；不能用两次普通 executor 调用伪装原子。

### P0-D：来源独立性 v3 已实现，可信 provenance registry 仍开放

`evidence-rule-v3` 用并查集合并三种有审计依据的边：同一 `source_key`、可信版本化
全文 SHA-256 evidence digest、以及收藏时计算并持久化的 `exact` /
`near_duplicate` relation。系统会在 rationale 单独报告 non-duplicate group 数；镜像
仍保留为来源记录，空/短/格式错误的 hash 不参与跨域折叠。

普通自声明 provenance（例如声称独立观察）绝不覆盖上述去重；未判定 pair 既不会被
自动标为独立，也不会自动折叠。由于当前仍缺可信 provenance registry，v3 不把这些
group 当作已验证独立来源：有证据时 `independent_source_count` 保守为 1，
corroboration bonus 固定为 0。v1/v2 只用于历史重放，保持各自旧评分。下一步必须定义
谁可以写入或签署独立观察、转载和纠错关系，以及关系失效/更正如何治理。

## 3. 正式实验前同轮关闭的可信性问题

以下问题不一定都阻塞第一行代码，但必须在对应路径的正式结果发布前关闭：

| 风险 | 当前表现 | 处理位置 |
|---|---|---|
| 原始模型输出被“洗白” | 已在对象构造前校验 raw JSON，错误类型、NaN、越界 confidence 与非法来源关系均失败关闭 | 保留 mutation test，并在真实 LLM 评测中保存 raw response/warning |
| official correction 权限过宽 | 已要求 primary + topic/fact-key scope + 指向目标 Entry 的 `corrects` relation | 下一步由可信 provenance registry 管理谁能写入/签署这些关系 |
| gold 泄漏 | G0-G3 与检索集均已物理拆分输入和 evaluator-only gold；检索 ranking 先于 qrels 加载 | 保留 loader/mutation test 与 manifest hash 门禁 |
| 测试数据隔离不完整 | 多个模块 import 时冻结全局路径，fixture 靠手工 patch | M2 加写入 guard；平台流逐步改为 runtime settings 构造注入 |
| 长文档静默截断 | 来源先截 3000 字符，prompt 再截 2000 字符 | M4 用检索选段并记录 chunk/selection manifest |
| 多文件持久化不具事务性 | Entry、index、card、embedding 可能在崩溃或并发下不一致 | M3/M4 先加锁、原子替换和 generation manifest；是否迁移 SQLite 由故障证据决定 |
| SPLIT 伪原子 | decision trace 已要求外部 atomic batch，但仓内无 production adapter | 实现跨 UPDATE + CREATE 的真实事务 adapter；中断/失败时不得留下半个 split |
| 旧卡来源迁移丢失 | singular `source_id` 复制后会被 schema 忽略 | 发布前显式迁移到 `source_ids` 并用旧版 fixture round-trip |

## 4. 六个里程碑

| 顺序 | 里程碑 | 可并行关系 | 退出证据 |
|---|---|---|---|
| M1 | 证据身份、独立性与协议闭环 | **核心契约已完成** | schema 3 span identity、v3 来源折叠、authority scope、旧 ledger 重放和 conditional split/noop trace 已有测试；production atomic adapter 与可信 registry 转入后续 |
| M2 | 冻结无用户评测资产与当前基线 | **首轮完成** | G0-G3 输入/gold 隔离；检索 22/36 fixture、manifest hash、排名和负结果已入库 |
| M3 | 真正的 Entry 级语义检索 | **本地基线完成，live 未完成** | 三接口统一、索引与诊断可观察；local-LSA 已跑但未胜 keyword；仍需真实 embedding、无答案/歧义和长文实验 |
| M4 | 原子主张与可验证证据结晶 | **部分完成** | raw JSON 与 quote/span 边界已有门禁；仍需 passage selection、entailment/conflict 标注和真实模型评测 |
| M5 | Preview-only 增量转移策略 | **协议完成，集成未完成** | trace 可审计且 fail closed；仍需真实 atomic adapter、action policy 与 abstention 留出评测 |
| M6 | 正式消融与面试证据包 | 进行中 | 检索已有可复现负结果；结晶、G0-G3、真实 embedding/LLM 仍缺完整原始输出与指标 |

## 5. M2 评测资产范围

### 检索集

首版已经冻结 22 条 synthetic-but-realistic Entry 与 36 个 query，覆盖：

- 精确术语与标题；
- 同义改写和自然语言问题；
- 版本化事实与时间条件；
- 长文档中部或尾部信息；
- 中英文混合表达；
- 无相关结果和容易混淆的近邻来源。

`corpus.jsonl` 与 `queries.jsonl` 是 ranker-visible input，`qrels.jsonl` 只供 evaluator
使用；`manifest.json` 锁定三者角色和 SHA-256。runner 先生成 keyword、semantic、线性
融合与 RRF 的全部 ranking，之后才加载 qrels，并用 dev 选择参数、test 只做最终比较。

当前唯一 checked-in 模型是经典 TF-IDF/SVD `local-lsa-v1`，不是 neural embedding。
dev 选中 `linear-0.25` 与 `min_evidence_score=0.4`；held-out 为 Recall@5 `0.9375`、
MRR `1.0`、nDCG@5 `0.9498`、no-answer FPR `1.0`。同集 keyword 为 `0.9688`、
`1.0`、`0.9560`、`1.0`，所以 selected method 没有胜出，也没有解决 abstention。
live embedding 因缺少凭据未运行。下一轮不改 gold，围绕无答案、实体歧义、真实
embedding 与长文 passage 扩展 failure slice。

### 结晶集

首版建立 12–20 个来源 bundle，包含一致证据、局部冲突、版本变化、转载、长短文档
条件差异和无充分证据。标签以原子主张为单位，记录：

- 哪些来源和具体片段支持主张；
- 哪些来源冲突或只提供背景；
- 主张是否遗漏条件、日期、版本和数值单位；
- 与其他卡片是否语义重复。

先比较单来源摘要、无来源约束的多来源生成和 Sheaf 约束版本。模型自报 confidence
不能直接当作正确概率。

### 增量演化集

在现有 4 个案例上补充到至少 10–12 条证据序列，覆盖：

- 一个来源支持多个主张；
- split、noop、merge 和 retire；
- 官方来源自身纠错；
- 转载不计作独立确认；
- 无关噪声、含糊版本和低信息来源；
- 中途失败后的重试与重放。

模型输入和 evaluator-only gold 必须物理分开。任何组都不能看到 gold；G2 还不能看到
source tier、source kind 和审计要求。M2 只冻结数据、标签和当前 baseline，不为了
得到漂亮结果而修改 gold。

## 6. M3–M5 的算法加固方向

### Entry 级检索

- 独立的 Entry embedding 文本和索引 manifest；
- 模型、维度、内容 hash、Entry revision 和索引 revision 明确记录；
- 相关度阈值、稳定 tie-break 和可解释 fallback；
- 比较线性分数融合与 reciprocal rank fusion，再用评测选择而非凭感觉选择；
- KnowledgeCard 搜索保留为另一种对象检索，不再借它模拟 Entry 语义检索。

当前 `coverage-semantic-v1` relevance gate 是 backend/version-specific 实验信号，不是
概率或可迁移到任意模型的通用阈值。只有健康 `entry_index` 的语义分数才参与该标尺；
语义索引降级时，gate 回到 keyword query-coverage scale。选中的 `0.4` 只属于当前
local-LSA/dev split，不能直接成为产品默认值。

### 可验证结晶

- KnowledgeCard 的 evidence 从一段自由文本逐步升级为
  `source_id + quote/span + relation`；
- KnowledgeCard 构造前先验证模型 raw JSON，拒绝 NaN、越界 confidence 和错误字段类型；
- 引文必须在规范化来源文本中可以定位；
- 输入选择检索出的相关段落，不再只截文档开头；
- 多来源要求、单来源例外和来源独立性由执行层检查；
- 保存 prompt、raw response、warnings、模型和算法版本；
- 将模型 confidence 与确定性 evidence strength 分开。

### Preview-only 增量策略

- 分开事实抽取、旧 claim 检索、动作建议和确定性 executor；
- 先输出 preview，用户或上层 Agent 明确 apply 后才改变知识；
- 已有 decision trace 记录输入快照/request hash、policy/algorithm version、证据、目标
  head、原因、操作与状态，并用 append-only hash chain 检测篡改；
- SPLIT 只能通过 production atomic adapter 一次提交 UPDATE + CREATE；当前仓库没有该
  adapter，不得把 atomic fake 或两次顺序调用写成产品能力；
- G2 与 G3 共享 executor，只改变 policy 可以看到的信息和治理规则；
- 低证据或无法区分 UPDATE/CONTEST 时必须 abstain；
- 结晶卡片最终进入同一 evidence ledger，避免长期维护两个平行知识系统。

## 7. 下一轮开发安排

```text
Lane A — 检索失败切片
  no-answer / 实体歧义 -> 真实 embedding -> 长文 passage -> 冻结复跑

Lane B — 来源治理
  可信 provenance registry -> duplicate/correction relation 写入权限 -> 迁移与审计

Lane C — 原子演化集成
  production atomic split adapter -> 跨进程失败测试 -> G0-G3 policy/abstention 评测

Lane D — 可验证结晶与持久化
  passage selection -> entailment/conflict labels -> 真实 LLM -> Entry/card/index 跨文件事务
```

四条 Lane 可以并行，但共享两个发布门槛：不得在真实 embedding 前把 local-LSA 写成
模型效果；不得在 production atomic adapter 前把 SPLIT trace 写成原子执行能力。
任何阈值调整只能用 dev，held-out test 与 evaluator-only gold 保持冻结。

## 8. 暂不进入主路线

- 新增大量网站适配器，除非它阻塞评测语料；
- 知识市场、交易或复杂协作；
- 没有真实瓶颈证据的大规模数据库重写；
- 为了展示而增加没有基线和失败样本的新算法名词；
- 在 G0-G3 前宣称自动增量演化优于 batch crystallization。

## 9. 当前阶段的完成定义

只有同时满足以下条件，才进入“自动演化策略”阶段：

1. 三条路径的评测调用真实生产服务；检索至少完成一轮真实 embedding；
2. schema 3 身份、v3 来源独立性和 authority scope 保持关闭，同时补齐可信
   provenance registry 与 production atomic split adapter；
3. 固定数据、标签、原始输出和指标可由一个命令复现；
4. raw 输出校验、gold 隔离、数据路径隔离和关键持久化风险有回归门禁；
5. 无答案、实体歧义、长文 passage 和跨文件事务有明确失败样本与门禁；
6. 至少一轮算法消融包含负结果和失败切片；
7. README 和演示只使用实验真正支持的结论。
