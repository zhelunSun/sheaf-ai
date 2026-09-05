# Integrity review — 2026-09-05

Result: PASS for the bounded engineering checks below. This independent review
used the pinned v3 Python environment and tokenizer. No gold contents, semantic
score tables, or credentials were read; no API requests were made. This file is
the sole new artifact written by the reviewer.

All three source freezes and their parent links match; 14 frozen source entries
and the input identity were checked. Freeze identities:

- Base: `1a6d139d6ac43d2de517b45cac29dd7215a16073db42ac89f9b50c5b0187dc8a`
- Output cap: `4b352725e8ad497b4ec946e8559afe3af0a208464826b8e3a3bd09b58c54f449`
- Encoded budget: `18c374bdcd74ff3b01bb33e7464287e2bc471f9f00fac4791f437e0867c87add`

The campaign contains exactly 132 matched intent/result/admission triples, with
sequences 1–132. Checksums, complete payload hashes, manifest bindings, response
identities, provider usage, registrations, and recovery history pass.
Recomputed usage is 152,772 input + 100,606 output = **253,378 tokens**;
`uncertain=false`, `uncertain_requests=0`, `issues=[]`. Both ceilings remain
respected: 132/170 calls and 253,378/600,000 tokens.

| Run | Actual requests | Tokens |
|---|---:|---:|
| run-v1 | 4 | 22,045 |
| run-v2-output-cap | 92 | 184,265 |
| run-v3-encoded-budget | 36 | 47,068 |

The final revision's 36 new calls are exclusively answers: 18 `all_facts` and
18 `scoped_facts`. Each matches its frozen final payload and differs from its
same-ID parent payload. All 57 reused entries resolve to the original complete
payload, manifest, and receipt identity: 1 probe, 8 extractions, and 48 raw
answers with their original draw IDs. There are no new probe or extraction calls.

Rebuilding from original extraction `response.text` preserves fact-field order
and reproduces all 72 saved contexts and the complete final answer plan exactly.
Raw unit splitting uses the original counter. Actual JSON string literal counts
for valid contexts are:

| Arm | Valid contexts | Mean tokens | Maximum tokens |
|---|---:|---:|---:|
| raw_passages | 24 | 758.00 | 796 |
| all_facts | 9 | 779.44 | 798 |
| scoped_facts | 9 | 779.33 | 799 |

Every valid context is within the 800-token delivered-literal limit. All 144
task/arm/draw slots remain present: 84 effective answer responses and 60 retained
preparation-failure slots without calls. No semantic quality or method-effect
conclusion is made by this integrity review.
