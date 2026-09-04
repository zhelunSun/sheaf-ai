# 方法选择：三种知识表示的实验入口

本目录已完成输入/标签隔离、请求准备、响应导入、评分和失败处理；**没有真实模型结果**。
[预检](preflight.json)只证明六个来源包、十二题、三个表示组可以进入实验，未调用 API。
设计限制和指标解释以冻结的 [protocol.md](protocol.md) 为准。

## 运行顺序

以下命令在仓库根目录运行。所有输出路径必须尚不存在；旧结果不得覆盖。
`--model` 必须换成实际固定的模型 ID，不要用模型昵称或每次变化的默认配置。

```powershell
python evals/method-selection/run_experiment.py prepare-extraction --model MODEL_ID --output extraction-plan.json
# 由模型执行器完成 extraction-plan.json 中的 requests，保存 extraction-responses.json。
python evals/method-selection/run_experiment.py prepare-answers --plan extraction-plan.json --responses extraction-responses.json --budget-characters 6000 --output answer-plan.json
# 用相同模型完成 answer-plan.json 中的 requests，保存 answer-responses.json。
python evals/method-selection/run_experiment.py score --plan answer-plan.json --responses answer-responses.json --output result.json
```

runner 默认无网络，也没有隐式付费调用。它负责严格的离线执行协议；实际模型执行器
尚未绑定供应商。不能因为存在请求文件，就称“完成了真实模型实验”。在接入执行器前，
固定模型、tokenizer、预算、重试策略及 usage 记录，并另立正式 token-budget 协议。
目前的字符上限只约束 context，不是整个模型请求或输出的 token 总量。

每个响应文件是一个 JSON 数组，每条记录必须包含以下全部键：

```json
{
  "request_id": "extract-b01",
  "request_hash": "从请求复制其完整哈希",
  "model": "与请求相同的实际模型 ID",
  "text": "模型原始响应文本，不在导入前改写或修补",
  "finish_reason": "stop",
  "usage": {"input_tokens": null, "output_tokens": null},
  "latency_ms": null
}
```

请求的 system/prompt/temperature/max_output_tokens 应原样执行。结束原因为 length、
error、content_filter 也必须提交记录，不能丢弃失败调用。缺失 usage 或耗时用 null，
不是零。`stop` 只表示正常结束，不表示内容正确。哈希绑定请求内容，不认证调用者。

计划保存原始构建响应、两种卡共有的字段、三个上下文和所有任务行。卡片抽取失败
不阻止原文组回答；单组超预算不裁剪句子或 JSON，也不从分母删除任务。
结果同时报告方法选择、证据状态、引用定位与必需来源覆盖；引用定位成功并不证明
理由或主张被原文支持。缺少完整响应或哈希/模型不一致时，评分整体拒绝执行。

## 冻结和测试

`lock.json` 在模型运行前生成，固定输入、gold、协议和被测代码，hash 只归一化 CRLF/LF。
准备两个阶段的请求都不读取/计算 gold 内容；收齐回答响应后评分才读 gold。
修改生产 renderer 或 runner 后，应建立新的实验 revision，不更新旧锁来冒充复现。

```powershell
python -m pytest tests/test_method_selection_experiment.py -q
```

单测中的响应是故意简单且经常答错的测试替身，只测试流程和指标，不保存为真实模型
质量报告。六个来源包全是内部开发集；本版没有被包装成 holdout 的题目。
