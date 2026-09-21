# Stage 0 progress log

Running log for the Stage 0 execution (unified design, Part 6, plus the engine changes decided
in the task's decision 2). Newest entry last. Companion files: `docs/stage0_decisions.md`
(engineering calls made without asking) and `docs/stage0_questions.md` (rules questions parked
for the owner). The plan itself is the "Stage 0" section of the session plan file and is
reproduced in `docs/stage0.md` with the final report.

## Step 1 — engine changes (decision 2)

| item | state | commit(s) |
|---|---|---|
| 1a verification tests (23 red, 5 documenting) | done | a8c3624 |
| E1 Sketchy Ripper / Misty / El Sombrerón | done, golden regenerated | 0c98b30, 2d72c6a |
| E2 Take Control reaches effect steals | done (no golden movement; ledger entry) | a393c3a, + suite commit |
| E3 Flathead unblockable fixed at declaration | done (no golden movement; ledger entry) | 68f8036, + suite commit |
| E4 Dying Night pays out after V died | done (no golden movement; ledger entry) | 374191a, 4c6b091 |
| E5 face-up Legends on the field (six readers incl. Goro and Pepe) | done, golden regenerated (2 keys) | see git log |
| E6 "first time each turn" by event count (eight scripts; Yorinobu counts itself) | done, golden regenerated (3 keys) | see git log |
| E7 Bootleg's sold card hidden from both seats | done (G0 IDENTICAL; ledger entry); bootstrap sample re-recorded | see git log |
| E8 trigger ordering over printed hooks and listeners (+ `wants` on every hook; 046's spurious prompts gone) | done with E9, golden regenerated (all 8 keys) | see git log |
| E9 activation / payment ordering | done with E8 | see git log |
| E10 reaction window always opens (re-window after a Block excepted; residual recorded) | done, golden regenerated (all 8 keys, no outcome moved) | fa1ab52, 024833c |
| E11 root dedup without hidden identities (`neural.seat_key`) | done | 41f510a |
| 1c pay-events (kill test 4) | 5,000 games of h20k: 109,748 payments, **14.18%** strategic (gate 2%) → WIRE | out/s0/pay_events_h20k.txt |
| E12 payment as a Pick (which Legends pay) | done, golden regenerated (all 8 keys); suite 72 → 68 (four findings, ledger); sample re-recorded | see git log |
| 1d requalify, bootstrap sample, site build, rulings rows 049–053 | rulings rows committed; after E12: requalified, sample re-recorded, full suite run (see below) | — |
| **No further rule changes after E12** | in force from this point | — |

Owner rulings received 2026-09-21: Kiroshi Optics equips friendly cards only (engine correct; row
to add); Goro *Losing His Way* counts a solo'd Legend as face-up and gains nothing with no Legends
left (ruling 042 closes; Goro joins E5).

## Steps 2–6

Step 3 files written, uncommitted, smoke-tested: `learn/coverage.py`, `learn/tokens.py`, `tools/decision_coverage.py`, `tools/timing.py`, `tools/cards_model.py` (numpy/torch twins agree to 1e-7), `tools/fit_cards.py` (rows → fit → export works on the sample), `tools/cards_agents.py`, `tools/dice_regret.py`. Corpora h20k/r8k harvesting in the background. Estimate at 2026-09-21 (start of Step 1 E3): 20–28 hours wall-clock remaining.

## Step 2 — timing table (n = 20 games per agent, seat 0 vs the frozen heuristic, one process per agent on a quiet core, inferred-list sampler)

| agent | game median s | IQR | min | max | decisions/game | median ms MAIN / PICK / TARGET / GIG_DIE |
|---|---:|---:|---:|---:|---:|---|
| heuristic | 0.16 | 0.06–0.20 | 0.05 | 0.40 | 76.7 | 0.88 / 0.19 / 0.65 / 0.00 |
| neural | 0.17 | 0.12–0.27 | 0.08 | 0.38 | 65.1 | 2.71 / 0.64 / 1.37 / 0.00 |
| ismcts:32 | 3.22 | 2.03–4.05 | 1.02 | 12.26 | 68.3 | 42.8 / 47.0 / 60.2 / 51.9 |
| ismcts:200 | 14.05 | 9.92–16.63 | 8.20 | 24.01 | 56.5 | 246 / 255 / 301 / 285 |
| plan:32 | 9.77 | 8.73–13.02 | 6.26 | 22.87 | 65.5 | the plan is searched once per turn at the GIG_DIE decision: 1,237 |
| plan-deep:32 | 18.79 | 12.41–27.17 | 9.00 | 61.61 | 63.7 | as above: 2,289 |

Files: `out/s0/timing_{a,b,c,d}.json` (commands: `tools/timing.py --games 20 --agents …`). Per
iteration `ismcts:32` costs 42.8 ms / 32 = **1.34 ms** on a MAIN decision (the design's n = 1
figure was 1.1 ms; the inferred-list prior is now drawn per world). Micro-costs and the 1-vs-4
worker harvest throughput are in `out/s0/timing_micro.json` (Step 2, second half).

**Micro-costs** (`out/s0/timing_micro.json`, 10,000 calls each, quiet machine): clone 4.5 µs,
determinize 71 µs, clone+apply 43 µs, features 48 µs, features+forward (114-head) 107 µs.
**Parallel efficiency**: 200 games of `ismcts:32` vs `ismcts:32` (both seats searching) took
972 s on 1 worker (0.206 games/s, 4.86 s a game) and 254 s on 4 workers (0.787 games/s):
efficiency **0.956**.

**Stage 1 projection** (30,000 games a generation, both seats `ismcts:32`, inferred list):
30,000 × 4.86 s ÷ 4 ÷ 0.956 ≈ **38,100 s ≈ 10.6 h a generation** on this machine, before the
card-aware model's forward is added at the leaves (`ismcts-cards`, measured separately in Step 3).
When more cores would change the plan: the efficiency is 0.96, so wall-clock scales almost
linearly — 8 cores ≈ 5.3 h, 16 ≈ 2.7 h; a generation a night needs 4 cores, a generation per
working day needs 8. The oracle labelling (2,000 × ~10 s of `cheat:ismcts:2000`) is a one-off
~1.5 h on 4 cores and is not on the per-generation path.

## Steps 3–4 — corpora, sidecar, families

* Corpora re-recorded under E12 with the coverage sidecar: `out/s0/h20k` (20,000 heuristic self-play games, 3,251,747 decisions, coverage block in the manifest) and `out/s0/r8k` (8,000 heuristic vs random).
* Kill test 1 pipeline launched (`scratchpad/kt1.sh`): 114-feature head refit on the new corpora → card-aware rows and fit → three panels (`neural@w114`, `neural-cards`, `neural-cards-ablated`).
* Suite families: **dice** — 12 proposals, 12 verified by `qualify` (agent report; files under `out/positions/dice/`). Race, card-semantics and play-around agents still running. A `mode: "defend"` position kind exists for the defender family; positions not yet authored.
* Kill test 1 pipeline, first stages: `harvest.py examples` on h20k+r8k → `fit_eval.py fit --hidden 16` → `out/s0/w114.json` (held-out Brier 0.1238 at epoch 124, 115 s). Card-aware rows: 218,364 (h20k, rate 0.04) + 50,914 (r8k) = 269,278 rows, 141,057 parameters; epoch 1 = 192 s, holdout Brier 0.135 after one epoch (`out/s0/kt1/fitcards.log`).
* Suite families merged (all verified by `qualify` on this build, none refused by `merge`): **dice 12, race 12, play-around 13, card-semantics 15** → `data/arena/delayed.json` **68 → 120** positions. A `defend` family (the new `mode: "defend"` kind) is being authored.

