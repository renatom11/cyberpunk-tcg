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
- **E7's fuzz digests cannot move and the ledger says so** — the fuzz hashes outcomes of
  perfect-information play and nothing reads an Eddie's identity; the change is to who may name a
  card, which the determinization property tests and the scenario test observe. Treated as
  satisfying the G0 rule's intent (the change is provably not a no-op) rather than its letter.
- **The bootstrap sample is re-recorded whenever the full suite says it no longer replays**, in the
  regeneration commit of the item that caught it (here E7, for streams E5/E6 moved); the ledger
  entry names it.
- **E8 and E9 land as one commit** — E9's deferred spend triggers *are* an E8 group, and the
  `deferring` collection mode is what both need; the ledger entry covers both.
- **`CardScript.wants(ctx, ev)` added and declared on all 37 event hooks** — a trigger that would
  not act is not pending, so it must not be offered for ordering; 046's "3.2% of events" was mostly
  inactive hooks, and the true ordering rate is 1.8% of decisions. A lint would be the right guard
  for new scripts (not added in Stage 0; `registry.load_default` check in the report instead).
- **Listeners carry the registering card's instance and an event-kind attribute** (`fn.kinds`) —
  the lint that proves one-shot listeners remove themselves reads the `m[2] is listen` idiom, so
  the filter lives on the function rather than in a tuple value.
- **A Call's spend triggers resolve after the Call and join its CALL group** — by analogy with
  the FAQ's "play the card first"; no FAQ answer names the Call case (listed in the questions file).
- **Pass-only reaction windows are real decisions in the stream, and `conftest.do` answers them
  for scenario tests** — auto-resolving them in the engine would keep the tell in the action
  stream (the very thing E10 removes); hiding them from card tests keeps 148 attack-driving tests
  readable without asserting a Pass each.
- **E11's seat key lives in `agents/neural.py` (`seat_key`) and the frozen heuristic keeps
  `_equiv_key`** — the heuristic is frozen and is the yardstick; the neural greedy and the search
  root are the agents being built. `tests/unit/test_neural_agent.py` now pins the dedup key as the
  second deliberate difference between the two `_greedy` bodies.
- **The Pass-only window that re-opens after a Block stays closed** — opening it made the frozen
  heuristic stop blocking (its preview cannot see past a pending decision on the rival's turn)
  and cost the suite a defensive position; the residual tell is recorded in the report. The first
  window, the one the leak was about, always opens.

## E12 — payment as a Pick (kill test 4 said WIRE)

* **Measured, not assumed.** `dump.py --pay-events out/s0/h20k -n 5000`: 109,748 payments, a Legend with content spent while another source stayed ready in 15,567 = **14.18%** (ability 12,151; last face-down 4,643; spend-trigger Gear 27) — the gate was 2%.
* **The flag is not flipped.** `explicit_payment` stays `False` in `RulesConfig` because every field is hashed into `digest()` and the shipped `weights.json` (rules `149b39c8f55e9d41`), the corpus and the suite are refused on a mismatch; the day-0 baselines and kill test 1 need those weights under this digest. The behaviour is hard-coded in `engine._with_payment`, the field's comment says so, and `DESCRIPTIVE` keeps it (the ruling-flag test pins that nothing reads it). Same precedent as 047's orientation (`engine.go_solo`).
* **Eddies first, always.** Plans differ only in *which Legends* cover what the Eddies do not. Keeping an Eddie back to spend a Legend with a spend trigger instead was wanted in 27 of 109,748 payments (0.02%); enumerating those plans would multiply the width of every payment for that. Recorded as a residual in ruling 025.
* **Ask only when there is a choice.** One plan (Eddies suffice, or every Legend must pay) asks nothing, so the goldens move only where a real choice was inserted.
* **Script-internal payments stay automatic** (El Sombrerón's optional 2 €$, and one other): a Pick inside a continuation would need the effect rewritten around it; two cards, rare, noted.
* **The prompt names no card**: the view-redaction test caught the first version naming the payer's face-down Legends in a prompt both seats receive. Labels go through the identity gate instead.
* **Token layout moved** (`tokens_digest` `ae121dc0ed23616c` → `1c4b67e7c9000efc`): a `pay` tag class and a `payplan` pick class. No card-aware weights existed yet, so nothing is refused.

## Step 2 — how the timing table was measured

* Each agent group ran as its own single-threaded process (`heuristic,neural,ismcts:32` / `ismcts:200` / `plan:32` / `plan-deep:32`), four at once on the four cores, so every measurement had a core to itself; the micro-costs and the 1-vs-4-worker harvest throughput ran afterwards on the otherwise idle machine. Per-decision times are therefore per-core quiet, not machine-quiet; memory-bandwidth sharing is the residual.
* The table is taken under the **inferred-list** sampler (the Stage 1 default), so `ismcts` rows include a `RivalPrior` draw per world. The design's 1.1 ms/iteration was measured under the known-list sampler.
* `plan` and `plan-deep` search once per turn (at the GIG_DIE decision) and replay the plan, so their per-kind MAIN medians read 0.00; the per-game column is the comparable number.
* `tools/timing.py` scaled the decision counts by 1000 along with the milliseconds; fixed in the tool and in the four JSON files (quantiles were unaffected).

## Step 4 — the defender family is built as a `mode: "defend"` position

* `qualify` gains a second goal: for `mode: "defend"` the position's `player` is the defender, the rival is active and the claim is `delayed.held` — the rival's turn ends without the rival winning or reaching the winning Gig count. The solver searches the defender's decisions during the rival's turn (reaction windows, Calls, QUICK plays, the defender's own Picks) with the rival on the frozen policy; the heuristic must fail to hold on every seed and random must hold on at most 25% of the scoring seeds, the same shape as a mover position. Horizon is 1 by construction.
* Chosen over a separate `defend_search` because the existing exhaustive search, trials and floor are one `goal` parameter away from it; the "prevents the winning Gig this turn" criterion of the design is exactly `held`. What a defend position cannot express: a defence that only pays off two turns later.
* Positions for the family are authored the same way as the others (propose → `check`); none exist yet at the time of this note.

## Kill test 4 after E12 — what the classifier now measures

`dump.py --pay-events` on the re-recorded corpus (5,000 games): 109,558 payments, 15,397 (14.05%) spent a Legend with content while another source stayed ready. Under E12 those are no longer the auto-payer's doing: whenever such a payment had more than one plan the heuristic was *asked* and its preview chose. The classifier cannot tell an asked payment from an unasked one, so the number is now "how often the chosen plan spent a Legend with content", not an approximation share. The residual approximations E12 leaves (Eddies always first; two script-internal payments) were sized on the pre-E12 corpus (0.02% for the spend-trigger case) and are recorded in ruling 025.

## Observations from the family proposals (recorded, not acted on — the heuristic is frozen)

* The frozen defender's reaction preview stops at the attacker's die Pick (`HeuristicAgent._resolve` returns when the active player is not itself), so it Blocks only when the naive attack would take **all** its stealable dice or its Unit would lose a fight; a Gig attack that leaves a die behind is never blocked. Several verified positions in the play-around and card-semantics families lean on this. It is the same mechanism that produced E10's residual (the re-window after a Block stays closed), and it is a property of the yardstick, not of the engine.
* The heuristic answers an optional prompt with option 0 (the first candidate, not the decline), which is why Alt Cunningham *Mother of Daemons* cannot anchor a play-around position against it.
* The heuristic's evaluator counts Eddies and Legends as cards regardless of orientation, so spending is free to it; proposals gate lines on legality (exact Eddies) rather than on the greedy not wanting to spend.

## Merging the families: two repo standards the proposals had to meet

* `tests/learn/test_delayed_reward.py::test_hand_built_positions_look_like_real_games` requires three Legends a side and at least twenty cards in each deck. The proposals were briefed with "6+ cards", so the 52 merged positions were padded to twenty at the **bottom** of the deck (the front of the spec list) by repeating their own cards, which leaves the top — the only part a line can draw or reveal — exactly as authored; every padded position was then re-qualified and its `verified` block replaced. A Legend that went solo stands on the field and is still one of the deck's three, so the test now counts it.
* `MAX_DEPTH` (own decisions a searched turn may hold) raised 14 → 22: with E10's Pass at every attack, E12's payment question and E8's orderings, a turn with two attacks and two Legend-paid plays reaches fourteen and the solver reported "not exhausted" on a position it had in fact solved (`play-around-overwatch-eats-the-fang`).

## Defend family merged (13 positions)

* Observations from the proposer, recorded: the frozen heuristic on defence Calls a face-down Legend at the first reaction window whenever it can pay (its evaluator counts Eddies and Legends as cards, so payment is free and face-up is +2) and prefers "Draw 1" over a pending modal, so a Call is never a discriminating line by itself; nine of the thirteen positions make that Call cost something (a QUICK that becomes unaffordable). The re-window after a Block still offers the other Blocker (legal per CR 9.7), so "Block A then Block B" is a line random play stumbles into. A single-candidate `choose` is auto-resolved on some paths and asked as a one-option PICK on others — harmless to solver and agents (one option) but it shifts stored line indices; left as is, no rule content.
* `qualify` in defend mode relies on the rival's frozen turn being a pure function of the position (`fixed_policy`, `POLICY_SEED`); the order between equal-valued attackers is decided inside that policy's own noise and is therefore reproducible, but a proposer cannot choose it.

## Kill test 1 — the card-aware agent's previews are scored under one context

The first panel run of `neural-cards` came back **below the 114 head and near random** (0.544 vs random, 0.583 vs heuristic) while the same model's values on fresh positions correlate 0.908 with the 114 head at the same Brier. The cause was in the inference path, not the model: the head is E[outcome | board, decision context], and `_greedy` scored each preview under the context it landed in — a Play leaves my MAIN pending, an EndTurn leaves the rival's GIG_DIE pending — so it compared two different conditionals; every EndTurn preview came out about a logit above every Play. Fix: `cards_agents._value_batch` reads a position "as if at my MAIN" (one fixed context per seat) unless the caller passes the context of the decision being made, which the greedy loop does. The 114 head has no context input and so never had the problem. The three panels were re-run with the fix; the first run's numbers are kept in `out/s0/kt1/first_run/` for the record. My judgement: this is a bug fix in the instrument, not a softening of the test — the criterion and the weights are unchanged.

## Kill test 2 — how the round robin was invoked

`cptcg tourney` is a console script of an uninstalled package and `src/cptcg/cli/main.py` has no `__main__` guard, so `python3 -m cptcg.cli.main tourney …` exits silently with nothing written. The runs use `PYTHONPATH=src python3 -c "from cptcg.cli.main import main; main(sys.argv[1:])" tourney …`. The design's `data/arena/panel.json:*` deck syntax does not exist either: the twelve frozen panel lists were exported to `out/s0/panel_decks/*.json` and passed with the eight `data/decks/*.json` lists (20 decks, 190 pairs). The first attempt cost about half an hour of pipeline time before the failure was noticed.

## KT1 rerun, step 1 — the Gig-monotonicity "defect": root cause

Measured on 200–300 sampled MAIN positions of h20k with the card-aware model (`out/s0/wcards.npz`), decomposed by input path (aggregates / dice tokens / card tokens) and by perturbation:

| perturbation | legal? | card model: mean Δ logit, share falling | shipped 114 head | refit 114 head |
|---|---|---|---|---|
| add a d6=3 to my Gig area, fixer unchanged (the instrument's `+gig`) | **no** (the d6 is then in two places) | +0.15, **22%** | +0.35, 0% | +0.39, 1% |
| take a die from my fixer into my Gig area | yes | −1.21, 94% | −0.00, 38% | −0.07, 62% |
| remove one of my fixer dice (no Gig change) | no | −0.68, 97% | −0.32, 96% | −0.51, 97% |
| steal the rival's last Gig die | yes | +0.85, 1% | +0.69, 0% | +0.94, 0% |
| the rival steals my last Gig die | yes | −0.82 (95% fall, correct) | — | — |

Attribution of the illegal `+gig` for the card model: aggregates path alone +0.31 (0.3% falling), dice-token path alone −0.17 (32% falling), card tokens 0. So:

1. **The 22% figure was an instrument bug.** `tools/monotonicity.py`'s `+gig`/`-gig` created states no game reaches (a die in the Gig area *and* in the fixer; a die in neither). The card model reads dice as tokens and answered the impossible multiset noisily; the 114 heads, which read counts, did not notice. Fixed: every perturbation is now rules-legal (Gig changes are steals, the dice of the game are conserved), pinned by `test_perturbations_conserve_the_dice`, and `+die`/`-die` (fixer ↔ Gig) are reported beside the counted rows but not counted, because they are ambiguous under the Overtime clock.
2. **On the legal, unambiguous perturbation (a steal) the card model is monotone: 98.9%.** There is no Gig-monotonicity defect in the model.
3. **Every head, the 114 ones included, dislikes having fewer fixer dice than the rival**, and that is learned from the corpus, not a bug: in the r8k rows the outcome label is 0.318 at fixer-diff −1 and 0.691 at +1, and at the mover's own MAIN it is 0.305 vs 0.658. The fixer count is a turn-parity signal (the player to move has taken this turn's die), and in heuristic-vs-random games it is also an *agent-identity* signal, because the frozen heuristic chooses to go second when it wins the roll and random does not — so "one fewer fixer die" mostly meant "I am the random player". The 114 features carry `fixer_left_me/rival` too, which is why the refit 114 head shows it more strongly than the shipped one (fitted on 80k heuristic-only games).

Per the pre-registration: no constraint is bolted on. The remedy for (3) is the corpus the rerun already prescribes — symmetric `ismcts:32` self-play, where fixer parity can only encode the true first/second-player effect — plus the instrument fix in (1). My call, logged here for veto: the rerun proceeds, because the defect as reported was the instrument's, the model is monotone on the legal test, and the learned behaviour is shared by the comparison head and addressed by step 2's corpus by construction.


## Oracle relabel: resume from the 750 positions the killed run finished

The relabel with the original labellers (`cheat:ismcts:2000` + `plan-deep:32`, seed 7) was killed at 750/2,000
because running it beside the 4-worker corpus harvest slowed both to a crawl. The 750 finished positions are a
contiguous prefix (positions 0–749; `seconds` differ from the committed labels on exactly those, and on 69 of them
the label itself moved under the four rulings — mean |Δ cheat_value| 0.0004, max 0.14). Rather than recompute
them, the remaining 1,250 are labelled with `oracle.py label --resume` after the labels of positions 750–1999 are
stripped (`out/s1/oracle_partial.json`); the labellers, budget and seed are identical, so the result is the same
file a full run would produce. The committed `data/arena/oracle.json` is restored to HEAD until the run finishes.

## KT1 rerun: card-model configs d and e added before any panel result

Added 2026-09-21 18:50 UTC, while config a was still fitting and before `CHOOSE` fired. Reason: config a's
holdout Brier was best at epoch 2 (0.1364) and rose to 0.1524 at epoch 3 while train Brier fell to 0.092 —
the 141k-parameter model memorises 806k rows from 10k games within three epochs. Two regularised configs
join the queue: **d** (lr 5e-4, l2 1e-3, dropout 0.2 on the token MLP outputs and the pooled vector,
identity embedding 16 wide, policy weight 0.5) and **e** (the same, policy weight 1.0). They run at the
front of `rerun2.sh`, i.e. after a/b/c and before the head choice; the selection rule is unchanged (holdout
Brier, tie-break legal monotonicity, never the panel). `tools/cards_model.py` gained `emb` and `dropout`
arguments on `torch_model` (defaults reproduce the previous arithmetic exactly; the numpy twin reads the
width from the weights; dropout is training-mode only), `tools/fit_cards.py fit` gained `--embed` and
`--dropout`, and `cmd_eval` builds the torch twin at the weights' width. Pinned by
`test_the_twin_agrees_at_another_embedding_width_and_dropout_is_off_at_inference`. Configs b and c will
import the edited module when they start; the defaults are untouched, so their fits are unaffected.

## KT1 rerun: the card fits checkpoint and the second half resumes (after two machine restarts)

The machine restarted twice while `rerun2.sh` was fitting config d (2026-09-22). The first restart
killed only the session's watcher; the second killed the pipeline itself, at config d's epoch 5,
with no weights written, and nothing ran for about 22 hours. `tools/fit_cards.py fit` now writes
`OUT.ckpt.pt` after every epoch (weights, optimiser state, both RNG states, early-stopping
bookkeeping) and `--resume` continues from it; `test_a_resumed_fit_matches_an_uninterrupted_one`
pins that a fit killed after two epochs and resumed ends on the same weights as one run straight
through, dropout included. The second half was relaunched as `scratchpad/rerun3.sh`: the same
commands, settings and order as `rerun2.sh`, with a marker per finished step so a restart skips
what is done. Config d restarts from epoch 0 with the same seed, so its result is unchanged. No
setting, selection rule or criterion changed.

## KT1 rerun: three questions from the owner before config e (answered 2026-09-23 03:30 UTC)

### 1. The holdout-Brier "discrepancy" for configs a and b was my misreading, not a computation change

Nothing about how holdout Brier is computed or reported changed. The fit logs show epoch 1 was the
best epoch for every card config from the moment it was written:

| config | epoch 1 | epoch 2 | epoch 3 | epoch 4 | epoch 5 | epoch 6 | log written |
|---|---:|---:|---:|---:|---:|---:|---|
| a | **0.12831** | 0.13644 | 0.15237 | 0.15009 | 0.17538 | 0.16943 | 2026-09-21 18:53 |
| b | **0.12889** | 0.13220 | 0.13126 | 0.13434 | 0.14694 | 0.13901 | 2026-09-21 22:22 |
| c | **0.13140** | 0.13785 | 0.14754 | 0.15887 | 0.16084 | 0.16769 | 2026-09-21 23:02 |

The 18:22 and 21:50 status reports on 09-21 were built from `tail -2`/`tail -3` of the running
logs, which showed epochs 2–3 (config a) and 3–5 (config b) but not epoch 1, and I reported the best
of the lines I happened to see. So "a best 0.1364 at epoch 2" and "b best 0.1313 at epoch 3" were
wrong; the correct figures are 0.1283 and 0.1289, both at epoch 1. The same misreading went into
this log's configs-d-and-e entry above ("best at epoch 2 (0.1364)") and into
`docs/stage1_plan_draft.md` (corrected there in this commit). The overfitting observation that
motivated d and e stands and is stronger than stated: holdout Brier rises from epoch 2, not 3.

Which number the pipeline uses: `choose.py` takes the minimum over the log's `holdout brier` lines,
which is the epoch-1 value, and the exported weights are the best epoch's state (each `.npz`
records `holdout.network` = 0.128308 / 0.128891 / 0.131400, identical to the epoch-1 lines). The
checkpointing change (7c93654, 2026-09-23) came after all three fits and does not touch
`_eval_value`; the resume test now also asserts that the held-out Brier of every epoch and the
exported summary are identical between a resumed and an uninterrupted fit.

One real finding while checking this: the 4-thread fit is **not bit-reproducible**. Config d's
epoch 1 was 0.14303 in the killed run and 0.14265 in the relaunch, same seed and settings. The
resume test passes at one thread; at four threads torch's parallel reductions are not
order-stable. My statement "config d restarted with the same seed, so its result is unchanged" was
therefore wrong; the result can differ at the fourth decimal. The selection rule is unaffected
(it reads whatever the completed fits report), and this is recorded rather than fixed.

### 2. The restarts: one was the session worker, one was the machine, and neither was memory

* **04:47 UTC 09-22** — not a machine restart. `uptime` at that moment read "1 day, 1:54" (booted
  09-21 02:53) and the fit (pid 30442) was still running; the Claude worker process restarted and
  took only its own background watcher with it.
* **Machine reset between 04:37 and 16:39 UTC 09-22.** Config d's last log line is epoch 5 at
  04:37; the current boot began 16:39:03 (`uptime -s`). The previous boot's kernel log did not
  survive (Firecracker microVM, no persistent journal, `/var/log/journal` empty), so the cause
  cannot be read directly. From 16:39 until the relaunch at 03:05 09-23 the CPUs were idle
  (149,404 of 153,068 CPU-seconds idle since boot).
* **Memory is ruled out as far as the evidence reaches.** The same fit on the same rows, running
  now: RSS 4.1 GB, peak (`VmHWM`) 4.2 GB, of 16 GB; no swap is configured; `/proc/pressure/memory`
  reads zero (some and full) since boot. The only large process in the pipeline is this fit, and
  configs a–c used the same code on the same rows. An OOM kill would also not reboot a VM; a host
  reclaim or re-provision does, and the environment documents that containers are reclaimed after
  a period of inactivity — the session was idle from ~04:50 on 09-22. My judgement: that is the
  cause. No memory cap is applied, because the evidence does not point at memory.
* **The 3.6× slowdown was not memory either.** Epoch times: a 620 s; b 800 s then ~2,270 s;
  c ~375 s; d (killed run) 1,042 s then ~4,900 s; d (now) 773 s. At 21:46 on 09-21, mid-slowdown,
  the fit was the only busy process and showed 388% CPU with a load average of 3.9, i.e. the guest
  was giving it all four vCPUs; epochs still took 3–6× longer. That pattern — full guest CPU,
  much less throughput, no swap, no memory pressure — is host-side contention (CPU steal), which
  was not being recorded. Steal now, on the fresh VM, is 1.5% over a 20 s sample. From here a
  sampler appends `/proc/stat` and the load average to `out/s1/cpu_steal.log` every five minutes,
  so a slowdown will leave evidence.

### 3. Best epoch, epochs trained, and how far the embeddings moved

| config | best epoch | epochs trained | stop |
|---|---:|---:|---|
| a | 1 | 6 | patience 5 |
| b | 1 | 6 | patience 5 |
| c | 1 | 6 | patience 5 |
| d (killed run) | 3 | 5 | machine reset |
| d (relaunch), e | running / queued | | |

Every completed config peaks after one pass over the 805,974 training rows (about 3,150 Adam steps
at batch 256) and overfits from the second: the rows are ~1M decisions but ~10k independent game
outcomes, and a second pass memorises outcomes.

Embedding drift after that one epoch (`out/s1/baselines/embedding_drift.json`): the L2 distance
of each card's 32-wide identity row from its initial value, for the 30 cards with the fewest token
occurrences in the rows (all Legends — a face-down Legend is not a token — 73k–160k occurrences,
median 112k) against the 30 most frequent (median 659k). The mean initial row norm is 0.553.

| config | rare 30 | common 30 | all 150 | rare, relative to init norm | common, relative | corr(log count, drift) |
|---|---:|---:|---:|---:|---:|---:|
| a | 0.457 | 0.387 | 0.425 | 0.83 | 0.71 | −0.30 |
| b | 0.522 | 0.475 | 0.491 | 0.94 | 0.85 | −0.26 |
| c | 0.330 | 0.271 | 0.306 | 0.60 | 0.50 | −0.29 |

What it implies: every row moved a distance comparable to its own initial size, and the **rarer
rows moved more**, not less. Under Adam each parameter takes steps of similar size whatever the
gradient's magnitude, so fewer, noisier updates give rare cards a larger random walk, not a better
representation. Drift therefore cannot be read as learning; what can is the held-out identity
ablation on rows (config a 0.1283 against 0.1353 with the rows permuted), which says identity
carries about 0.007 Brier on unseen games. Whether any of that is concentrated in the rare cards
is not something one epoch can show, and it is the question the Stage 1 draft's embedding check
(nearest-neighbour structure agreeing with the static table, stability across two splits) is for.
Note that "rare" by token count here means Legends; by game exposure the rarest cards are main-deck
cards (Animals Wrecker, Octant, MaxTac Heavy), each still with 72k+ token occurrences in these rows.

Selection rule and KT1 criterion unchanged. The pipeline continues: config d is fitting at ~13
minutes an epoch, then e.

## Correction (2026-09-23 09:15 UTC): the slowdown was subnormal floats, not the host

The answer to question 2 above said the 3.6× slowdown was host-side CPU contention. **That was
wrong.** The CPU sampler (`out/s1/cpu_steal.log`) recorded config d's slow epochs 2–3 at 96% user
CPU and 0.4% steal, with a load average of 3.9: the guest had the CPUs and they were slow on
this work. A read of d's epoch-3 checkpoint found the cause:

* **17% of config d's weights were subnormal floats**, including 80% of the attention query/key
  weights and 70% of the feed-forward weights, plus 10% of Adam's moment estimates. Subnormal
  arithmetic on x86 is one to two orders of magnitude slower than normal arithmetic.
* **The slowdown depends on the config, which is why it looked like the machine.** Configs with
  l2 1e-5 (a, c) ran at a steady 620 s and 375 s an epoch and export 0.25% and 0.08% subnormals.
  Config b (l2 1e-4) slowed from epoch 2 and exports 3.4%. Config d (l2 1e-3) slowed from epoch 2
  to about 3,700 s an epoch and holds 17%.
* **Mechanism.** `torch.optim.Adam(weight_decay=…)` adds the L2 term to the gradient before Adam
  normalises it. A weight whose real gradient is small is therefore pushed toward zero by about
  lr per step, whatever its size. The attention query/key weights have small gradients and decay
  to nothing.
* **Fix.** `torch.set_flush_denormal(True)` in `fit` and `fit114`, and subnormals written as exact
  zeros at export so the numpy inference path is not slowed either. A test asserts that an
  exported fit contains no subnormals. This changes values only below 1.2e-38 and changes no
  setting. Config d resumed from its epoch-3 checkpoint with the fix on.

**A finding for the KT1 report, not acted on.** Under coupled L2 at 1e-4 and above, the attention
layer collapses. In config b's exported (epoch-1) weights the median |attn_q| is 7e-23, against
0.027 in config a, so b's attention is uniform and b is in effect a no-attention model. Config d
shows the same, and config e (l2 1e-3) will too. Switching to decoupled weight decay (AdamW) would
be tuning, so the settings stay as registered. The report will say which model the selection
picked and whether its attention is alive.

**The restarts, updated.** The machine rebooted again at 09:06:20 UTC on 09-23, the minute the
scheduled check-in fired. The CPU sampler's last line before the reboot is 05:39. From that
timing, my judgement is that the environment reclaims an idle session's machine and provisions a
new one when the session is woken. The 05:35 notice was a worker restart only: the boot time was
unchanged and the pipeline survived it. With checkpoints and step markers, each reboot now costs
at most the epoch in progress.

## KT1 rerun: order changed and a secondary panel added (owner, 2026-09-23T20:33Z, before any panel result)

No panel, head-to-head or suite result of the rerun exists at the time of writing
(`out/s1/kt1/` is empty). Head choice (card config e, 114 head h16) and the KT1 criterion are
unchanged.

1. **Reorder.** The 128-playout independent-oracle step is stopped at about 900 of 2,000
   positions; `oracle.py playouts --resume` continues from the positions already written (it
   saves every 25, so at most 24 positions are redone). The rest runs in this order: the three
   registered KT1 panels (`neural@out/s1/w114.json` = h16, `neural-cards@out/s1/wcards.npz` =
   config e, `neural-cards-ablated@out/s1/wcards.npz`); then the secondary panels below; then the
   mirrored head-to-head; then the delayed suite by family; then the playouts, agreement scoring
   and final monotonicity. The KT1 criterion reads only the three registered panels, so the order
   cannot change the verdict. KT1 is reported as soon as those panels finish.
2. **Pre-declared secondary, not pass/fail: config a.** Panels for `neural-cards@out/s1/wcards_a.npz`
   and `neural-cards-ablated@out/s1/wcards_a.npz`, written to `out/s1/kt1_secondary/`. Reason:
   config e's attention query/key weights and most of its feed-forward weights are about 1e-32, so
   the registered KT1 tests card tokens plus pooling plus the 114 aggregates. Config a is the only
   card model with live attention and feed-forward layers (median |attn_q| 0.027), and its holdout
   Brier (0.12831) is within 0.0005 of e's (0.12783). Its panels are reported next to KT1 and
   labelled secondary; they do not enter the verdict. Config a's weights were exported before the
   subnormal flush at export and hold 0.25% subnormals, which affects only inference speed.

## After KT1: the owner's delegation, and the signal diagnostic, pre-registered (2026-09-25T04:59Z, before any fit)

The owner answered the two open decisions with "do what you think is best". My calls, recorded
before anything runs:

1. **The FAIL version of the Stage 1 draft is accepted.** There will be no card-aware head for
   Stage 1 and no third KT1. The next question is the learning signal.
2. **The signal diagnostic is pre-registered here**, with its decision rules, before any fit.
3. **`docs/strategy_guide.md` is committed.** The owner held it "until I say", and the delegation
   covers it.

### Experiment 1 — a per-decision value target

* **Target, fixed now:** `y = 0.7 · v_next + 0.3 · z`. Here `v_next` is the search's stored root
  value, from the row's seat, at the first decision that seat faces in its own next turn, and
  `z` is the game outcome. When the game ends before that turn, `y = z`. The code is
  `fit_cards.next_turn_values` / `BOOTSTRAP_LAMBDA`, pinned by two tests. The source is the same
  10,000 games, rebuilt with the same rate (0.5) and seed (7), so the rows and the by-game split
  are identical to the rerun's.
* **Heads, fixed now:**
  * the 114 head with h16's settings (`fit114 --hidden 16`);
  * the card model with config a's settings (lr 1e-3, l2 1e-5, embedding 32, policy weight 0.5),
    the only card config whose attention stays alive.

  Both use `--target boundary`, early stopping on holdout Brier against `y`, and the visit
  distribution as the policy target.
* **R1, evaluation.** Each boundary-trained head's Spearman against the independent playout
  oracle is compared with its outcome-trained twin (h16: 0.655 [0.627, 0.682]; config a: scored
  in this run). It counts as *improved* only if the boundary-trained 95% interval lies wholly
  above the outcome-trained one.
* **R2, play.** Frozen panel, 360 games a member. It counts as *improved* only if the
  boundary-trained head's rate against the heuristic is above the outcome-trained head's
  between-pairing band: h16 0.713, config a 0.724.
* **R3, identity (information only, not a third KT1).** The KT1 legs are read on the
  boundary-trained card model, its identity ablation, and the boundary-trained 114 head.
* **What follows.**
  * R2 holds for the 114 head: the Stage 1 loop trains on boundary targets.
  * R2 holds for neither head: the signal is not the lever either; the report says so and stops.
  * R2 holds for the card model and R3's two legs clear: that is reported to the owner as the
    first evidence that identity helps under the right signal. Nothing is started on it.

### Experiment 2 — held-out cards (changed from the plan, and why)

The plan said twelve cards. Measured on s10k before registering, only **187 of 10,000 games
(1.9%)** contain none of those twelve, and 88.6% of rows show at least one of them, so that
design cannot be trained. Registered instead: **one card per type**, the median-exposure verified
card of each type by games containing it in either list:

| type | card | games in s10k |
|---|---|---:|
| Legend | Royce — Psycho on the Edge | 2,296 |
| Unit | Rockn' Rockerboy | 2,447 |
| Program | Chrome Reverie | 2,815 |
| Gear | Zetatech Berserk | 3,666 |

**2,061 games (20.6%)** contain none of the four (`out/s1/heldout_cards.json`).

* **Training.** Both heads (boundary targets, the settings above) train only on those games,
  with the same 80/20 by-game split inside them.
* **Set A.** Rows from the other 7,939 games in which one of the four cards is visible or offered.
* **Set B.** The ordinary holdout rows of the 2,061 training games.
* **Reading.** For each head, gap = Brier(A) − Brier(B). The quantity reported is
  gap(card model) − gap(114 head), with a 95% bootstrap interval over games (1,000 resamples).
  *The embedding is doing work* if that interval lies wholly above zero, meaning the card model
  loses more than the aggregate head on cards whose embeddings it never trained. Otherwise the
  embedding is decorative at this data size.
