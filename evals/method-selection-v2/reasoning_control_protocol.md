# DeepSeek-V4-Flash 输出控制修订

状态：看到首轮输出截断后的接口修订，不是算法改进或独立重复实验。

Paratera `DeepSeek-V4-Flash` 的 128-token探针可返回 JSON；但默认正式抽取连续两次把
4096 completion tokens 全部用于隐藏 reasoning，正文为空、finish_reason=length。
第三个抽取在人工中止时已有发送 intent、无 result，可能已计费，禁止自动重发。

为避免继续浪费，冻结轮被中止且完整保留。随后使用同一合成探针、128 输出上限、无重试，
依次检查三个参数：

- `reasoning_effort="none"`：HTTP 200，17 输入、5 输出，reasoning 0，JSON 正常；
- `thinking={"type":"disabled"}`：同上；
- `enable_thinking=false`：HTTP 200，96 输入、18 输出，其中 reasoning 12，JSON 正常。

新修订选择首个实测有效且语义直接的 `reasoning_effort="none"`。它加入实际 HTTP body，
但不改变冻结的 source/task、抽取/回答 prompt、gold、表示或评分器。request option、修订源码
与本文 hash 一并写入新 manifest；底层请求 intent 的逻辑 prompt hash 不单独证明该传输参数，
因此验证时必须同时检查 manifest hash。这一组合是本修订的完整执行身份。

新目录重新运行最多 1 探针 + 6 抽取 + 36 回答，50 请求/150000 tokens、串行、无重试。
旧轮和三个参数探针的消耗另行报告，不能从新目录 usage 中消失。人民币价格仍 unknown。
若新模型返回的 model ID 或 usage 不一致、正文不满足 JSON/schema，仍按原规则失败。

本修订只解决模型输出控制，不解决证据作用域、条件分类或引用语义。那些属于冻结 v2
三组对照要观察的问题。结果好坏不能归因于“关闭思考提高算法”，也不能与旧 V3.2 一次
运行作公平代际比较。
