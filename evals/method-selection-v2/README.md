# 方法选择 v2：条件语义与任务作用域

本目录接续 v1 的真实失败，但不覆盖 v1 数据或结果。它把问题从“文本还是 JSON”收窄为：

1. 能力、要求、明确否定、测量结果和未报告维度能否不被混为一类；
2. 回答一个方法时，其他方法的冲突能否不污染当前判断；
3. 这些处理是否改善正确性，或至少降低传给回答模型的上下文开销。

完整协议见 [protocol.md](protocol.md)，阶段结论见
[DeepSeek-V4-Flash 实验记录](../../docs/DEEPSEEK-V4-FLASH-EXPERIMENT-2026-09-05.md)。

## 当前真实结果

`DeepSeek-V4-Flash` 经 Paratera 实际完成 43 次请求、27028 个供应商报告 token。
`raw`、`all_facts`、`scoped_facts` 在十二个内部合成开发题上均为 12/12，且方法、状态、
引用定位和必需来源覆盖四项同时正确。作用域过滤没有显示质量增益；它把事实组的独立
使用总量从 13829 降为 12303 token，但仍高于原文的 5008。

这是看过 v1 错误类型后设计的前瞻开发诊断，不是独立留出、用户效果或论文结论。
三组全对首先表示题目对当前模型过易，不能证明结构表示优于原文。

## 运行入口

以下命令均在仓库根目录执行。默认不调用网络：

```powershell
python evals/method-selection-v2/run_live_no_reasoning.py `
  --model DeepSeek-V4-Flash `
  --run-dir NEW_RUN_DIRECTORY
```

真实调用必须显式增加 `--execute`。`--credential-profile` 只选择本机 Paratera 凭据记录；
真正的推理模型由 `--model` 决定。不要把密钥写入参数、仓库或运行目录。

```powershell
python evals/method-selection-v2/run_live_no_reasoning.py `
  --model DeepSeek-V4-Flash `
  --run-dir NEW_RUN_DIRECTORY `
  --execute
```

本模型在 Paratera 默认设置下曾把两次 4096 completion tokens 全部用于隐藏推理并返回
空正文，因此完整轮使用 manifest 绑定的 `reasoning_effort="none"`。失败轮保留在
`runs/paratera-deepseek-v4-flash-20260905-v1/`；成功轮保留在
`runs/paratera-deepseek-v4-flash-no-reasoning-20260905-v1/`。不要向有未决 intent 的
失败目录续跑，否则可能重复计费。

## 可重放边界

- `lock.json` 固定 inputs、gold、协议以及 v1/v2 离线 runner；成功 manifest 另绑定两个
  live runner、输出控制协议和请求选项。
- 每次请求先保存 intent，再保存包含原始 HTTP body、模型 ID、usage 和 hash 的 receipt。
  有 intent 无 result 时状态不确定，执行器拒绝自动重发。
- 输出控制由 manifest、注入代码和 0 reasoning usage 共同核对；当前没有单独保存完整的
  on-wire payload，下一 revision 应增加脱敏后的 effective-payload hash。
- 回答全部收齐且身份核对通过以后，评分器才读取 `gold.json`；抽取阶段只读方法 ID 和来源。
- `normalization-audit.json` 只记录完整 JSON 代码围栏的移除；内部答案和引用不改写。
- `preflight.json` 是调用前的历史快照，保留 `No actual model run` 不代表当前仍未执行。

离线 runner 和测试替身的入口：

```powershell
python -m pytest tests/test_method_selection_v2.py tests/test_method_selection_v2_live.py -q
```

真实结果可在禁止网络的 mock transport 下重放；这验证持久化与评分一致，不构成第二次
模型抽样。供应商价格未核实，金额必须保持 null；原生 token 也不等于人民币账单。

## 下一步

当前集合已经转为回归资产。下一版不能继续修改这十二题来制造差异，应换成独立编写的
较长来源和多轮复用任务，给原文 passage 与事实表示相同输入预算，并把构建成本按实际
复用次数摊销。还需新增一个能表达“争议未裁决”的类型或独立状态，但应先用新样本确认
它会改变任务结果，不能只因为 schema 看起来不完整就继续加字段。
