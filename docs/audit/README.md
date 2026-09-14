# The audit's working papers

Every card script in `src/cptcg/cards/sets/wnc.py` was read against the printed text in
`data/cards/wnc.json`, in both directions — text→script for a missing clause, script→text for one
the card never asked for. These are the reports that pass produced. They are kept here because they
were written into a gitignored directory on an ephemeral machine, and the argument behind a finding
is worth more than the one-line reason string that survives in a test.

**Read these as working papers, not as settled truth.** They are agent-written, they disagree with
each other in places, and at least one of them is wrong on purpose — `AUD-kiroshi-optics-1` was
filed, verified, and then *killed*, and the kill is in the file next to the claim. What is settled
lives in the repository itself: the `xfail(strict=True)` tests under `tests/cards/audit/`, the
fixes in `src/`, the rulings in [`../rulings.md`](../rulings.md), and the ledger in
`tests/golden/REGEN.md`. Where a working paper and the code disagree, the code is the answer and
the paper is the reason someone went looking.

## The rule the whole pass was run under

A finding has **two legs** and is not a finding without both:

* **Leg A — observed.** A test in `tests/cards/` style that the auditor ran and watched fail, with
  the verbatim pytest output. It asserts printed-text outcomes only — zones, Gig faces, hand size,
  power, keywords — never a script internal. A test asserting a flag bit is unreviewable and was
  rejected on sight.
* **Leg B — expected.** The printed `text` copied byte-exact from `data/cards/wnc.json`, split into
  numbered clauses, each mapped to the `wnc.py` lines implementing it or marked unimplemented, plus
  a statement of which of the 42 rulings apply.

Leg A alone proves what the engine *does*, not what it *should*. A test written by an agent that
misread the card is a wrong expectation frozen into the repository — worse than the bug. The clause
maps in these files are Leg B, and they are the part that cannot be reconstructed from the test.

Anything with only one leg went to [`../audit-unproven.md`](../audit-unproven.md) instead.

## The files

| | |
|---|---|
| `a01`–`a15` | one batch per mechanic section of `wnc.py`, contiguous and disjoint, so no two auditors read the same region and an out-of-range finding is instantly detectable |
| `b01`–`b05` | cross-cutting passes by hook family — `on_event` trigger words against declared event kinds, the modifier family, optionality and sides, `on_play`, replacement and permission effects — which is where a section pass is blind, because the two cards that disagree sit in different sections |
| `verification/` | one file per finding from the first verification round: the card as the blind reader saw it, the finding and its failing test, then both skeptics' reports |

## The verification records

Each file in `verification/` is a finding put through two asymmetric skeptics:

* **Skeptic 1 is never shown the finding.** It is given the card and the script and re-derives the
  card clause by clause. Agreement counts only if it lands on the *same clause with the same
  direction of error*. This is the anti-anchoring leg and the reason the pass is worth running.
* **Skeptic 2 is told the finding is presumed wrong** and must kill it: a ruling covers it, the
  engine handles it somewhere the filer did not look, the test's board is unreachable, the test
  asserts internals, or the expectation misreads a word.

Twenty-three of twenty-four survived, the blind reader independently found the error on 21 of 24,
and the three it missed are exactly the two prohibition cases — where the bug lives in a card the
reader was never shown — plus the one genuine false positive. [`../verification.md`](../verification.md)
is the summary; these are the transcripts it summarises.
