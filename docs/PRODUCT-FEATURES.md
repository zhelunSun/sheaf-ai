# Sheaf Product Feature Queue

> Updated: 2026-10-07. This document distinguishes candidate implementation from shipped features.
>
> PF-01 and PF-02 have local candidate implementations; integrated acceptance and real use are separate gates.
> PF-03 has an isolated developer workflow trial; author use and value remain unverified.
> PF-04 through PF-07 remain `planned / not-started`.
> Existing mechanisms are identified separately. Queue position is a priority, not a delivery promise.

## Product outcome

用户照常收藏资料，Sheaf 自动整理、判断处理质量与来源线索，帮助已有 Agent 在实际任务中
找回并使用这些资料。第一次使用、没有反馈历史时就应该有用。用户不必逐条解释收藏
动机、填写偏好问卷或反复教系统自己的知识。自然语言纠正是可选能力，不是前置步骤。

来源评分是启发式信号，不是真理分数。收藏不等于赞同，检索命中不等于支持结论，工具
调用不等于用户采纳。产品验证应观察资料是否帮助完成任务；调用次数、卡片数量和反馈
数量不能代替这个结果。

本队列优先连接已有能力与用户体验。当前技术能力及边界见
[产品设计入口](PRODUCT-DESIGN-INDEX.md)和[生产链路加固记录](HARDENING-2026-09-22.md)。

## Existing foundation

以下是代码核查确认的机制，不是本队列已经完成的功能。核查没有运行付费模型，也不
代表完成真实用户验收。

| 已有机制 | 代码锚点 | 仍需连接的产品结果 |
|---|---|---|
| URL/手工文本去重，正文缺失与图片主导提醒 | [pipeline.py:301](../sheaf_ai/pipeline.py#L301)、[quality.py:111](../sheaf_ai/quality.py#L111) | 用户收藏后能看见处理限制；不同 URL 的近重复另在存储时记录关系，不等同于自动拒收 |
| 自动主题、体裁、重要性与来源线索判断 | [classify.md:9](../prompts/classify.md#L9)、[source_scoring.py:290](../sheaf_ai/source_scoring.py#L290) | 自动判断帮助用户安排注意力，而非要求用户先配置品味 |
| 原文、Entry、摘要本地保存及带诊断的检索 | [storage.py:383](../sheaf_ai/storage.py#L383)、[mcp/search.py:91](../sheaf_ai/mcp/search.py#L91) | 用户和 Agent 能从建议返回可检查的来源 |
| MCP 原文读取与 Agent 操作指南 | [mcp/resources.py:108](../sheaf_ai/mcp/resources.py#L108)、[sheaf-guide.md:77](../sheaf_ai/skills/sheaf-guide.md#L77) | 已有 Agent 在任务中实际复用资料，并说明哪些判断来自资料 |
| 当前条目的纠错日志、独立的证据版本执行器 | [feedback.py:18](../sheaf_ai/feedback.py#L18)、[card_service.py:881](../sheaf_ai/card_service.py#L881) | 纠错尚非偏好学习；普通结晶卡不会自动进入版本账本 |

## Queue and first sprint

2026-09-28 依赖澄清：先保证收藏的保存/整理阶段结果真实，再经 PF-01 展示；当前条目
纠正后派生数据的失效与恢复是可靠性修补，不等于 PF-04 偏好应用。PF-03 可从现有接口
开始有界自用，但已知降级和未验证效果须分别记录。最小备份/恢复先保障资料安全，
PF-06 负责之后的产品化。10/3 实现进展按下表分别记录，不提升尚未开始的项目。

浏览器的安装修补、收藏任务状态恢复和最小页面整理见[浏览器工作包](BROWSER-EXTENSION-PLAN.md)。
它们属于 PF-01/02/03 的入口建设，不新增一套功能优先队列；侧栏与 New Tab 仍待需求触发。

| ID | User-visible outcome | Planning status | Implementation status | Queue position |
|---|---|---|---|---|
| PF-01 | 收藏后看见已有处理提醒与来源线索 | in-progress | candidate-implemented | First sprint; acceptance pending |
| PF-02 | 从收藏结果、最近列表或搜索结果查看来源并打开原文 | in-progress | candidate-implemented | First sprint; acceptance pending |
| PF-03 | 已有 Agent 在一个真实任务中复用可查来源 | in-progress | developer-trial-only | First sprint; recurring author use still pending |
| PF-04 | 一句可选纠正影响以后同类处理 | planned | not-started | After first sprint |
| PF-05 | 按需给出简短阅读建议，先验证有用性 | planned | not-started | After first sprint |
| PF-06 | 导出、隔离恢复一个最小本地知识库 | planned | not-started | After reuse is demonstrated |
| PF-07 | 第二个 Agent 客户端使用同一份知识而不重新收藏 | planned | not-started | After PF-06 |

首个 sprint 推荐 PF-01、PF-02、PF-03 三项，PF-03 从一开始就用现有接口试真实任务，
不等界面完善。若容量只够两项，保留 PF-03 与最阻塞使用的一项入口改进。结束时应
能在正常任务中收藏、找到资料并检查原文，记录仍缺少的入口提示。前三项不依赖
偏好模型、反馈积累或新的知识表示。

## PF-01 — Show collection quality and source signals

**Status:** in-progress / candidate-implemented. Local contract and isolated browser checks exist;
installed-extension use and user acceptance remain pending.

**用户价值：** 收藏仍是一键操作，用户能立刻知道正文是否完整、图片是否未被读取，及
来源判断的有限依据。无需为了得到这些结果额外填写信息。

**候选实现：** [pipeline.py](../sheaf_ai/pipeline.py) 区分保存与整理，持久化阶段状态；
[公共投影](../sheaf_ai/collection_projection.py)和 [HTTP](../sheaf_ai/api.py) 传递必要诊断；
[扩展展示](../extension/presentation.js) 区分完成、部分完成、未评估和保存结果未知。
CLI/MCP/批量接口也保留部分完成记录。详细字段语义见[采集结果契约](COLLECTION-RESULTS.md)。

**最小范围：** 将已有质量诊断和来源分项经 HTTP 传给扩展，显示一条必要提醒及可展开
的来源说明。区分“正文不足/图片未读”“模型整理失败”和“来源线索较弱”；缺失字段
显示未评估。上游须先分清保存与整理的阶段状态，明确旧 success 字段及旧客户端的
兼容语义，不把保存成功显示为整理全部完成；保持现有去重行为，较弱来源不新增自动拒收。

**验收与边界：** 用固定响应覆盖正常正文、图多文少、质量拒绝、模型整理失败、重复和诊断缺失；扩展
所示与流水线一致，旧服务无新字段时仍可收藏。不增加 OCR、事实核查、评分模型调用，
不把 A/B/C/D 显示为事实正确概率。正常收藏不弹出必答问题。

**依赖及实际影响：** 依赖现有流水线结果。实现前登记 HTTP/extension 契约变更；优先
可选的增量字段并保留旧字段。向扩展传必要诊断，不传本地绝对路径、模型配置或原始
错误堆栈；新增展示本身不需要调用模型。

## PF-02 — Inspect and reopen a collected source

**Status:** in-progress / candidate-implemented. All three entry paths share one detail view;
real installed-extension use remains pending.

**用户价值：** 收藏后能够查看保存的来源信息与摘要，也能从搜索结果继续阅读。
本项不提供完整正文阅读器，保存正文的核查由 PF-03 的已有 MCP Resource 路径承担。

**候选实现：** [popup.js](../extension/popup.js) 从收藏、最近和搜索进入同一详情页；
[api.py](../sheaf_ai/api.py) 的已有 Entry 详情接口提供保存版本信息。
来源按钮仅在用户点击后打开 HTTP(S) 网页；笔记与无效链接不提供网页动作。

**最小范围：** 让收藏成功结果、最近条目和搜索结果进入同一种轻量详情视图，显示
标题、保存的摘要、来源 URL 和 PF-01 的可用提醒，并提供“打开来源网页”。明确这会
访问网页当前版本，不代表当时保存的正文；需要核对保存版本时，通过已接入 Agent
读取对应 Entry 的 raw Resource。粘贴笔记显示为笔记，不把 `manual://` 当网页打开。
查看详情使用已有接口。

**验收与边界：** 三个入口均定位到正确 Entry；用户主动点击才打开对应 HTTP(S)
来源；失效/缺失 URL 和笔记有可理解的状态；标题和 URL 按不可信文本处理。收藏继续
保持一步完成。不建设阅读器、标注系统、浏览历史采集或完整工作台。

**依赖及实际影响：** 可与 PF-01 并行实现，共用其诊断展示。保持扩展既有本地服务
配置及权限范围，打开来源才产生相应网页访问；不在预览时静默重新抓取网页或调用
模型。若确需新权限或 API 字段，单独说明具体用途并登记契约变化。

## PF-03 — Reuse sources inside an existing agent task

**Status:** in-progress / developer-trial-only. A bounded stdio search/raw trial uses
manually loaded official excerpts in an isolated library. It is not author
acceptance, full-page collection or an embedding quality experiment.

**用户价值：** 用户在自己的 Agent 里完成方法比较、技术选择或资料解释时，已收藏
资料能被找回、检查并用于回答，无需另开一个 Sheaf 聊天产品。

**当前锚点：** [mcp/search.py:91](../sheaf_ai/mcp/search.py#L91) 提供检索与诊断；
[mcp/resources.py:108](../sheaf_ai/mcp/resources.py#L108) 可读保存的原文；
[sheaf-guide.md:77](../sheaf_ai/skills/sheaf-guide.md#L77) 已约定按需检索，
[sheaf-guide.md:126](../sheaf_ai/skills/sheaf-guide.md#L126) 已约定使用后的轻量提示。

**最小范围：** 选择一个已有客户端和一个用户已有任务，先走“集中检索一次 → 读取
相关原文 → 将关键结论链接回来源”的最短路径。必要时仅调整现有操作指南，让 Agent
区分文中事实、自己的推断与缺失材料；资料无帮助时可正常不用。暂不新增工具或
专用 context-pack schema。

**验收与边界：** 在隔离资料上检查一次有相关来源和一次无充分来源的任务：能返回
可定位的出处，保留关键条件，无充分依据时不借检索分数断言。随后在用户正常任务中
做一次小型试用，记录是否减少重新找资料或核查的步骤，以及剩余阻碍。验证来源网页
改变或无法访问时，仍可通过 raw Resource 核查当时保存的正文；若未保存则明确缺失，
不以在线页面冒充保存版本。工具调用、
输出引用、用户明确认为有用是三种不同观察，不自动等同；不强制用户每次打分。

**依赖及实际影响：** 使用现有 MCP/CLI/Resource，可先于 PF-01/PF-02 的界面改进试用，
独立于 PF-04 的纠正历史。若修改
操作指南须保留其现有写入授权边界。资料会进入用户所用 Agent 的上下文；不额外
上传到新服务、不后台收集完整任务对话。真实试用使用用户现有任务与模型额度，不
承诺零模型成本；离线固定响应验证不冒充真实 Agent 验收。

## PF-04 — Accept an optional natural-language correction

**Status:** planned / not-started.

**用户价值：** 用户只在需要时说“这类新闻少一点”或“我看重可复现方法”，以后相应
建议能有所调整；不要求先写个人画像。

**当前锚点：** [feedback.py:120](../sheaf_ai/feedback.py#L120) 只修改当前条目；
[source_registry.py:195](../sheaf_ai/source_registry.py#L195) 有域名级覆盖方法；
[pipeline.py:193](../sheaf_ai/pipeline.py#L193) 的分类输入未读取这些纠正历史。

**最小范围：** 先支持一种低风险、明确的纠正：对某个来源或内容类型减少主动阅读
建议。把用户直接表达的要求保存为简短、可查看、可撤销的本地设置，后续建议读取它。
当前条目的事实纠错继续走已有路径，两者不混为一谈。

**验收与边界：** 无任何设置时功能照常有用；一条明确要求只影响对应范围，撤销后
恢复；无法确定指代时不猜测写入。用户喜欢某来源不提高该来源事实的真值或治理权限。
不从一次忽略推断永久偏好，不微调模型，不建立复杂对齐流程。

**依赖及实际影响：** 在 PF-03 试用中确有重复纠正需求再实施，与 PF-05 共用简单
设置。若增加持久字段，先写兼容策略；不追溯覆盖旧资料。不保存完整对话，只保留
必要规则；现有 Agent 能解析时不增加专用模型调用。

## PF-05 — Offer reading suggestions on demand

**Status:** planned / not-started.

**用户价值：** 用户问“最近这些哪些值得我自己读”时，得到少量带理由的建议；系统
利用已有整理结果先减轻筛选负担。

**当前锚点：** [classify.md:50](../prompts/classify.md#L50) 已有重要性判断，
[storage.py:329](../sheaf_ai/storage.py#L329) 保存主题、体裁和摘要；
[source_scoring.py:259](../sheaf_ai/source_scoring.py#L259) 提供来源分项，
[query.py:95](../sheaf_ai/query.py#L95) 可查看主题趋势。

**最小范围：** 对一个有限的最近收藏集合，按用户本次问题和已有字段给出最多三条
建议与一句理由，能返回来源。可试用“值得精读”“看摘要即可”等自然语言，但先作为
待验证建议，不固定为不可更改的分类或全库状态。没有明确目标时使用通用排序并说清
依据；用户不必补齐偏好才能拿到结果。

**验收与边界：** 零反馈即可得到建议；相同输入能解释为何选出这些内容；图片未读
等限制不能被重要性分数掩盖。以小批真实收藏试用检查建议是否节约筛选，而非只验收
分类格式。此版本不自动拒删低分内容、不定时推送、不声称掌握用户长期品味。

**依赖及实际影响：** PF-01/PF-02 提供可查来源和处理限制；PF-04 可选，不是前置。
优先复用已有判断，由用户当前 Agent 按需组织，不重跑全库摘要；若新增模型步骤，
限定输入条数并记录实际成本。建议失败不改变已保存条目。

## PF-06 — Export and restore a minimal local library

**Status:** planned / not-started.

**用户价值：** 用户能带走资料，并通过实际恢复确认备份可用。

**当前锚点：** [storage.py:383](../sheaf_ai/storage.py#L383) 保存 Entry、原文与摘要；
[storage.py:619](../sheaf_ai/storage.py#L619) 可重建索引；
[card_service.py:51](../sheaf_ai/card_service.py#L51) 标明独立版本与来源登记存储。
本地文件存在不代表导入导出及恢复能力已经交付。

**最小范围：** 第一版只处理明确选择的数据目录中的 Entry、原文、摘要及其引用
关系，提供可检查的文件清单；恢复到新目录并重建可派生索引。已存在卡片或治理账本
而本版未覆盖时，明确说明这只是来源库导出，不能称为全库备份。先完成同版本恢复，
再决定其他格式和历史版本兼容范围。

**验收与边界：** 隔离恢复后的 Entry 数量、正文内容与来源对应一致，能搜索并打开
一个原文；缺失/损坏文件有报告；目标目录非空时不覆盖。导出排除密钥、客户端配置
及绝对工作路径。不承诺跨所有版本迁移，不接入云盘同步或市场发布。

**依赖及实际影响：** PF-03 已证明资料复用值得保留。新增 CLI/导出格式前登记契约
和兼容边界；文件清单使用明确 allowlist，恢复可撤回。数据复制本地完成，不需要
模型或联网；不会删除原始知识库。

## PF-07 — Hand off the library to a second agent client

**Status:** planned / not-started.

**用户价值：** 换 Agent 时仍能使用同一批资料，无需重做收藏和整理。

**当前锚点：** [setup.py](../sheaf_ai/setup.py) 已有多客户端配置适配；
[cli.py:121](../sheaf_ai/cli.py#L121) 提供目标客户端与数据目录参数；
[mcp/resources.py:82](../sheaf_ai/mcp/resources.py#L82) 提供相同内容的读取入口。

**最小范围：** 选定两个现有支持的客户端，让第二个客户端以用户明确选择的数据
目录读取同一来源库；需要搬移时只使用 PF-06 验证过的范围。提供短的设置与验证
步骤，不创建新的同步服务。

**验收与边界：** 两客户端能找到相同 Entry 并读取相同原文；第二客户端对一个
已有问题给出可查出处，不因迁移重新生成所有摘要。不同客户端的回答可能不同，
不以回答文字完全一致作验收。不迁移聊天记忆、隐式权限或用户未选择的私有文件。

**依赖及实际影响：** 依赖 PF-06 的可恢复性及 PF-03 的复用流程。配置改动提供
预览，保留其他客户端设置；本版不扩大网络监听范围。接入第二个云端 Agent 可能
让其模型提供商处理被读取的资料，遵循该客户端已有授权，不自动复制完整语料。

## Deferred work

知识市场、知识包交易和链上登记保持 **deferred**，不进入当前 sprint，也不据此
扩展核心 schema。重新讨论前，先有 PF-03 的复用证据、PF-06 的可恢复成果，以及
一个明确愿意接收/购买的资产场景；同时弄清用户有权分享哪些内容、收到的东西如何
使用。当前不开发 token、NFT、链上凭证、定价系统或平台分成。

通用品味模型、自动观点更新和新的检索/治理算法研究也不是前三项的依赖。已有技术
机制继续保留；发现阻碍上述用户流程的具体问题时，再按问题开有界实现任务。

## Implementation boundary

本次仅新增规格，不修改代码、用户数据、API 契约或已安装的 Agent 指南。未来实现前，
维护者按现有仓库规则在 `internal/code-audit-issues.md` 登记 CLI/MCP/HTTP/extension
契约变化；涉及持久数据时先说明兼容与恢复路径。沿用现有服务边界，不为本队列另建
大型协议或审批系统。

每项完成时应附实际变更、针对该用户路径的检查结果及仍未验证的部分，再更新对应
状态。固定响应测试证明接口行为，真实试用证明有限场景的可用性；两者均不自动证明
用户采纳、长期留存或商业需求。
