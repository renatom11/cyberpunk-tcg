# Running the Stage 1 loop on your laptop

The loop is the one registered in `docs/stage0_decisions.md` (boundary target, 30,000 games a
generation, `ismcts-explore:32` generator, `ismcts:32` gate, plan-candidate stage off). Nothing
about it depends on the machine; more cores only make generations faster. On an 8-core / 16-thread
laptop with 14 workers, expect roughly 3–4× the cloud VM's 1 game/s.

## 1. One-time setup (Windows 11: use WSL)

In PowerShell as administrator:

    wsl --install -d Ubuntu

Reboot, open **Ubuntu**, then:

    sudo apt update && sudo apt install -y git python3 python3-venv python3-pip
    git clone https://github.com/renatom11/cyberpunk-tcg.git
    cd cyberpunk-tcg
    git checkout claude/wizardly-archimedes-e20tzv
    python3 -m venv .venv && . .venv/bin/activate
    pip install numpy "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu

WSL uses half the machine's memory by default (about 7.5 GB here), which is enough: the 114
head's fit needs well under that.

## 2. Bring over the inputs

The corpus and the incumbent are not in git (`out/` is ignored). Copy them from the transfer
branch:

    git fetch origin transfer/stage1-inputs
    git checkout origin/transfer/stage1-inputs -- transfer/
    mkdir -p out/s1 out/s2 out/stage1
    mv transfer/s10k transfer/s10k.harvest.json out/s1/
    mv transfer/w114_boundary.json out/s2/
    # optional, to continue generation 0 where the cloud stopped instead of starting it again:
    [ -d transfer/loop ] && mv transfer/loop out/stage1/loop
    rm -rf transfer && git reset -q

## 3. Run

    . .venv/bin/activate
    bash tools/stage1_local.sh          # workers = cores - 2; or pass a number

Keep the laptop plugged in and set Windows to never sleep while plugged in. If it does sleep or
reboot, run the same command again: everything resumes.

## 4. What to send back

After each generation, `out/stage1/loop/ledger.json` and `out/stage1/loop/gen-NNN/gate/` hold
the verdict. To let the cloud session report on and continue from a generation, push them:

    git checkout -b stage1-results
    git add -f out/stage1/loop/ledger.json out/stage1/loop/gen-*/gate out/stage1/loop/gen-*/weights.json
    git commit -m "Stage 1 generation results" && git push -u origin stage1-results

If you run Claude Code locally in this folder, it can do all of the above for you.
