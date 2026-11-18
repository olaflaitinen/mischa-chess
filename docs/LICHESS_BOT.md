# Running Mischa as a Lichess bot

Lichess allows engines to play on special BOT accounts. This is the right place to let
Mischa meet human opponents and to check its rating against people.

## 1. Create a bot account

1. Register a **new** Lichess account for the bot. An account that has already played
   games cannot be turned into a bot account.
2. Create an API token for it at <https://lichess.org/account/oauth/token> with the
   `bot:play` scope.
3. Upgrade the account to a bot account. lichess-bot can do this for you with
   `python3 lichess-bot.py -u`.

## 2. Install lichess-bot

```bash
git clone https://github.com/lichess-bot-devs/lichess-bot.git
cd lichess-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.yml.default config.yml
```

## 3. Put Mischa in place

Build Mischa (see the main README) and copy the executable together with its `books`
folder into `lichess-bot/engines/`:

```
lichess-bot/engines/mischa
lichess-bot/engines/books/rodent.bin
lichess-bot/engines/books/ph-tal2.bin
```

## 4. Configure

Edit these parts of `config.yml` (keep the rest of the default file):

```yaml
token: "your-bot-token"

engine:
  dir: "./engines/"
  name: "mischa"              # mischa.exe on Windows
  protocol: "uci"
  ponder: false
  uci_options:
    Hash: 64
    Threads: 1
    UCI_LimitStrength: true
    UCI_Elo: 2000
    HumanTime: true
    Flair: 100

challenge:
  concurrency: 1
  variants:
    - standard
  time_controls:
    - blitz
    - rapid
    - classical
  modes:
    - casual
    - rated
```

Keep `concurrency` at 1: the human timing makes Mischa use its clock like a person, and
several parallel games would slow each other down.

## 5. Run

```bash
python3 lichess-bot.py
```

Rapid games (10 minutes or more) give the most human-like behaviour and the most useful
rating information.
