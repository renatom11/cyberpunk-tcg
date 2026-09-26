# transfer/stage1-inputs

Data branch for running the Stage 1 loop on a local machine. It is never merged. The steps are in
`docs/stage1_local.md` on `claude/wizardly-archimedes-e20tzv`.

* `transfer/s10k`, `transfer/s10k.harvest.json`: the 10,000-game `ismcts:32` search corpus (seed
  rows and seed visits).
* `transfer/w114_boundary.json`: the incumbent, the boundary-trained 114 head (experiment 1).
* `transfer/loop/` (when present): the loop's ledger and each finished generation's games,
  weights and gate results. The laptop resumes from them.
