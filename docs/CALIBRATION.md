# Calibration

The goal of Mischa is to play like a human rated about **2000 FIDE**. A rating is not a
setting that can simply be switched on; it has to be measured. This document explains how
Mischa is measured and how the numbers relate to FIDE, Lichess and Chess.com.

## Measuring against Stockfish

`tools/calibrate.py` plays matches between Mischa and Stockfish with `UCI_LimitStrength`
enabled. Stockfish's `UCI_Elo` levels are calibrated by the Stockfish team against the CCRL
engine rating list, which makes them a reproducible yardstick that anyone can download.

```bash
pip install chess
python3 tools/calibrate.py --mischa build/mischa --stockfish /path/to/stockfish \
    --anchors 1800 2000 2200 --games 100 --tc 60+0.6 --concurrency 4 --pgn games.pgn
```

* Openings are taken from a fixed list and every opening is played with both colors.
* Mischa runs with `HumanTime` off, so games are fast and the clock-pressure effects stay
  out of the measurement.
* The script prints the score against each level, the rating difference with a 95 %
  confidence interval and a combined estimate.

Use at least 100 games per anchor for a usable result. With fewer games the error bars are
wide (around +/- 100 Elo for 40 games).

For a much larger and more detailed evaluation (tens of thousands of games, every `UCI_Elo`
level, robustness and move-quality analysis) use the test suite in
[`testing/`](../testing/README.md).

## Results for version 1.0

Mischa 1.0 with the default `UCI_Elo 2000`, `HumanTime` off, time control 12 s + 0.12 s,
Stockfish 16 as the anchor, 12 games per anchor:

| opponent | result | score | performance |
|---|---|---|---|
| Stockfish `UCI_Elo 1800` | +8 =1 -3 | 70.8 % | 1954 |
| Stockfish `UCI_Elo 2100` | +4 =2 -6 | 41.7 % | 2042 |
| **combined estimate** | | | **about 2000** |

With 24 games the uncertainty is large (roughly +/- 150 Elo), so treat this as a first
check that the default level is in the right range, not as a final number. Larger runs are
welcome; please open an issue with the output and the PGN.

The same games were checked with Stockfish at depth 11 to see whether the mistakes look
human. Over 1287 of Mischa's moves:

| measure | value |
|---|---|
| average centipawn loss | 37.9 |
| inaccuracies and mistakes (100 to 299 cp) | 3.7 per game |
| blunders (300 cp or more) | 0.2 per game |

That profile, many small errors and rare big ones, is typical of club players around
2000.

## From engine ratings to human ratings

Engine-list ratings and human ratings are different scales. Even inside the human world,
FIDE, Lichess and Chess.com ratings differ by hundreds of points at the same playing
strength, and the gap changes with the rating level and the time control. Surveys that
compare players' ratings on several sites (for example
[ChessGoals' rating comparison](https://chessgoals.com/rating-comparison/)) give a rough
picture for a player around 2000 FIDE:

| scale | approximate equivalent of 2000 FIDE |
|---|---|
| FIDE classical | 2000 |
| Lichess rapid / blitz | about 2200 to 2300 |
| Chess.com rapid | about 2000 to 2100 |

These are averages with a wide spread, not exact conversions.

## Validating against people

The only reliable check of "plays like a 2000 human" is to let Mischa play humans. The
recommended way is a Lichess bot account with
[lichess-bot](https://github.com/lichess-bot-devs/lichess-bot); see
[`LICHESS_BOT.md`](LICHESS_BOT.md). After a few hundred rated games, compare the bot's
Lichess rapid rating with the table above and adjust `UCI_Elo` (or the functions in
`src/humanizer.cpp`) until the rating settles where you want it.

Running any engine in games on Chess.com is against that site's fair play rules. Do not do
it; Chess.com does not offer bot accounts.
