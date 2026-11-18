# Mischa

**A human-like chess engine that plays in the style of Mikhail Tal, at about 2000 FIDE.**

[![CI](https://github.com/olaflaitinen/mischa-chess/actions/workflows/ci.yml/badge.svg)](https://github.com/olaflaitinen/mischa-chess/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

Mischa was the name Mikhail Tal's friends called him by. The engine is built on
[OpenTal](http://www.pkoziol.cal24.pl/opental) by Pawel Koziol, an engine that already plays
the attacking, sacrificial chess of "the wizard from Riga". OpenTal is strong, around 2500
to 2600 Elo by its author's estimate, and it plays like an engine. Mischa adds a layer that
makes it play like a person:

* it looks at a handful of candidate moves to a limited depth, as a club player would,
* it always finds the obvious moves: short mates, recaptures, hanging pieces,
* it makes small inaccuracies, and now and then a real mistake, more often in complicated
  positions and when the clock runs low,
* its mistakes are human ones: it tends to trust the move that looks best at first sight,
* it spends its time like a person: quick in the opening and in obvious positions, longer
  when the position is sharp,
* and it keeps Tal's taste for checks, captures and sacrifices.

The default strength is `UCI_Elo 2000`. Any level from 1000 to 2600 can be set, and with
`UCI_LimitStrength` switched off Mischa plays at the full strength of OpenTal.

How the human layer works is described in [docs/HUMANIZER.md](docs/HUMANIZER.md).
How the strength is measured, and how it relates to FIDE, Lichess and Chess.com ratings, is
in [docs/CALIBRATION.md](docs/CALIBRATION.md). The complete test suite is described in
[testing/README.md](testing/README.md).

## Download

Ready-made builds for Windows, Linux and macOS are attached to every
[release](https://github.com/olaflaitinen/mischa-chess/releases). Unpack the archive and
keep the `books` folder next to the executable.

| file | for |
|---|---|
| `mischa-windows-x86-64-popcnt.zip` | Windows, any CPU from about 2010 on |
| `mischa-windows-x86-64.zip` | Windows, very old CPUs |
| `mischa-linux-x86-64-popcnt.zip` | Linux, any CPU from about 2010 on |
| `mischa-linux-x86-64.zip` | Linux, very old CPUs |
| `mischa-macos-arm64.zip` | Macs with Apple silicon |

## Using Mischa

Mischa is a UCI engine. It needs a chess GUI such as
[Cute Chess](https://github.com/cutechess/cutechess), [Arena](http://www.playwitharena.de/)
or [En Croissant](https://encroissant.org/). Add it as a new UCI engine and start a game
with a clock: the human behaviour needs a real time control (for example 10 minutes + 5
seconds). With "fixed depth" or "fixed time per move" Mischa still plays human moves, but
the human timing is switched off.

To play humans online, see [docs/LICHESS_BOT.md](docs/LICHESS_BOT.md).

### Options

| option | default | meaning |
|---|---|---|
| `UCI_LimitStrength` | `true` | play like a human; `false` gives full-strength OpenTal |
| `UCI_Elo` | `2000` | target strength, 1000 to 2600 |
| `HumanTime` | `true` | think for a human amount of time and play worse when short of time |
| `Flair` | `100` | 0 to 200, preference for forcing and sacrificial moves (100 = Tal) |
| `RandomSeed` | `0` | 0 = different games every time; any other value makes play reproducible |
| `HumanVerbose` | `false` | print the reason for every move choice as `info string` |
| `UseBook` | `true` | use the opening books (the book depth follows `UCI_Elo`) |
| `MainBookFile` | `rodent.bin` | Polyglot book in the `books` folder |
| `Hash`, `Threads`, `MultiPV`, `Ponder`, `TimeBuffer` | | as in OpenTal |

`MultiPV` above 1 and `go infinite` always use the full-strength search, so Mischa can
still be used to analyse games.

## Building from source

You need a C++14 compiler and CMake 3.14 or newer.

```bash
git clone https://github.com/olaflaitinen/mischa-chess.git
cd mischa-chess
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DMISCHA_POPCNT=ON
cmake --build build --config Release
ctest --test-dir build -C Release      # runs the UCI smoke test (needs Python 3)
```

The executable and a copy of the `books` folder end up in `build/` (on Windows with Visual
Studio in `build/Release/`). Leave out `-DMISCHA_POPCNT=ON` for CPUs older than about 2010.

Without CMake a plain `make` works on Linux and macOS (`make popcnt` for a faster build on
x86-64 CPUs).

| CMake option | default | effect |
|---|---|---|
| `MISCHA_POPCNT` | `OFF` | use the hardware POPCNT instruction (x86-64 only), faster |
| `MISCHA_NATIVE` | `OFF` | optimise for the CPU of the build machine |
| `MISCHA_THREADS` | `ON` | build with multi-threaded search |

The books are looked up in a `books` folder next to the executable. On Linux and macOS
another folder can be given with the `MISCHA_BOOKS` environment variable.

## Repository layout

```
src/              engine sources (OpenTal / Rodent III) and the human layer
  humanizer.cpp   candidate search, complexity, move choice and timing
books/            Polyglot opening books
docs/             how the humanizer works, calibration, Lichess bot setup
tests/            UCI smoke test
testing/          full test suite (strength, Elo scale, robustness, move quality),
                  with job scripts for the CSC Roihu supercomputer
tools/            calibration script (matches against Stockfish)
```

## Credits and license

Mischa is written by **Yunus Imanov**, Department of Engineering Mathematics and Artificial
Intelligence, Azerbaijan Technical University, Baku, Azerbaijan
(yunus.imanov.fz@student.aztu.edu.az).

It stands on the work of Pawel Koziol (OpenTal and Rodent III), Brendan J. Norman (the Tal
personality) and Pablo Vazquez (Sungorus). See [AUTHORS](AUTHORS).

Mischa is free software under the [GNU General Public License v3.0](LICENSE) or later, the
same license as OpenTal and Rodent.
