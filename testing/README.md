# Test suite

`run_suite.py` evaluates Mischa from every side and writes a Markdown report. It is meant
for a machine with many cores, such as one node of CSC's Roihu supercomputer, but the
`quick` profile also runs on a laptop.

## What is tested

| stage | what it checks | full profile |
|---|---|---|
| `perft` | the move generator, on seven standard positions with known node counts | depths 5 to 7 |
| `robustness` | random positions, random options and every kind of `go` command, including `stop` and `isready` while thinking; the engine must always answer with a legal move, never crash or hang, and stay within its clock. One batch in ten runs on a build with AddressSanitizer and UndefinedBehaviorSanitizer | 20 000 positions |
| `strength` | Mischa at `UCI_Elo 2000` against Stockfish `UCI_Elo` 1600, 1800, 2000, 2200 and 2400 | 10 000 games at 60 s + 0.6 s |
| `scale` | every `UCI_Elo` level from 1200 to 2400 against Stockfish 200 below, equal and 200 above; shows whether the Elo setting means what it says | 8 000 games at 60 s + 0.6 s |
| `human` | games on a real clock with human timing on: think-time distribution, fast obvious moves, more time in complex positions, no time losses | 380 games at 10 min + 5 s |
| `analysis` | every Mischa move from `strength` and `human` checked by full-strength Stockfish: centipawn loss, Lichess-style accuracy, inaccuracies, mistakes and blunders, by game phase and by position complexity | depth 12 |
| `report` | `REPORT.md`, `summary.json` and PGN files of all games | |

Ratings are computed by maximum likelihood over all opponents, with 95 % confidence
intervals. They are on the Stockfish `UCI_Elo` scale; `docs/CALIBRATION.md` explains how
that relates to human ratings.

## Running on Roihu

All commands are run from the repository root on a Roihu-CPU login node.

**1. Get the code.** Use the project's scratch folder, the home folder is small:

```bash
cd /scratch/<project>
git clone https://github.com/olaflaitinen/mischa-chess.git
cd mischa-chess
```

**2. Build everything** (Mischa, a sanitizer build, Stockfish 17.1, a Python environment
with python-chess). The login node has internet access, the compute nodes do not, so this
step runs here. It takes a few minutes:

```bash
bash testing/roihu/setup.sh
```

**3. Quick check** on the `test` partition (64 cores, about 10 minutes):

```bash
sbatch --account=<project> testing/roihu/quick.sbatch
```

Follow it with `squeue --me` and `tail -f mischa-quick-<jobid>.out`. When it is done, read
`testing/results/quick-<jobid>/REPORT.md`.

**4. Full run** on one `medium` node (384 cores, about two hours, time limit five hours):

```bash
sbatch --account=<project> testing/roihu/full.sbatch
```

The report is written to `testing/results/full-<jobid>/REPORT.md`.

**Resuming.** If the job stops before the end, submit it again with the same output folder.
Finished games are kept and only the missing ones are played:

```bash
sbatch --account=<project> \
    --export=ALL,MISCHA_OUT=$PWD/testing/results/full-<jobid> testing/roihu/full.sbatch
```

**Single stages** can be run with `MISCHA_STAGES`, for example
`--export=ALL,MISCHA_STAGES=scale,report`.

**Billing.** A full run reserves one whole node; at about two hours that is roughly 770
core-hours. Check the project's remaining billing units with `csc-projects` first.

## Running anywhere else

```bash
pip install chess
python3 testing/run_suite.py --mischa build/mischa --stockfish /path/to/stockfish --profile quick
```

Options:

| option | meaning |
|---|---|
| `--profile quick` or `full` | size of the run (see the table at the top) |
| `--stages a,b,c` | run only some stages |
| `--workers N` | games played in parallel (default: number of CPUs minus one) |
| `--mischa-asan PATH` | Mischa built with sanitizers, used for part of the robustness stage |
| `--out DIR` | output folder; reuse it to resume an interrupted run |
| `--seed N` | changes the random positions and seeds; the default makes runs repeatable |

A sanitizer build can be made with:

```bash
make popcnt EXE=mischa-asan CXXFLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined" \
    LDFLAGS="-fsanitize=address,undefined"
```

## Output

```
testing/results/<run>/
  REPORT.md          the report
  summary.json       the main numbers, machine readable
  config.json        the exact settings of the run
  strength.pgn       all games (also scale.pgn, human.pgn), Mischa's moves annotated
                     with the position complexity and the reason for the choice
  *.jsonl            raw results, used for resuming
```

`REPORT.md` and `summary.json` are small and can be committed; the other files are ignored
by git.
