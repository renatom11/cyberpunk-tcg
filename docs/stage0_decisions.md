# Stage 0 — engineering decisions made without asking

One line each: what was decided and why. Rules questions are not here; they go to
`docs/stage0_questions.md`.

- **Decision-coverage tool is `tools/decision_coverage.py`, not `tools/coverage.py`** — that
  name already means card-script test coverage (`data/COVERAGE.md`); renaming a shipped tool is
  churn for nothing.
- **Fuzz baseline re-taken on the committed tree** — the 046 ledger entry's random-agent digest
  (`a70eb43f…`, 33,954 actions) does not reproduce on `750c723` (`2e54e2c3…`, 33,880, stable
  across three runs); the Stage 0 entries use the reproducible figure and say so.
- **E1's four fixes share one commit and one regeneration** — three card scripts answered by name
  in the FAQ, each G0/G1 with disjoint golden keys; splitting them would cost three requalify
  cycles for no extra attribution (each key is localised to its own card in the entry).
- **Take Control's reduction is a helper (`ops.steal_reduction`) read by each effect steal** rather
  than a change to `push_steals` — `push_steals` is also called after the attack path has already
  subtracted it, and a second subtraction there would double-count.
- **Flathead's unblockability travels on `AttackContext`** (read once in `engine._attack`) — the
  FAQ fixes it at declaration; the field is in the attack key of `view.info_key`, so a search sees
  it as the public fact it is.
- **No editing of engine or script files while a verification job for the previous item is
  running** — E4's script edit landed while E3's fuzz was starting and could have contaminated
  E3's digest; the fuzz was re-run on the clean tree. Each item's golden cycle now completes
  before the next item's edit begins.
- **E5 applies the field-inclusive reading to every "friendly Legends" reader, not only the four
  FAQ-named cards** — Pepe Najarro ("Ready up to 2 spent MERC Legends") now also reaches a spent
  solo'd MERC Legend; the owner's Goro ruling states the principle (a Legend on the field is a
  face-up Legend), and one helper (`EffectCtx.all_legends`/`faceup_legends`) applied everywhere is
  what keeps the six sites from drifting apart again.
- **E6 converts every "first time … each turn" script, not only the three FAQ-named ones** —
  Johnny Silverhand, Rita Wheeler, Gorilla Arms, Rogue Amendiares and Viktor Vektor read the same
  phrase; the FAQ fixes its meaning (events, not the card's memory), and one helper applied to all
  eight is what stops the phrase meaning two things. Viktor's conversion turned the audit's open
  finding AUD-viktor-vektor-drop-your-illusions-1 green, which is the reading the audit had
  already reached from the text alone.
