# Explicit output-cap repair, 2026-09-05

Parent run `run-v1` stopped after four requests, before any answer generation.
Probe and x01 completed; x02 and x03 each returned `finish_reason=length` with
6000 completion tokens. All four have complete HTTP 200/model/usage receipts;
known usage is 22045 tokens, with no unresolved send. The stop rule worked.
This is an inspected output-envelope failure, not a reason to delete old evidence.

The sole experimental change is the extraction output allowance: 6000 to 12000.
The task-blind extraction prompt, input text, gold, 40-fact limit, selection code,
800-token answer context, answer prompt, answer cap, temperature, no-reasoning
setting, model, shuffled two-draw plan and metrics remain unchanged. No answer
scores exist at the time of this repair. All eight constructions are sampled
again under the same amended allowance, not patched into the old partial output.

The parent probe is explicitly reused by verified payload and receipt; it is not
a new model sample and incurs no second bill. The intended new request count is
8 constructions + 144 answers = 152, or 156 including the four parent attempts.
The same campaign retains its 170-attempt / 600000-token ceiling, so failed-parent
use reduces what remains available. Standalone method cost and total campaign
cost are distinct: the latter also includes interface diagnosis.

Recovery is a source-frozen, one-time admission tied to the exact two terminal
length receipts below. It only allows the new revision's first 12000-token
extract request; it resets the consecutive-length observation window at that
admitted request. Two new consecutive length results stop again. It never clears
unknown usage, missing files, HTTP failures or identity mismatch. No automatic
retry and no more than this one output-cap repair are permitted in this stage.

- x02: `38615da68c349bf4889b9be33b006b8465781437bc3b61345e86d305accf5d5d`
- x03: `6e3bef74178524a7de74a27fc42ad81be401b9f425a0d9653440b6c9eb2529f3`

The wrapper checks both original lock and amendment code hashes before every
cached/live call. Complete actual payloads still enter intents before dispatch.
The independent transport copy is used because the original frozen transport
correctly refuses caps above 6000 and must not be modified in place. All original
source files, fixtures, lock and receipts remain byte-identical.

The parent's strict cache reader may not understand newer 12000-token campaign
entries; use this revision's transport for campaign-wide accounting and this
wrapper's `replay` command for the completed result. Historical source identity
and the old four receipts remain independently verifiable.
