# Changelog

## Unreleased

* `perft <depth>` UCI command for checking the move generator.
* Full test suite (`testing/run_suite.py`): perft, robustness with random positions and
  sanitizers, strength against Stockfish, the whole `UCI_Elo` scale, human timing and move
  quality analysis, with a Markdown report. Job scripts for the CSC Roihu supercomputer.
* `make` accepts extra `CXXFLAGS` and `LDFLAGS` on the command line without losing the
  required flags.

## 1.0 (2026-11-18)

First release of Mischa, based on OpenTal 1.1 by Pawel Koziol.

### Human-like play

* New human layer (`src/humanizer.cpp`): multi-candidate search with a rating-dependent
  depth, complexity estimate, noisy move choice, rare human mistakes based on the
  "first impression" move, and moves that are never missed (short mates, recaptures,
  hanging material, only moves).
* Human time management: fast in obvious positions and in the opening, longer in complex
  positions, random variation, a short pause before book moves, and more mistakes under
  time pressure. `stop` is answered at once.
* Opening book depth follows the target rating.
* New UCI options: `UCI_LimitStrength`, `UCI_Elo` (1000 to 2600, default 2000),
  `HumanTime`, `Flair`, `RandomSeed`, `HumanVerbose`.
* `MultiPV` above 1, `go infinite` and `UCI_LimitStrength false` keep the full-strength
  OpenTal search for analysis.

### Engine and build

* Engine renamed to Mischa 1.0.
* CMake build for Windows, Linux and macOS, plus a plain Makefile.
* Fixed the Linux build (missing `<cmath>`) and the macOS build (executable path lookup).
* Fixed a possible buffer overflow when reading long FEN strings.
* Fixed a crash of the multi-threaded search: the search thread kept a reference to a
  variable that went out of scope (seen on macOS).
* Fixed the MSVC build (missing `<chrono>` include).
* `isready` is now answered while the engine is thinking.
* Book files are checked when they are read into memory.
* Books can be placed in a folder given by the `MISCHA_BOOKS` environment variable.
* UCI smoke test, calibration script against Stockfish, CI on three platforms and
  release builds.
