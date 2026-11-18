# How Mischa plays like a human

Mischa keeps the search and the evaluation of OpenTal, which already plays in the
attacking, sacrificial style of Mikhail Tal. What it adds is a layer that decides *which*
of the engine's candidate moves is actually played, and *how long* to think about it.
All of it lives in `src/humanizer.cpp`.

A normal engine at reduced strength is usually weakened by searching fewer nodes. That
gives an opponent that is uniformly shallow: it never hangs a piece in a quiet position,
but misses every three-move combination. People do not play like that. A club player
finds simple tactics almost always, misses deep ones often, plays obvious moves fast, and
goes wrong far more often in messy positions and when short of time. The humanizer models
exactly those effects.

## 1. Candidate search

For every move Mischa runs a multi-PV search over the six best candidate moves, limited to
a depth that depends on the target rating (depth 8 at 2000). The search records

* the score of every candidate,
* the move that looked best after depth 2, the "first impression",
* how many times the best move changed between depth 3 and the final depth.

## 2. How hard is the position?

These numbers are combined into a complexity value between 0 and 1:

| ingredient | weight | idea |
|---|---|---|
| instability of the best move | 0.35 | if the engine keeps changing its mind, so would a person |
| material on the board | 0.20 | more pieces, more to calculate |
| only-move situations | 0.25 | the best move is much better than the rest and is a quiet move |
| number of legal moves | 0.20 | more options, more chances to choose badly |

Being in check reduces the value, since the choice is usually narrow.

## 3. Moves that are never missed

Some moves any 2000 player finds, so they are played without noise:

* a forced mate within the player's "mate vision" (3 moves at 2000),
* a recapture on the square where the opponent just captured, when it is clearly best,
* winning material that is simply hanging,
* the only legal move.

## 4. Choosing the move

Every other move is chosen by adding random noise to the candidates' scores and taking
the best result. The size of the noise grows with the complexity of the position and,
when human timing is on, with time pressure. Candidates that lose more than a set amount
(140 centipawns at 2000) are never picked this way, so ordinary noise produces small
inaccuracies, not blunders.

On top of that there is a small chance of a real mistake (about 1.5 % per move at 2000,
more in complex positions). A mistake is usually the first-impression move: the one that
looked best at a glance but fails to something deeper. This is the most typical way club
players lose games.

The `Flair` option adds a small bonus to checks, captures, sacrifices and moves near the
enemy king. It only decides between moves of nearly equal value, so it colours the play
without making it unsound.

## 5. Spending time

With `HumanTime` on, the engine does not answer instantly. It estimates the normal time per
move from the clock, then

* plays obvious moves and the opening quickly,
* thinks longer when the position is complex,
* varies its timing randomly, like a person,
* never uses more than 15 % of the remaining clock on one move,
* answers at once when the GUI sends `stop`.

Book moves get a short pause as well. When the clock runs low, the noise and the mistake
rate go up, as they do for humans.

## 6. Parameters by rating

All parameters are simple functions of `UCI_Elo`:

| UCI_Elo | depth | noise (cp) | mistake rate | normal loss cap | mistake loss cap | mate vision | book plies |
|---|---|---|---|---|---|---|---|
| 1200 | 4 | 45 | 3.1 % | 273 | 450 | 1 | 8 |
| 1600 | 6 | 35 | 2.3 % | 206 | 350 | 2 | 16 |
| 2000 | 8 | 25 | 1.5 % | 140 | 250 | 3 | 24 |
| 2400 | 10 | 15 | 0.7 % | 73 | 150 | 4 | 32 |

The functions are at the top of `src/humanizer.cpp`. To change the character of the engine,
edit them and measure the result with `tools/calibrate.py` (see `CALIBRATION.md`).
