#!/bin/bash
# Builds everything the test suite needs: Mischa (normal and sanitizer builds), Stockfish
# and a Python environment with python-chess. Run it once on a Roihu login node (the
# compute nodes have no internet access), from anywhere inside the repository:
#
#     bash testing/roihu/setup.sh
#
# Works on any Linux machine with git, make, a C++17 compiler and Python 3.8+.
#
# Environment variables:
#     MISCHA_WORK   where to put the builds (default: testing/work in the repository)
#     SF_TAG        Stockfish release to build (default: sf_17.1)
#     JOBS          parallel compile jobs (default: 8)

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${MISCHA_WORK:-$REPO/testing/work}"
SF_TAG="${SF_TAG:-sf_17.1}"
JOBS="${JOBS:-8}"

mkdir -p "$WORK/bin"
echo "repository: $REPO"
echo "work folder: $WORK"

# Roihu uses environment modules; load a recent compiler if one is offered.
if type module >/dev/null 2>&1; then
    module load gcc >/dev/null 2>&1 || true
fi

for tool in git make g++ python3; do
    command -v "$tool" >/dev/null 2>&1 || { echo "error: $tool is not available"; exit 1; }
done
echo "compiler: $(g++ --version | head -n 1)"
echo "python:   $(python3 --version)"

# --- Mischa ------------------------------------------------------------------------------

echo
echo "== building Mischa"
make -C "$REPO" -s clean EXE="$WORK/bin/mischa"
make -C "$REPO" -s popcnt EXE="$WORK/bin/mischa" CXXFLAGS="-O3"
make -C "$REPO" -s popcnt EXE="$WORK/bin/mischa-asan" \
    CXXFLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined" \
    LDFLAGS="-fsanitize=address,undefined"
rm -rf "$WORK/bin/books"
cp -r "$REPO/books" "$WORK/bin/books"

# --- Stockfish ---------------------------------------------------------------------------

echo
echo "== building Stockfish $SF_TAG"
if [ ! -x "$WORK/bin/stockfish" ] || [ "$(cat "$WORK/bin/stockfish.tag" 2>/dev/null)" != "$SF_TAG" ]; then
    rm -rf "$WORK/stockfish-src"
    git clone --quiet --depth 1 --branch "$SF_TAG" \
        https://github.com/official-stockfish/Stockfish.git "$WORK/stockfish-src"
    # AVX2 runs on every current x86-64 server CPU, including Roihu's AMD Turin
    make -C "$WORK/stockfish-src/src" -s -j "$JOBS" build ARCH=x86-64-avx2
    cp "$WORK/stockfish-src/src/stockfish" "$WORK/bin/stockfish"
    echo "$SF_TAG" > "$WORK/bin/stockfish.tag"
else
    echo "already built"
fi

# --- Python ------------------------------------------------------------------------------

echo
echo "== Python environment"
if [ ! -x "$WORK/venv/bin/python" ]; then
    python3 -m venv "$WORK/venv"
fi
"$WORK/venv/bin/python" -m pip install --quiet --upgrade pip
"$WORK/venv/bin/python" -m pip install --quiet chess

# --- check -------------------------------------------------------------------------------

echo
echo "== check"
"$WORK/venv/bin/python" "$REPO/tests/smoke_test.py" "$WORK/bin/mischa" | tail -n 1
printf 'uci\nquit\n' | "$WORK/bin/stockfish" | grep '^id name'
printf 'position startpos\nperft 4\nquit\n' | "$WORK/bin/mischa" | grep '^perft'

echo
echo "Setup finished. Next steps (from the repository root):"
echo "  sbatch --account=<project> testing/roihu/quick.sbatch     # about 10 minutes"
echo "  sbatch --account=<project> testing/roihu/full.sbatch      # about 2 hours"
