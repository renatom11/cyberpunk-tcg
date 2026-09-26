#!/bin/bash
# Run the Stage 1 loop on a local machine (see docs/stage1_local.md).
#
#   bash tools/stage1_local.sh [WORKERS]
#
# Needs, under the repo root: out/s1/s10k (+ .harvest.json) and out/s2/w114_boundary.json (the
# incumbent), copied from the transfer branch. Rebuilds the seed rows locally, then starts or
# resumes the loop in out/stage1/loop. Safe to re-run after a crash, reboot or sleep: every step
# resumes (rows are skipped once built, the loop resumes from its ledger, the harvest from its
# manifest).
set -euo pipefail
cd "$(dirname "$0")/.."
W=${1:-$(( $(nproc) - 2 ))}
export PYTHONPATH=src
for f in out/s1/s10k out/s1/s10k.harvest.json out/s2/w114_boundary.json; do
  [ -e "$f" ] || { echo "missing $f - copy it from the transfer branch first (docs/stage1_local.md)"; exit 1; }
done
python3 -c "import numpy, torch" 2>/dev/null || { echo "install numpy and torch first (docs/stage1_local.md)"; exit 1; }
mkdir -p out/stage1
if [ ! -e out/s2/rows.npz ]; then
  echo "building seed rows with $W workers..."
  python3 tools/fit_cards.py rows --in out/s1/s10k --out out/s2/rows --rate 0.5 --perspectives both --lite --workers "$W"
fi
echo "Stage 1 loop, $W workers, log out/stage1/loop.log"
python3 tools/learn.py run --stage1 --target boundary --incumbent out/s2/w114_boundary.json \
  --dir out/stage1/loop --games 30000 --hours 10000 -j "$W" \
  --generator ismcts-explore:32 --player ismcts:32 \
  --seed-rows out/s2/rows.npz --seed-games out/s1/s10k 2>&1 | tee -a out/stage1/loop.log
