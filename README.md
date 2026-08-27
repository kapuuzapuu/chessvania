# Chessvania

A terminal chess roguelike. You pilot a **persistent army** up a ladder of enemy
formations played by Stockfish at rising Elo. Win a fight → earn **gold** based on
how few moves you took → spend it on pieces for your bench. **Captured pieces are
gone for good.** One life per run.

Every position is legal standard chess. Pieces move normally, there are no fairy
pieces and no abilities — which is exactly why Stockfish can play the other side.
All the roguelike systems live between fights and never touch how a piece moves.

## Install

Chessvania needs a Stockfish binary, which it does **not** bundle (it's GPL-3.0 and
multi-megabyte per platform). Install one first:

```sh
brew install stockfish            # macOS
sudo apt install stockfish        # Debian/Ubuntu
# Windows/other: https://stockfishchess.org/download/
```

Then install the game:

```sh
python3 -m venv .venv
./.venv/bin/pip install -e .
```

## Play

```sh
./.venv/bin/python -m chessvania
```

The app looks for Stockfish on your `PATH`, or at `STOCKFISH_PATH` if you set it:

```sh
STOCKFISH_PATH=/opt/homebrew/bin/stockfish ./.venv/bin/python -m chessvania
```

If it can't find one, it exits with install instructions rather than a stack trace.

Terminal should be at least **80×24**.

## The menu

The game opens on a short boot sequence — the banner draws in, a rank of pieces
walks on, the menu appears. **Any key skips it.**

| entry | |
|---|---|
| **new game** | pick an army and a stake, start a fresh run |
| **load game** | resume a run in progress (greyed out if there isn't one) |
| **bestiary** | armies you can field and enemies you've beaten |
| **achievements** | 10 to earn, one of them secret |
| **quit** | |

## Saving

Two files, with two different lifetimes, in your platform's user-data directory
(`~/Library/Application Support/chessvania` on macOS). Override with
`CHESSVANIA_DATA_DIR`.

- **`profile.json`** — achievements, the bestiary and unlocks. Survives everything.
- **`run.json`** — the run in progress. Written at the top of every fight, so
  resuming always puts you at the start of a fight rather than halfway through
  one. **Deleted when the run ends** — one life means a lost run is gone.

Both write atomically, and a corrupt file costs you that save rather than the
ability to launch the game.

## Unlocks

Three armies are available from the start. **Cavalry** unlocks by defeating a
mini-boss and **Endgame** by winning a run — the bestiary shows locked entries
with their condition, so there's something to aim at. Enemies you haven't beaten
appear as `???`, with the tier counts visible so you know how many are left.

## Controls

Everything is driven from the keyboard. The mouse moves the same cursor, so both
work without you having to learn two models.

| key | what it does |
|---|---|
| `↑ ↓ ← →` | move the cursor |
| `enter` / `space` | pick a piece up, then put it down on a destination |
| `esc` | drop the piece you picked up |
| `tab` | switch pane — board, bench, shop controls |
| `ctrl+q` | quit |

Pick a piece up and its legal destinations are marked: a green dot for a quiet
move, a red square for a capture. The cursor is drawn as brackets around the
square it's on, and the inspect panel follows it.

When a pawn reaches the last rank a promotion picker opens — `← →` to choose,
or press `q` / `r` / `b` / `n` directly, then `enter`. It never auto-queens, and
`esc` backs out of the move entirely.

## The threat readout

Because captures are permanent, the question worth answering every move is *what
dies if I ignore this*. The panel under the board answers it, and the board
itself is marked to match.

| mark | | |
|---|---|---|
| `+` | **check** | on a dark red square |
| `!` | **hanging** — attacked with nothing defending it, so it is taken for free and gone for the run | piece tinted red |
| `-` | **losing trade** — defended, but the cheapest attacker is worth less than the piece | piece tinted amber |

Attacked-but-held is deliberately unmarked: it's the normal state of most of a
position, and a board that annotates everything annotates nothing. Every warning
has a glyph as well as a colour, so nothing is lost on a monochrome terminal.

```
THREAT             IN CHECK
+ ♜b1 checks          1 out
! ♖h1 free to ♜h8        -5
- ♘c3 trades down        -2
> ♜b1 is free            +5
```

The right-hand number is material you lose for good. When you're in check it
counts your legal replies instead — *1 out* plays very differently from *12*.
The `>` line is the other direction: the best capture available to you right
now, built from your actual legal moves, so pins and checks are already
accounted for.

Move the cursor and the inspect panel expands whatever it's over — who attacks a
piece, who holds it, whether an enemy piece is guarded, and for an empty square
whether it's covered at all before you step onto it.

It's a static one-ply read, not a search: geometric attackers, cheapest-attacker
trade arithmetic, and pinned defenders discounted. It errs toward warning you,
because over-warning costs a cautious move and under-warning costs a piece for
the rest of the run. The rules live in
[core/threat.py](chessvania/core/threat.py), the appearance in
[ui/theme.py](chessvania/ui/theme.py).

## The rules

**Your army persists.** Pieces carry across the whole run, and anything the enemy
captures is gone permanently. That's the core tension — you are not trying to win
fights, you are trying to win fights *cheaply*.

What persists is a **formation**, not a position. Your pieces always start a fight
on the squares you arranged them on in the swap phase, no matter where the last
fight left them stranded.

**Promotion is tactical, not strategic.** A pawn that queens does so for that
fight only and comes back a pawn — queen to win faster, not to get richer. If the
promoted piece is captured you still lose the pawn for good, so pushing one is a
permanent risk for a temporary gain.

**Gold is paid by move count.** Win in ≤10 moves for 5 gold, ≤20 for 4, ≤30 for 3,
≤45 for 2, anything slower for 1. The live "IF YOU WIN NOW" panel shows the tier
you're currently in, so the pressure is always visible.

**The post-fight phase runs in a fixed order**, shown as a rail on the right:

1. **Payout** — collect your gold, and see which pieces you lost.
2. **Shop** — buy pieces. Every type is always in stock and you can buy as many
   as you like; nothing is rolled and nothing sells out. They go to the **bench**,
   never straight to the board. Skipping without spending banks a bonus onto your
   next payout *and* keeps your gold, so it compounds twice over.

   Three things bound what you can buy: **gold**, the **16-slot bench**, and the
   **3 swaps** you need to actually field a purchase. In practice the board's
   16-piece limit matters most — a full army has nowhere to put anything, so the
   economy is a replacement treadmill: lose pieces, buy replacements, deploy them
   into the gaps.
3. **Sell** — unlocks only once the shop closes, so sale gold can never fund the
   purchase you're standing in front of. It always arrives for the next shop.
4. **Swap** — up to 3 per phase. Since purchases land on the bench, deploying one
   costs a swap. That budget is the tightest constraint in the game.

**Win by checkmate.** Stalemate inverts: whoever gets stalemated *wins*, so
delivering stalemate is a loss and you have to actually mate. Other draws
(repetition, 50-move, dead position) count as a failure to win.

**One life.** Lose a fight and the run is over.

**Veterancy.** Every piece tracks how many fights it has survived, and shades
warmer as it does — fresh, seasoned, veteran. It's cosmetic today, but it's
tracked from the first fight so it can be built on later. Bench pieces don't age;
veterancy is earned on the board.

## Run structure

3 antes × 3 fights (`low → mid → boss`) = 9 fights. Material shape carries the
pulse *within* an ante; Elo carries the climb *between* them, from ~700 up to
~2200. Each ante's floor sits above the previous ante's ceiling, so difficulty
never regresses.

Six stakes form an NG+ ladder, alternating two levers — an economy squeeze
(smaller payouts) and an Elo squeeze (sharper enemy). Each is just a
`{elo_bonus, payout_penalty}` modifier layered over the base ramp, so fight logic
stays stake-agnostic.

### A note on Stockfish strength

Stockfish's `UCI_Elo` bottoms out at **1320**, but the ramp starts at 700. Below
that floor the engine is driven by `Skill Level` (0–20) plus a shallow search
depth instead; above it, by `UCI_LimitStrength` + `UCI_Elo`. The mapping lives in
`config.py` (`strength_for`) and is tunable.

## Layout

```
chessvania/
├── __main__.py         entry point; resolves Stockfish before the TUI starts
├── app.py              Textual App; maps run phases onto screens
├── config.py           every tunable constant
├── core/               PURE LOGIC — never imports Textual or Stockfish
│   ├── legality.py     army legality, mostly via chess.Board.status()
│   ├── army.py         the player's army: deployment, bench, identity, veterancy
│   ├── economy.py      payouts, prices, sale values (ints in, ints out)
│   ├── placement.py    where the enemy stands, given your deployment
│   ├── fight.py        one encounter; the opponent is injected
│   ├── threat.py       what is attacked, framed around permanent loss
│   ├── ladder.py       builds the 9-fight sequence and its Elo ramp
│   ├── postfight.py    payout → shop → sell → swap state machine
│   ├── progress.py     achievements, unlocks, the bestiary record
│   └── run.py          RunState and the phase machine
├── engine/stockfish.py locates the binary, maps Elo onto the right lever
├── persistence/        the only layer that touches a filesystem
│   ├── paths.py        where saves live; atomic, fault-tolerant JSON
│   ├── profile_store.py  profile.json
│   └── run_store.py    run.json, including piece identity
├── data/               enemy formations and loadouts, as FENs
└── ui/                 Textual screens and widgets
```

`core/` never imports Textual or Stockfish. Every rule — the inventory cap, the
swap budget, payout maths, fight resolution — is unit-tested without a terminal or
an engine process.

**Two words, two things.** The player has a **deployment** (`Army.deployment` —
home square to piece, persisting across the run); the enemy has a **formation**
(`ladder.Formation` — an authored FEN with a tier). A fight composes them into one
ordinary chess position and mutates a *copy*, so nothing a fight does leaks back
into your deployment except deaths, which are permanent. The full glossary lives
in [core/\_\_init\_\_.py](chessvania/core/__init__.py).

## Dev mode

A diagnostics mode for debugging and balancing. It is deliberately **not**
reachable from any menu — flip `DEV_MODE` in [config.py](chessvania/config.py),
or run with the environment variable:

```sh
CHESSVANIA_DEV=1 ./.venv/bin/python -m chessvania
```

A status strip appears at the bottom with live state — ante, Elo and which
Stockfish lever is driving it, gold, material on both sides, move count — plus
these shortcuts:

| key | in a fight | post-fight |
|---|---|---|
| `f1` | expand detail (FEN, payout breakdown, stake) | same |
| `f2` | +10 gold | +10 gold |
| `f3` | win the fight instantly | skip the phase, next fight |
| `f4` | lose the fight instantly | — |
| `f5` | remove the enemy piece under the cursor | refill swaps |

`f3` in a fight followed by `f3` in the post-fight phase blitzes through a whole
run, which is the fastest way to reach ante 3 and look at the final bosses.

It is a debugger, not a sandbox: **progression behaves normally while it is on**,
so a run played with dev mode is still a real run. Removing the enemy king is
refused — use `f3` to end a fight.

## Development

```sh
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

The tests inject a scripted opponent, so the whole suite runs without Stockfish
installed. `tests/test_ui.py` boots the real Textual app and drives it with
Textual's pilot, including a check that every control stays on screen at 80×24.

## Balance

None of the numbers are balanced. Payout tiers, prices, the Elo ramp, material
targets and stake modifiers are placeholder scaffolds living in `config.py`, to be
tuned once the game has been played properly.

## Licence

GPL-3.0-or-later — python-chess is GPL-3.0, so this is too.
