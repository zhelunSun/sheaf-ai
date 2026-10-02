# Sheaf 下一阶段开发计划

## 当前计划：从可运行的知识工具到持续使用的产品（2026-09-28）

**产品方向：Sheaf 让你的 Agent 用上你挑选的资料和形成的判断，并帮助你决定哪些内容值得亲自读。**

“Agent 时代的个人知识基础设施”保留为长期定位。近期用收藏入口、可检查的来源和已有
Agent 把这个方向做实；不要求用户先教系统品味，也不要求先生成知识卡片。产品共识与
能力边界以[产品设计入口](PRODUCT-DESIGN-INDEX.md)为准，具体功能及验收以
[功能队列](PRODUCT-FEATURES.md)为准。本节替代下方历史技术计划中的开发顺序。

### 2026-09-28：把工程修补接到产品循环

产品顺序仍是现有 Agent 复用资料、核查来源、按实际阻碍完善入口。近期技术审查进一步
明确了依赖：收藏结果应区分“原文已保存”和“模型整理完成”；当前条目纠正后，过期的
向量或展示内容应可识别，并有明确的回退/恢复策略。这些是待完成的修补，不能由现有
机制或界面展示推定已实现。

因此，PF-01 展示上游提醒前先保证阶段状态准确；PF-03 仍可使用现有接口开始有界自用，
但要记录已知降级，不把它当作效果验收。当前条目的事实纠错与 PF-04 的后续偏好应用
是不同需求。最小隔离备份/恢复用于保障使用，PF-06 之后再将其产品化。

具体可靠性候选的实现、主版本集成和发布分别验收；当前 PF-01 至 PF-07 的状态仍为
`planned / not-started`。新增算法实验只选择真实任务最突出的一个失败点，保留原文和
简单检索对照；不同时铺开检索、结晶和自动演化三条效果实验。

### 已确定的边界与待验证的选择

- 零反馈时就提供价值；收藏表达关注，不等于认可内容。用户原话、来源观点和 Agent
  推断应能分清，不能由一次收藏自动制造“用户判断”。
- 自动清洗、分类、质量提醒与来源线索继续复用。反馈应顺手、可选；不以反馈次数
  或训练出完整品味模型作为早期成功条件。
- Skill/MCP 是接入现有 Agent 的方式；Sheaf 的增量要在找回资料、减少重复查找、
  保留依据和有效复用上证明。无需为格式差异另造生态。
- 卡片与版本治理保留为可选能力。既有安全、持久化和回归要求继续有效；新的研究
  实验由真实失败驱动，不把完成整条算法研究路线作为小型试用的前置条件。
- 知识交易、持续维护的专业知识服务、链上授权与结算均为待验证选项。先证明个人
  使用价值，再证明别人愿意为某项具体增量付费；市场和 Web3 不是默认终点。

**暂定首批用户：** 已经日常使用 Agent 做 AI/技术研究与选型的人，围绕一个持续问题
反复找资料。它是验证起点，不是最终市场选择。科研阅读用户也是候选；不同时承诺
覆盖所有知识工作者。作者尚待选择首批群体和实际投入时间。

### 形态如何进化

| 阶段 | 用户接触到的形态 | 必须看见的结果 | 何时进入下一阶段 |
|---|---|---|---|
| A：自己持续使用 | 现有浏览器收藏入口 + 轻量来源详情 + 已有 Agent | 不填画像也能收藏、检查来源，并在真实任务里用上资料 | 连续一周在正常工作里走通；已记录主要阻碍、处理失败及成本 |
| B：少量外部试用 | 同一条流程，加清晰安装与故障提示；按需阅读建议 | 外部用户能理解用途，并愿意再次使用，不靠演示脚本和开发者陪跑 | 建议先邀 3–5 人，至少 2 人在连续两周自发复用；这些是试验门槛，不是市场验证 |
| C：可依赖的小产品 | 可恢复的数据、稳定更新、按真实需要增加的入口 | 用户愿意留下资料、能迁移恢复；支持和成本可承担 | 重复使用持续出现，并有明确付费试用；未满足时缩小场景或改流程 |
| D：可持续的细分产品 | 围绕已证明需求提供付费服务；需要时再做独立工作台 | 客户持续得到结果，愿意续用/续费，维护成本可控 | 扩大用户前观察续费、流失原因、支持负担；另行决定专业知识交付是否值得尝试 |

独立 App、移动端、完整阅读器和云同步没有预定上线顺序：如果重复使用被跨设备收藏
卡住，优先解决入口；如果用户一直在 Agent 中使用，Sheaf 可以长期保持轻量界面。
基础设施的可信度来自可带走、可恢复、可接入和可持续使用，不取决于界面规模。

### 建议节奏与首个 sprint

以**每周 10–15 小时、单人负责产品并由 Agent 协助开发**为暂定容量：阶段 A 约 2–3 周，
阶段 B 再约 3–5 周，阶段 C 再约 6–10 周。阶段 D 取决于此前证据，不排固定日期。
时间是容量估算，不是交付承诺；每周只有 5–8 小时时，减少并行事项并延长日历时间，
不能靠取消真实使用和维护工作维持进度。

首个 sprint 只安排：

1. **PF-01：** 将已有质量提醒与来源线索显示在收藏结果中。
2. **PF-02：** 从收藏、最近列表和搜索返回来源详情与原文。
3. **PF-03：** 在一个现有 Agent 客户端完成有出处的任务复用；资料不足时明确说明。

PF-03 从首日使用现有接口尝试，不等待界面完善；容量不足时保留 PF-03 与最阻塞
使用的一项入口改进。以上均为待实现规格，不因为已有底层机制就标记完成。
按需阅读建议 PF-05 可在阶段 B 开始时轻量试用；
可选纠正 PF-04 只在出现重复纠正需求时推进。它们没有“先教会再推荐”的依赖关系。

阶段 B 收集一次简短安装观察和每周一次自愿回访即可，不建设后台行为采集系统。
分享真实资料前先明确处理范围；用户不必交出全部知识库或完整对话。开始保存外部
用户资料前，应有可操作的本地备份/恢复步骤；阶段 C 再通过 PF-06 产品化导出与
隔离恢复。PF-07 检查第二客户端交接，不强迫所有用户采用多个 Agent。

### 怎么知道值得继续

用一张小记录表即可观察：用户当时要做什么、原来如何找资料、Sheaf 实际改变了什么、
是否愿意再用、额外检查/纠正时间和模型成本。正常使用不要求每次打分。重要的失败
也记录：漏收正文、错误代表用户立场、引用不支持结论、找回资料比手工更费事。

复用与阅读建议分别看结果：前者是否减少重复查找并帮助完成任务，后者是否让用户
更快选定值得亲读的内容。引用数量、工具调用、卡片数量、收藏连续天数都只是过程
信息。安装成功、工程回归通过、真实使用有效、愿意付费是四种不同结果。

首批访谈和反复试用若未出现价值，先定位入口、任务选择或输出的问题；不自动通过
增加图谱、评分字段或模型复杂度补救。阶段 C 的付费试验应围绕实际节省的工作与
持续服务展开，不先假定知识包交易或订阅就是成立的商业模式。

### 保留、推迟与不变的工程要求

| 处理 | 范围 | 理由 |
|---|---|---|
| 优先连接 | 采集、分类筛选、原文/摘要、检索诊断、MCP、轻量来源核查 | 已有基础最接近用户任务中的直接收益 |
| 按失败修补 | 抓取、输出完整性、出处支持、安装更新、恢复、成本与超时 | 决定用户是否能放心持续使用 |
| 保留但不继续扩张 | 卡片表示、证据账本、自动增量策略、复杂图谱和评分校准 | 已有机制有用与新机制必要，需分别证明 |
| 暂不建设 | 重型品味对齐、完整阅读器/社交社区、知识市场、链上交易 | 缺少当前任务需求和付费证据 |

涉及公开接口先按仓库规则登记；涉及存储先说明兼容与恢复路径。每个实现只做与
改变的用户流程匹配的回归和检查，发布仍按[发布清单](RELEASE-CHECKLIST.md)执行。
本轮更新不运行新模型实验、不改实验分数、不宣称新功能已交付。

### 作者需要作出的少数选择

1. 从 AI/技术研究选型，还是科研/论文阅读切入，并提供一个自己每周都会遇到的任务。
2. 每周实际愿意投入多少时间，其中能否留出接触 3–5 位潜在用户的时间。
3. 进入外部试用后，根据观察选择最重要的价值：任务中复用，或更快决定亲读内容。
   当前先把复用做通，阅读建议轻量验证；这是可修订的顺序，不是永久产品边界。

## 历史技术计划与证据（以下不再决定当前开发顺序）

下方原始计划保留了当时的判断与负结果，其中“下一步”“只做”“当前阶段”均按其
日期理解。技术保证与证据边界继续有效；后续安排以本页 2026-09-28 当前计划为准。

### 2026-09-22 阶段快照：生产链路加固，准备小型真实效果验收

见[本轮交付](HARDENING-2026-09-22.md)。完整JSON、明确的结晶结果状态、跨CLI/MCP/HTTP
诊断、保守精确去重和卡片文件内原子批保存已实现；模拟用户脚本封闭任意shell入口，
默认不调用模型。普通卡与版本账本仍不自动合并，来源号可解析仍不等于主张得到证实。

旧v3响应的离线诊断没有提高原分数：310条事实有6条非逐字引文，4组超量；84个实际
答案的结构字段全部形式自洽，故理由/结论语义矛盾不能靠JSON规则解决。

下一项只做生产结晶的小型新样本验收准备，保持原文强基线、条件/否定/版本/冲突分层、
完整失败分母及构建/查询成本。先冻结协议和无网络回归，再决定真实模型调用；不扩大
schema、图谱或自动增量策略。搬迁验收保留为后续产品加固，不冒充已经验证可迁移性。
以下阶段文字为历史快照。

## 2026-09-05 当前阶段交付：长来源实验完成，先修输出契约

见 [长来源实验报告](LONG-SOURCE-EXPERIMENT-2026-09-05.md)。8组来源、24题、三组方法、
两次回答的全144个评分位置已收口，含60个抽取不可用位置。保留原始截断失败，分别
冻结输出额度及实际JSON文本预算修订；累计132次调用、253378 tokens，未超过原预算。
最终首轮72个位置有独立智能体语义审核，完整证据可禁止网络重放。

原文决定正确35/48，两种事实组12/48、13/48；事实抽取仅3/8组通过契约，不应把这些
全分母数字解释成结构表示的普遍优劣。三组可用构建的事后子集到20次查询仍未摊平成本。
实验还暴露最终字段与理由矛盾，以及包装前token预算漏掉JSON转义的测量问题；后者已
单独修正，原表未覆盖。当前事实替代原文方案No-Go，不迁移生产默认、不宣称算法获胜。

下一阶段只做R2输出契约加固：区分超量、逐字引用不匹配和语义状态混淆，评估单条
事实隔离与共同配置去重，检查最终决定/理由矛盾的显式失败路径。先离线修复，再以
新独立小样本验收；当前集合只作已知失败回归。不新增字段、图谱、功能或大型调用。
R3增量策略仍保留，但先解决已经阻断比较的输入输出问题，不把抽取失败直接当作
“表示无价值”的证据而跳过修复。以下旧阶段记录保留为历史快照。

## 2026-09-05 前阶段：Flash 接口与条件/作用域实验完成

见 [DeepSeek-V4-Flash 实验](DEEPSEEK-V4-FLASH-EXPERIMENT-2026-09-05.md)。Paratera 当前
可实际运行该模型；默认隐藏推理造成的空正文失败已保留，manifest 绑定
`reasoning_effort="none"` 后完成 43 次请求、27028 tokens。原文、全量事实和任务范围
事实在新的十二题开发诊断上均为 12/12。任务范围过滤相对全量事实少约 11% token，
但未产生质量差异且仍明显贵于短原文。

这意味着当前集合已经饱和，不再用于调字段或宣称结构收益。下一阶段继续 R2，但改为
独立编写的长来源、相同输入预算、人工语义审查和多次复用成本曲线；若新集合仍无质量
收益，停止扩展表示 schema，转向 R3 增量动作策略留出实验。生产默认模型不随本轮
合成诊断静默迁移。

## 当前阶段交付：Paratera 三组实验已跑通

见 [真实实验与下一步](PARATERA-EXPERIMENT-2026-09-04.md)。49 次调用、23238 tokens；
首轮接口失败保留，修订后的方法选择为原文 12/12、普通文本卡与结构卡各 11/12。
未观察到结构卡收益，反而用量更高。新增执行器可在无网络情况下重放真实结果。
下一阶段主要跑实验：先测条件含义、冲突作用范围与引用支持，再讨论更广泛结构和增量
更新。不改旧 gold；正式同 token 预算、新来源组与独立评价仍未完成。

## 前阶段交付：版本卡读取与方法选择实验准备

见 [阶段记录](METHOD-SELECTION-PHASE-2026-09-04.md)。版本卡的内置视图/接口状态提示、
非概率强度解释及历史版本被替代状态已补齐。R2 已开始建立实验资产和离线运行链路：
六个来源包、十二题、原文/普通文本卡/结构卡三组；真实模型效果尚未运行，正式同 token
预算及新来源包留出仍未完成。下一步绑定模型和预算，不直接扩大 schema 或图谱。

## 2026-09-04 修复后更新

本轮已按低到高修复完整卡展示、来源别名传递、检索诊断消费，并补充显式待核对模式；
全量回归另暴露并补修 Windows CardStore 原子替换的短暂拒绝。详见
[修复与收益评估](FIX-ROUND-2026-09-04.md)。旧检索集已转为已知标签回归：严格模式仍
误拒 3/16；review 恢复候选，但协议无答案也返回 8/8，不是拒答算法已验证有效。

R1 部分完成，剩余重点是版本卡治理状态/强度解释的消费契约。之后优先做 R2 一个
方法选择任务的同预算比较，再决定是否推进 R3 增量维护与更广泛知识挖掘；不先扩
通用图谱和 schema。下面各轮快照按其日期解读，不覆盖历史负结果。

> 当前阶段：核心算法证据
>
> 决策：先修复会让评测失真的核心契约，同时冻结离线评测资产；随后由失败样本
> 驱动算法加固。不是先堆复杂算法，也不是在错误实现上直接跑 benchmark。

## 1. 为什么这样排序

### 2026-09-04 研究范围校正

保留三条核心路径，但不把它们当成三项原创算法。下一阶段同时审视“知识被表示成什么、
消费时还剩什么”，不只打磨更新执行器。详细范围、公平基线和停止条件见
[知识表示与研究计划](REPRESENTATION-AND-RESEARCH-AGENDA.md)。

本轮锁定生产代码做两个独立诊断，不据测试标签调参数：

- [新检索集](../evals/retrieval-prospective/README.md)：代码冻结后新写样本；仍是内部合成
  诊断，不是独立外部盲测，也没有真实 neural embedding。
- [表示通道](../evals/representation-boundary/README.md)：人工响应走真实 parser、卡存储
  表示、renderer 和 embedding text，测完整限定语和来源/关系保留；不测模型理解。

新检索诊断已暴露 3/16 有答案误拒，且协议无答案误放仍有 3/8。后续协议应将“有明确
否定证据”与“没有足够证据”分开，不能仅以非空结果判定幻觉。结果与解释见
[本轮记录](EXPERIMENT-ROUND-2026-09-04.md)。

读过本轮结果后，样本转为诊断资产，不允许修复后把同集结果再称首次留出。后续优先级：
R1 接通最小生产消费边界 → R2 同预算表示/结晶效果 → R3 更新策略效果；知识挖掘先选择
用户任务再开发。没有凭据时不伪造模型输出，也不下载大型模型冒充已选定生产配置。

当前三条算法路径都已经有实现，但机制测试与真实效果之间仍有断层：

- 检索已覆盖生产 Entry 索引并冻结第一份 classical baseline，但还没有真实 embedding
  结果；不同合成集结果不同，不能宣称混合配置普遍胜过 keyword；
- 结晶已从头部截断升级为可追溯 passage selection，但还没有验证来源文本真的蕴含
  生成主张；
- 增量演化已闭合 span identity、来源登记、纠错权限和领域内原子 SPLIT，但模型/规则
  应选择哪个动作仍没有留出评测。

如果先调融合权重、增加提示词或实现自动策略，得到的提升可能只是测试设计造成的。
因此当前阶段的第一目标是让“被测系统”与“实际产品路径”成为同一个系统。

### 2026-09-01 第一轮历史快照

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

### 2026-09-01 第二轮收口

- `query-support-v3` 将过滤作用域前置、使候选深度与 `limit` 解耦，并补齐 Unicode
  entity、CJK bigram、多实体集合覆盖和明确拒答诊断；已知标签 post-hoc 为 Recall@5
  `1.0`、nDCG@5 `0.9698`、FPR `0.0`，但不属于盲测结论；
- 新 revision 把 ranker-visible query 收紧为 `query_id + text`，其余标签全部移入
  evaluator-only qrels；旧 revision 保留供历史报告重放；
- `passage-selection-v1` 已进入结晶生产路径并记录精确原文偏移、内容 hash 和选择
  manifest；四例合成消融为 4/4 evidence-hit、4/7 span recall，头部截断为 2/4、3/7；
- 本地 provenance registry 以 exact Entry + origin + full digest 绑定 admin attestation，
  支持 issue/supersede/revoke、严格失败关闭、提交时快照与撤销竞态门禁；hash chain
  仅表示完整性，不表示认证；
- schema 4 production adapter 可把 SPLIT 的 UPDATE + CREATE 和 receipt 在一次 evidence
  ledger replace 内提交；执行 manifest 防止操作替换，decision ledger 依靠 receipt-first
  恢复，仍不宣称跨文件原子；
- schema 4 event 字段已严格化，legacy upgrade 会物化历史默认值，ledger replace 后在
  支持的平台同步父目录。

因此下一阶段不再重复实现这些机制，而转向新封存检索集、表示消费边界、真实 embedding、
结晶 entailment/conflict 和增量 action-policy 留出实验；跨文件恢复继续作为平台风险。

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

### P0-C：production atomic SPLIT 已在领域账本内闭合

领域动作仍只有 CREATE、UPDATE、MERGE、RETIRE、CONTEST。SPLIT 是上层计划，固定展开
为 UPDATE + CREATE，并由 schema 4 batch 一次提交：

- executor 保留原子领域动作，不把 SPLIT 做成含义重叠的新动作；
- policy 的 SPLIT 计划展开为共享 `decision_id` 的 UPDATE + CREATE；领域锁内执行真实
  target-head CAS；
- NOOP 记录在 policy decision trace 中，不制造无意义的卡片版本；
- decision trace 使用 append-only hash chain、原子文件替换、幂等键和请求 hash；
- production adapter 在一次 evidence-ledger 原子替换内写入两个事件与 durable receipt；
- execution-manifest hash 和 receipt 全字段核对防止操作、证据或 target 被替换；
- decision ledger 在 receipt 前后故障时先查领域回执再推进状态。

尚未闭合的是两个账本之间的共同事务；当前是可恢复协议，不是跨文件原子提交。

### P0-D：可信 provenance registry 已实现，独立性奖励仍待版本化实验

`evidence-rule-v3` 用并查集合并三种有审计依据的边：同一 `source_key`、可信版本化
全文 SHA-256 evidence digest、以及收藏时计算并持久化的 `exact` /
`near_duplicate` relation。系统会在 rationale 单独报告 non-duplicate group 数；镜像
仍保留为来源记录，空/短/格式错误的 hash 不参与跨域折叠。

普通自声明 provenance（例如声称独立观察）绝不覆盖上述去重。registry 的 admin-only
入口已经定义 exact subject binding、issue/supersede/revoke、冲突处理和审计快照；缺失
或无效登记降为 `U`。为了不静默改写 `evidence-rule-v3` 的历史语义，当前仍不发放
corroboration bonus。下一步若启用 verified independence，必须发布新评分版本并做消融。

## 3. 正式实验前同轮关闭的可信性问题

以下问题不一定都阻塞第一行代码，但必须在对应路径的正式结果发布前关闭：

| 风险 | 当前表现 | 处理位置 |
|---|---|---|
| 原始模型输出被“洗白” | 已在对象构造前校验 raw JSON，错误类型、NaN、越界 confidence 与非法来源关系均失败关闭 | 保留 mutation test，并在真实 LLM 评测中保存 raw response/warning |
| official correction 权限过宽 | registry attestation 必须把 primary、topic/fact-key scope 与 exact corrected Entry 绑定在同一 active bundle | 保留撤销竞态、跨 attestation 组合和伪造 nested provenance 回归 |
| gold 泄漏 | G0-G3 与检索集均已物理拆分输入和 evaluator-only gold；检索 ranking 先于 qrels 加载 | 保留 loader/mutation test 与 manifest hash 门禁 |
| 测试数据隔离不完整 | 多个模块 import 时冻结全局路径，fixture 靠手工 patch | M2 加写入 guard；平台流逐步改为 runtime settings 构造注入 |
| 长文档静默截断 | `passage-selection-v1` 已替代头部截断并记录 exact offsets、source hash 与 manifest | M4 接入 entailment 标签和真实 LLM，验证选中不等于正确使用 |
| 多文件持久化不具事务性 | Entry、index、card、embedding 可能在崩溃或并发下不一致 | M3/M4 先加锁、原子替换和 generation manifest；是否迁移 SQLite 由故障证据决定 |
| SPLIT 伪原子 | schema 4 adapter 已在一个 evidence ledger replace 内提交 UPDATE + CREATE + receipt | 继续区分领域内原子与跨 decision/evidence 两文件可恢复，不夸大为跨文件事务 |
| 旧卡来源迁移丢失 | singular `source_id` 复制后会被 schema 忽略 | 发布前显式迁移到 `source_ids` 并用旧版 fixture round-trip |

## 4. 六个里程碑

| 顺序 | 里程碑 | 可并行关系 | 退出证据 |
|---|---|---|---|
| M1 | 证据身份、独立性与协议闭环 | **机制已完成** | span identity、v3 来源折叠、registry authority、旧 ledger 重放、schema 4 atomic SPLIT 与执行 manifest 均有生产集成测试 |
| M2 | 冻结无用户评测资产与当前基线 | **首轮完成** | G0-G3 输入/gold 隔离；检索 22/36 fixture、manifest hash、排名和负结果已入库 |
| M3 | 真正的 Entry 级语义检索 | **机制完成，泛化未证** | 三接口统一；post-hoc 拒答回归关闭已知失败；仍需新 sealed set 与真实 embedding |
| M4 | 原子主张与可验证证据结晶 | **选段完成，语义评测未完成** | raw JSON、quote/span 与 passage manifest 有门禁及小型消融；仍需 entailment/conflict 标签和真实模型评测 |
| M5 | Preview-only 增量转移策略 | **执行完成，选择未完成** | trace、manifest、atomic batch 与 recovery 有测试；仍需 action policy 和 abstention 留出评测 |
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

`2026-09-01.2` revision 已把 query 标签完全移到 evaluator-only qrels。对已经检查过的
q-035/q-036，`query-support-v3` post-hoc 为 Recall@5 `1.0`、nDCG@5 `0.9698`、FPR
`0.0`；它只用于防回归。下一次有效性比较必须新建 sealed query，不能继续调整旧 gold。

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
- SPLIT 通过 production evidence-ledger adapter 一次提交 UPDATE + CREATE 与 receipt；
  不得把跨 decision/evidence 两文件的恢复协议写成共同事务；
- G2 与 G3 共享 executor，只改变 policy 可以看到的信息和治理规则；
- 低证据或无法区分 UPDATE/CONTEST 时必须 abstain；
- 结晶卡片最终进入同一 evidence ledger，避免长期维护两个平行知识系统。

## 7. 下一轮开发安排

```text
Lane A — 检索泛化证据
  新 sealed no-answer / 实体歧义集 -> 真实 embedding -> 冻结比较

Lane B — 结晶语义证据
  entailment/conflict 标签 -> 真实 LLM -> passage ablation 与 raw output

Lane C — 增量动作策略
  simple-rule baseline -> preview-only policy -> G0-G3 action/abstention 留出评测

Lane D — 平台恢复
  Entry/card/index generation manifest -> 两账本 recovery audit -> 是否迁移 SQLite 的证据
```

四条 Lane 可以并行，但共享两个发布门槛：不得把已知标签 post-hoc 写成泛化效果；
不得把领域内原子替换写成跨文件事务。任何阈值调整只能用 dev，新 sealed test 与
evaluator-only gold 保持冻结。

## 8. 暂不进入主路线

- 新增大量网站适配器，除非它阻塞评测语料；
- 知识市场、交易或复杂协作；
- 没有真实瓶颈证据的大规模数据库重写；
- 为了展示而增加没有基线和失败样本的新算法名词；
- 在 G0-G3 前宣称自动增量演化优于 batch crystallization。

## 9. 当前阶段的完成定义

只有同时满足以下条件，才进入“自动演化策略”阶段：

1. 三条路径的评测调用真实生产服务；检索至少完成一轮真实 embedding；
2. span 身份、v3 来源折叠、registry authority 和 production atomic split adapter
   保持关闭，并明确领域内原子与跨文件恢复边界；
3. 固定数据、标签、原始输出和指标可由一个命令复现；
4. raw 输出校验、gold 隔离、数据路径隔离和关键持久化风险有回归门禁；
5. 新 sealed 无答案/实体歧义、长文 passage 和跨文件恢复有明确失败样本与门禁；
6. 至少一轮算法消融包含负结果和失败切片；
7. README 和演示只使用实验真正支持的结论。
