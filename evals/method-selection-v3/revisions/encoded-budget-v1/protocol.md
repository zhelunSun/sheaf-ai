# Encoded context-budget correction, 2026-09-05

This is an explicitly post-run mechanical correction, not the untouched original
pre-registration. The original result and output-cap repair remain preserved.
Inspection found that selection counted plain context text, whereas the actual
answer message embeds that text as a JSON string literal. Fact quotes require
additional escapes. Accepted raw contexts averaged 749.96 local tokens before
encoding and 758 after; fact contexts averaged about 780 before and 902 after,
with encoded maxima of 934. That violates the intended delivered-content cap.
This is local serialization overhead, not an unknown provider chat template.

Correct only the budget measurement at selection: count the exact
`json.dumps(context, ensure_ascii=False)` literal that is embedded in the answer
message, including its quotes. Keep the 800 limit, units, ranking, eligibility,
prompts, model, temperature, output caps, gold, extraction receipts and two actual
draw identities unchanged. Raw unit splitting still uses the original tokenizer,
so the repair does not silently change granularity. There is no threshold sweep.
The same formula now reduces query tokens in sorted order, with the existing
original-unit tie break, as a preventive determinism constraint on floating-point
accumulation. This is explicit, not a new learned score or tuned weight; no old
hash-seed failure is claimed without a reproducer. Cross-process hash-seed tests
must reproduce the complete contexts and payloads. Rebuild fact text from original
response JSON, not the key-sorted analysis export, so field order is preserved.

No new extraction or probe is permitted. Reuse their verified complete receipts.
Reuse an existing answer only if its same draw ID and complete effective payload
are identical; otherwise dispatch that answer once under the new source-frozen
manifest. This is traceable reuse of two existing independent samples where
inputs are unchanged, not relabeling one response as multiple draws. Preserve
every task/arm/draw denominator, including the five rejected extraction bundles.
Do not repair quotes, relax the 40-fact contract, or discard invalid facts here.

The single campaign ceiling remains 170 calls / 600000 tokens, including 96
parent calls / 206310 tokens. The correction may consume only what remains.
The output-cap transport, one-time recovery history, missing-evidence stops and
full effective-payload receipts are unchanged. No more paid corrections are
permitted in this stage after this mechanical budget correction.

The original 72-answer semantic packet remains independently reviewed. For this
corrected first-draw packet, an independent reviewer may reuse prior judgments
only for byte-identical anonymous answer/error records; changed records require
a new judgment. Preserve both review files and mapping lineage. Second draws
remain automatic-only. Small internally authored synthetic data and construction
failures prevent broad method, user-value or statistical-significance claims.
