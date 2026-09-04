# 表示方法：小型论断—来源核对

日期：2026-09-04。问题：哪些知识表示思路可以直接借鉴，Sheaf 还需要证明什么？

这是四个代表性一手来源的决策材料，不是完整综述，也不是截至当前的最新研究排名或
原创性证明。未修改 Zotero、用户论文正文或用户资料。

## 文件与阅读深度

- [ledger.json](ledger.json)：来源身份、阅读范围、论断及支持关系。
- [references.bib](references.bib)：任务内引用键与已核对元数据，未冒用个人文献库的键。
- [audit.json](audit.json)：确定性结构检查；通过不代表论断在科学上成立。

C1 依据 PROV-DM 2.1.2 / 5.2.1 / 5.2.2 的实际正文段落核验：已有派生与修订关系。
`full_text` 表示所引用的是正文，不表示整份标准已通读或完成合规审查。
C2–C4 只达到摘要一致：分别是 RAPTOR 的层级摘要树、GraphRAG 的实体图与社区摘要、
HippoRAG 的图与 Personalized PageRank。没有引用效果数值，也没有据此决定采用哪种方法。

仍待解决：`[FULL-TEXT-REVIEW:C2]`、`[FULL-TEXT-REVIEW:C3]`、
`[FULL-TEXT-REVIEW:C4]`；Sheaf 的 H1 保留 `[EXPERIMENT-REQUIRED:H1]`。
H1 是我们提出的待测假设，不是上述论文证明的结论。这份材料不能直接升级为论文论证。

## 可复核命令

从仓库根目录执行，审计器来自本机的 literature-evidence-ledger skill：

```powershell
python C:/Users/zhelunStation/.codex/skills/literature-evidence-ledger/scripts/audit_ledger.py docs/research/representation-2026-09-04/ledger.json --bib docs/research/representation-2026-09-04/references.bib --output docs/research/representation-2026-09-04/audit.json
```

这是文献材料审核，不是 Sheaf 自身 evidence ledger 的实验。两种账本不能混为一谈。
