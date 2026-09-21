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
