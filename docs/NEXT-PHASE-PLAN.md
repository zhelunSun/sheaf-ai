# Sheaf 下一阶段开发计划

> 当前阶段：核心算法证据
>
> 决策：先修复会让评测失真的核心契约，同时冻结离线评测资产；随后由失败样本
> 驱动算法加固。不是先堆复杂算法，也不是在错误实现上直接跑 benchmark。

## 1. 为什么这样排序

当前三条算法路径都已经有实现，但机制测试与真实效果之间仍有断层：

- 检索的固定分数评测验证了融合代码，却没有覆盖生产环境的 Entry 语义索引；
- 结晶验证了来源 ID 存在，却没有验证来源文本真的支持生成主张；
- 增量演化验证了状态执行器，却与评测协议在证据复用、claim split 和 noop 上不闭合。

如果先调融合权重、增加提示词或实现自动策略，得到的提升可能只是测试设计造成的。
因此当前阶段的第一目标是让“被测系统”与“实际产品路径”成为同一个系统。

## 2. 当前 P0 问题

### P0-A：检索评测与生产语义路径不一致

当前混合检索先搜索 KnowledgeCard 向量，再通过卡片 `source_ids` 映射回 Entry。
采集流程没有为所有 Entry 建立直接语义索引；未被结晶或单独处理过的来源，实际上
只能参加关键词检索。CLI、MCP 和 HTTP 的默认搜索路径也不一致。

完成标准：

- Entry 和 KnowledgeCard 使用明确分开的向量索引；
- 新增、重建、更新和删除 Entry 时，索引覆盖率和过期状态可观察；
- CLI、MCP、HTTP 共用同一个 retrieval service；
- embedding 不可用、索引为空和确实无结果具有不同诊断；
- 离线评测直接调用这条生产路径，不再注入最终语义分数冒充端到端结果。

### P0-B：证据复用粒度过粗

当前 ledger 把一个 `entry_id` 视为全局只能消费一次的证据。这能阻止重复事件，
但也导致一篇论文不能合法支持两个不同主张。

计划把两个概念分开：

- Entry 是否已经进入系统；
- 某段证据是否已经被用于某个主张。

证据使用身份至少绑定 `entry_id + claim identity + quote/span hash`。同一来源可以支持
多个不同主张；同一来源的同一段话不能因为重复提交而增加独立证据强度。精确请求
重试仍由 idempotency key 和 request hash 负责。

### P0-C：增量执行器与 G0-G3 协议不闭合

协议允许 `split` 和 `noop`，执行器目前只有 CREATE、UPDATE、MERGE、RETIRE、
CONTEST，并且一次事件只能产生一个版本。

拟冻结的边界是：

- executor 保留原子领域动作，不把 SPLIT 做成含义重叠的新动作；
- policy 的 SPLIT 计划展开为共享 `decision_id` 的 UPDATE + CREATE，并在同一加锁事务
  中提交；
- NOOP 记录在 policy decision trace 中，不制造无意义的卡片版本；
- schema 升级必须包含旧 ledger 迁移和重放测试。

如果原型证明原子批处理过于复杂，再单独评审多输出 event；不能让协议和实现各自
假定不同语义。

### P0-D：转载可能被误算为独立证据

当前证据强度主要按 domain `source_key` 去重。两个不同域名如果承载相同内容，仍会
被计为两个独立来源；仓库虽然保存 `content_hash`，强度计算并没有使用它。这与
现有 Cedar fixture 中“转载不能增加独立确认”的要求直接冲突。

完成标准：

- 独立性身份同时考虑规范来源、内容 hash、转载关系和 source kind；
- 重复内容仍保留为可追溯来源，但不增加独立来源计数和 corroboration bonus；
- 内容相似但确有独立验证的方法、数据或观察不能被简单 hash 去重；
- 相同内容跨域镜像、轻微改写转载和真正独立复现实验都有固定测试。

## 3. 正式实验前同轮关闭的可信性问题

以下问题不一定都阻塞第一行代码，但必须在对应路径的正式结果发布前关闭：

| 风险 | 当前表现 | 处理位置 |
|---|---|---|
| 原始模型输出被“洗白” | 非有限、越界或错误类型 confidence 会在对象构造时被钳到合法值 | M4 前先校验 raw JSON，拒绝非法类型、NaN 和越界值 |
| official correction 权限过宽 | `is_primary` 可能直接被当成有权纠正目标事实 | M1 分开 primary、official authority、authority scope 和 correction relation |
| gold 泄漏 | G0-G3 输入、gold、required/forbidden behavior 目前同文件 | M2 拆分 model input 与 evaluator-only gold，并保存最终发送 payload |
| 测试数据隔离不完整 | 多个模块 import 时冻结全局路径，fixture 靠手工 patch | M2 加写入 guard；平台流逐步改为 runtime settings 构造注入 |
| 长文档静默截断 | 来源先截 3000 字符，prompt 再截 2000 字符 | M4 用检索选段并记录 chunk/selection manifest |
| 多文件持久化不具事务性 | Entry、index、card、embedding 可能在崩溃或并发下不一致 | M3/M4 先加锁、原子替换和 generation manifest；是否迁移 SQLite 由故障证据决定 |
| 旧卡来源迁移丢失 | singular `source_id` 复制后会被 schema 忽略 | 发布前显式迁移到 `source_ids` 并用旧版 fixture round-trip |

## 4. 六个里程碑

| 顺序 | 里程碑 | 可并行关系 | 退出证据 |
|---|---|---|---|
| M1 | 证据身份、独立性与协议闭环 | 与 M2 并行 | 同一 Entry 可支持不同主张；转载不重复计强度；纠错权限明确；split/noop 有合法表示；旧 ledger 可重放 |
| M2 | 冻结无用户评测资产与当前基线 | 与 M1 并行 | 输入与 gold 隔离；fixture hash、标签、当前输出、模型设置和原始结果进入仓库且不可覆盖 |
| M3 | 真正的 Entry 级语义检索 | M2 提供尺子 | 三个接口排名一致；索引覆盖可观测；真实 embedding 消融可复现 |
| M4 | 原子主张与可验证证据结晶 | 可与 M3 后半并行 | 引文可在来源中定位；支持/冲突关系可标注；失败输出可复盘 |
| M5 | Preview-only 增量转移策略 | 依赖 M1、M3、M4 | 能检索旧 claim、提出动作、解释来源并在不确定时 abstain，不静默改写 |
| M6 | 正式消融与面试证据包 | 依赖前五项 | 检索、结晶、G0-G3 的原始输出、负结果、指标和一键复现报告齐全 |

## 5. M2 评测资产范围

### 检索集

首版建立 30–50 个 query，覆盖：

- 精确术语与标题；
- 同义改写和自然语言问题；
- 版本化事实与时间条件；
- 长文档中部或尾部信息；
- 中英文混合表达；
- 无相关结果和容易混淆的近邻来源。

每个 query 保存相关 Entry 集和相关性等级。基线包括 keyword、semantic、当前线性
融合和稳定的排名融合。报告 Recall@k、MRR、nDCG、延迟和失败切片，不只报告均值。

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
- G2 与 G3 共享 executor，只改变 policy 可以看到的信息和治理规则；
- 低证据或无法区分 UPDATE/CONTEST 时必须 abstain；
- 结晶卡片最终进入同一 evidence ledger，避免长期维护两个平行知识系统。

## 7. 并行开发安排

```text
Lane A — 领域契约
  M1 证据身份/独立性 -> split/noop decision trace -> schema migration/replay

Lane B — 评测资产
  M2 输入/gold 隔离 -> retrieval qrels -> crystallization bundles -> memory sequences -> frozen baseline

Lane C — 检索实现
  先写失败的生产路径测试 -> Entry index -> shared retrieval service -> ablation

Lane D — 结晶实现（M1/M2 接口冻结后启动）
  atomic claim evidence -> quote verification -> paragraph selection -> eval
```

Lane A 与 Lane B 立即并行。Lane C 可以先做接口和失败测试，但在 M2 基线冻结前不调
融合参数。Lane D 可以准备 schema 和 fixture，涉及 KnowledgeCard 持久格式的改动需
等待 M1 的证据身份决定。

## 8. 暂不进入主路线

- 新增大量网站适配器，除非它阻塞评测语料；
- 知识市场、交易或复杂协作；
- 没有真实瓶颈证据的大规模数据库重写；
- 为了展示而增加没有基线和失败样本的新算法名词；
- 在 G0-G3 前宣称自动增量演化优于 batch crystallization。

## 9. 当前阶段的完成定义

只有同时满足以下条件，才进入“自动演化策略”阶段：

1. 三条路径的评测调用真实生产服务；
2. P0 证据身份、来源独立性、split/noop 和 Entry 语义覆盖问题关闭；
3. 固定数据、标签、原始输出和指标可由一个命令复现；
4. raw 输出校验、gold 隔离、数据路径隔离和关键持久化风险有回归门禁；
5. 至少一轮算法消融包含负结果和失败切片；
6. README 和演示只使用实验真正支持的结论。
