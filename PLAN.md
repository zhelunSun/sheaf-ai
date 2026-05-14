# Universal Collector — 项目计划

> 产品孵化空间：从零散收藏到 Agent 可用知识资产的转化基础设施

## 当前阶段

```
Phase 0: 需求梳理          ✅ 已完成
Phase 0.5: MVP 验证        ✅ 4/4 文章端到端跑通
Phase 1: 增强能力           ← 正在这里
Phase 2: 生态联动
Phase 3: 产品化/Skill 化
```

## 路线图

### Phase 0.5 ✅ MVP 验证
- [x] 微信文章 requests 抓取测试（4/4 成功）
- [x] 四大主题 LLM 自动分类
- [x] 一句摘要 + 结构化要点生成
- [x] Markdown + JSON 本地存储
- [x] index.jsonl 全局索引
- [x] 关键词查询接口
- [x] 文档与 git 版本管理

### Phase 1 🔲 增强能力（待用户确认）
- [ ] 标题提取优化（当前微信文章标题为空）
- [ ] Embedding 向量检索
- [ ] 浏览器插件一键收录
- [ ] 定时报告（对接 WorkBuddy automation）
- [ ] URL 去重 + 内容相似度去重
- [ ] 重要性/时效性识别
- [ ] 人机纠偏反馈回路

### Phase 2 🔲 生态联动
- [ ] nova-reader 论文插件对接
- [ ] skill-factory 一键 Skill 转化
- [ ] 多收录源（邮件、RSS、Twitter）
- [ ] 知识图谱轻量关联

### Phase 3 🔲 产品化
- [ ] 独立 Skill 化发布
- [ ] ClawHub 分发
- [ ] 多用户支持（可选）

## 当前待决问题

1. 标题提取优化（微信文章 meta og:title 提取）
2. 是否要上 Embedding / ChromaDB？
3. 用户纠偏反馈机制设计
