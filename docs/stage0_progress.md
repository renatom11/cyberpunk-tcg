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
| E6 "first time each turn" by event count | pending | — |
| E7 Bootleg's sold card hidden | pending | — |
| E8 trigger ordering over printed hooks and listeners | pending | — |
| E9 activation / payment ordering | pending | — |
| E10 reaction window always opens | pending | — |
| E11 root dedup without hidden identities | pending | — |
| 1c pay-events (kill test 4) | after the first corpus | — |
| 1d requalify, bootstrap sample, site build, rulings rows | pending | — |

Owner rulings received 2026-09-21: Kiroshi Optics equips friendly cards only (engine correct; row
to add); Goro *Losing His Way* counts a solo'd Legend as face-up and gains nothing with no Legends
left (ruling 042 closes; Goro joins E5).

## Steps 2–6

Not started. Estimate at 2026-09-21 (start of Step 1 E3): 20–28 hours wall-clock remaining.
