# THIS .MD FILE IS OLD!!! DO NOT USE!!!

# Chess Roguelike — Build Spec (v1 / minimum playable)

> A terminal chess roguelike. You pilot a persistent army up a ladder of enemy
> formations played by Stockfish at rising Elo. Win a fight → earn **boons** (currency)
> based on how few moves you took → spend them in a shop to **buy pieces** onto your
> board or into your inventory. Captured pieces are gone for good. One life per run.
>
> **This spec is deliberately minimal.** The goal is ONE playable run end-to-end, not a
> balanced or feature-complete game. Balance, content polish, and extra systems come later,
> once the thing is playable. Build the skeleton first.
>
> **At a glance:** Python 3.11+ terminal app. Deps: `python-chess`, `textual` (+ `rich`).
> External: a **Stockfish binary** the app locates at runtime (see §1.1 — not bundled). Run with
> `python -m chessrl` (pick a package name). **For the coding agent:** build strictly in the
> order in §9, and **stop after each step so the user can run and verify it before continuing** —
> do not build ahead.

---

## 0. Golden rule (why this is buildable)

**Every board state is a LEGAL standard-chess position.** Pieces move normally. This means:

- `python-chess` handles all move generation, legality, check, checkmate, stalemate, FEN. Do
  NOT hand-roll chess rules.
- **Stockfish plays the enemy** — feed it the legal position, get a legal move back. Difficulty
  scales via Stockfish's Elo setting.
- There are **no fairy pieces, no piece upgrades, no special abilities, no mid-fight effects.**
  All the roguelike systems (boons, shop, inventory) live in the META layer BETWEEN fights and
  never touch how pieces move.

If a feature would require changing how a piece moves or what "check" means, it is OUT of v1.

---

## 1. Tech stack

- **Python 3.11+**
- **`python-chess`** — chess rules engine (move gen, legality, mate/stalemate, FEN, SAN).
- **Stockfish** — the enemy AI. **Drive it through python-chess's native engine interface**
  (`chess.engine.SimpleEngine.popen_uci(path)`) — do NOT add the separate `stockfish` pip wrapper;
  python-chess talks UCI to the binary directly (one fewer dependency, finer control). Scale
  strength with `UCI_LimitStrength=true` + `UCI_Elo=<n>`.
- **Textual** (+ **Rich**) — terminal UI: screens, board rendering, input.
- **JSON** save file for run state. No database.
- Packaged so it runs with `python -m chessrl` (pick a package name).

### 1.1 Locating the Stockfish binary (do NOT bundle it in v1)

Stockfish is an external **GPL-v3** binary. Bundling it in the repo triggers GPL distribution
obligations (ship license + source pointer) and means committing a separate multi-MB binary per
platform. **Skip all that for v1: the app finds a user-installed binary.**

Resolution order at startup:
1. An explicit path from **config / a `STOCKFISH_PATH` environment variable** (override hook).
2. The **system PATH** (`shutil.which("stockfish")`).

If not found, **exit immediately with a clear, friendly message** — never a stack trace:
```
Stockfish engine not found. Install it, then re-run:
  macOS:   brew install stockfish
  Debian:  sudo apt install stockfish
  Windows/other: download from https://stockfishchess.org/download/
Or set STOCKFISH_PATH=/path/to/stockfish
```
Document this one-time install step in the README. (Bundling for a pure clone-and-play release is
a possible LATER enhancement, not part of v1.)

---

## 2. Core game concepts (READ CAREFULLY — these are the actual rules)

### 2.1 The player's army is PERSISTENT
- The player has a set of pieces that **carries across fights** for the whole run.
- **Pieces captured by the enemy during a fight are GONE permanently.** They do not come back
  next fight. This is the core resource-management tension — you must protect your pieces.
- The player's king is always present (losing the king = losing the fight; see win/lose).

### 2.2 The inventory (bench)
- Separate from the board: an **inventory that holds up to 16 pieces** (hard cap).
- Pieces in the inventory are NOT on the board during a fight — they're reserves.
- Pieces move between board and inventory only during the **swap phase** (see 2.6) and via the
  **shop** (buying a piece can place it on the board or into inventory).
- **Total pieces the player controls at once on the board still obey chess limits**: a legal
  position is ≤16 pieces and ≤8 pawns on the board. The 16-slot inventory is SEPARATE storage.

### 2.3 Boons = the currency
- **Boons are the run's currency** (think "coins/points"), NOT board modifiers. Rename in code
  if clearer (e.g. `currency`), but the design calls them boons.
- You earn boons by winning fights. You spend them in the shop.

### 2.4 Boon payout is based on MOVE COUNT (fewer moves = more boons)
- When the player wins a fight, they earn a number of boons determined by **how many of the
  player's moves it took to win**. Fewer moves → bigger payout.
- Implement as a simple tiered/decreasing function of move count. EXAMPLE (tune later, put in
  config): win in ≤10 moves → 5 boons; ≤20 → 4; ≤30 → 3; ≤45 → 2; else → 1. These numbers are
  placeholders — expose them as constants.

### 2.5 The shop (opens after each win) — BUY PIECES ONLY
- After a win and payout, a **minimal shop** opens.
- The shop sells **individual pieces** for boons. Buying a piece lets the player **place it on
  the board OR save it to the inventory** (if inventory has room / board stays legal).
- **There are NO piece upgrades.** The ONLY thing you buy is pieces. (Piece prices: put in
  config; EXAMPLE placeholder — pawn 1, knight/bishop 3, rook 5, queen 9. Tune later.)
- The shop is **minimal**: a small fixed set of buyable pieces each visit is fine. Don't build
  a complex rotating stock for v1.

### 2.6 Skip-to-compound + sell + swap (the post-fight phase flow)

The post-fight phase, in order:

1. **Payout:** player earns boons based on move count (2.4).
2. **Shop (buy pieces):** player may spend boons buying pieces onto board/inventory (2.5).
   - The player can **SKIP the shop** (a button). If they skip WITHOUT spending, their **next
     payout is increased** (the unspent boons "roll over" and the next win pays even more).
     Implement as: track banked/rollover boons; skipping compounds the next reward. (Exact
     compounding formula → config; EXAMPLE: unspent boons carry over AND next payout gets a
     bonus. Keep simple; tune later.)
3. **Sell (only AFTER closing/skipping the shop):** once the shop is closed, the player may
   **sell pieces from their inventory** for boons. (Sell value in config; EXAMPLE: half buy
   price.) Selling is a separate step that happens after the shop, not inside it.
4. **Swap (reposition, max 3 per post-fight phase):** the player may make up to **3 swaps**.
   A swap is ONE of:
   - swap two pieces with each other (board↔board, board↔inventory, or inventory↔inventory), OR
   - move a piece to an empty square (board→empty board square, board↔empty inventory slot, etc.)
   Each such action counts as one swap; **max 3 total**. All resulting board states must remain
   **legal chess positions** (≤16 pieces, ≤8 pawns, exactly one king, no pawns on rank 1/8, etc.).

After this phase, advance to the next fight with the (possibly modified) persistent army.

### 2.7 One life
- Losing any fight ends the run. No revives in v1.

---

## 3. A fight (encounter)

- The player's persistent **board pieces** vs the enemy formation.
- Player is White, moves first. Enemy (Black) is played by **Stockfish at this fight's Elo**.
- Player enters moves; `python-chess` validates legality.
- **Win:** checkmate the enemy king. (Simplest rule. Optionally also "capture the king" — pick
  ONE and note it; strict checkmate via python-chess is the default.)
- **Lose:** the player's king is checkmated → run over.
- **Stalemate / draw:** define explicitly. v1 default: treat as a LOSS (or a re-fight — pick one
  and put it in config). Don't leave it undefined.
- Track the **player's move count** for the payout.

---

## 4. Run structure, scaling & stakes (PLACEHOLDER NUMBERS — tune after playtesting)

All numbers here are starting scaffolds, NOT balanced values. Put every constant in `config.py`
so they're trivial to change once the game is playable. Do not agonize — real values come from
playing.

### 4.1 Run structure: antes and fights
- A run is **3 antes**. Each ante is **3 fights** in the shape **low → mid → boss**:
  - Antes 1 and 2 end in a **mini-boss**.
  - Ante 3 ends in a **final boss** (the run's climax).
- So a run is **9 fights**: `low mid mini | low mid mini | low mid FINAL`.

### 4.2 Tiers are RELATIVE, not absolute
- `low / mid / boss` describe the **shape of a fight within its ante** (the warmup → real →
  spike pulse), NOT a fixed global difficulty.
- Every ante's difficulty floor rises: **ante N's "low" is harder than ante N-1's boss.** The
  run never regresses — you don't fight a weakling right after beating a mini-boss.
- Mechanism: **material shape** carries the *within-ante* pulse; **Elo** carries the
  *between-ante* climb (see 4.4).

### 4.3 Enemy material targets (relative to the ~24-material player)
Rough per-tier material, for budgeting placeholder formations (tune later):
- low  ≈ 16–20  (player is up material — feel strong)
- mid  ≈ 22–26  (roughly even — a real fight)
- mini-boss ≈ 26–30  (player slightly outgunned)
- final boss ≈ 36–45  (overwhelming; the showpiece)

Material sets the rough shape of an encounter; **Elo does most of the actual difficulty work.**

### 4.4 Base Elo ramp (Stake 1 / base game)
Elo climbs continuously across all 9 fights. Ante boundaries are where it steps into a new band,
and **each ante's floor is above the previous ante's ceiling** so it never regresses. Placeholder:

| Ante | low | mid | boss |
|------|-----|-----|------|
| 1 | ~700  | ~900  | ~1100 (mini) |
| 2 | ~1200 | ~1400 | ~1600 (mini) |
| 3 | ~1700 | ~1900 | ~2200+ (FINAL) |

In code: a per-fight base Elo driven by `(ante, position_in_ante) -> elo`, all in `config.py`.
Lock the Stockfish mapping early — default `UCI_LimitStrength=true` + `UCI_Elo`.

### 4.5 The stake ladder (single ladder — the replay/mastery system)
A **single stake ladder** (NG+ style): each stake is unlocked by winning a run at the previous
stake. A stake applies ONE of two levers on top of the base game; only the highest stakes stack
both. The alternating levers keep the challenge varied (some stakes starve you, some outgun you):

- **Lever A — economy squeeze:** reduce boons earned per win (smaller payouts → fewer pieces →
  thinner army). Difficulty through *scarcity*.
- **Lever B — Elo squeeze:** add a flat bonus to every fight's base Elo (the whole ramp shifts
  up). Difficulty through *the enemy playing sharper*.

Placeholder ladder (tune later):

| Stake | Name (placeholder) | Effect |
|-------|--------------------|--------|
| 1 | Base       | base Elo ramp, normal payouts |
| 2 | Sharpened  | **Lever B:** every fight Elo +150 |
| 3 | Lean       | **Lever A:** payouts −1 tier |
| 4 | Honed      | **Lever B:** every fight Elo +300 |
| 5 | Starved    | **Lever A:** payouts −2 tiers |
| 6 | Merciless  | **Both:** Elo +450 AND payouts −1 tier |

Implementation: a stake is a small modifier `{elo_bonus: int, payout_penalty: int}` layered over
the base ramp and payout tiers. The fight logic stays stake-agnostic — it just receives an
effective Elo and an effective payout function:
```
effective_elo    = base_elo_ramp[ante][position] + stake.elo_bonus
effective_payout = base_payout(move_count) - stake.payout_penalty   # floored at a minimum
```
This keeps the stake system fully decoupled from fight logic and trivially tunable in `config.py`.

---

## 5. Enemy library & pools

Enemy formations are legal positions stored as **FEN** strings (see the project's enemy-library
doc). Each formation is tagged with a **tier**: `low`, `mid`, `mini-boss`, or `final-boss`.

**A run pulls a random subset per tier at rising Elo** (see §4). Each of the 3 antes uses one
`low`, one `mid`, and one boss (`mini-boss` for antes 1–2, `final-boss` for ante 3).

**Pools to author for run-to-run variety** (bigger pool than one run uses = less repetition):
- low: ~6   (run uses 3)
- mid: ~6–8 (run uses 3)
- mini-boss: ~4–5 (run uses 2)
- final boss: ~3–5 (run uses 1) — the "handful of final bosses"

Total ≈ 19–24 formations for a varied game.

**For the FIRST prototype you need far fewer.** One formation per slot (reused across antes, only
the Elo changes) = ~3–4 placeholder formations gets a full 9-fight run playable. You can even use
the **standard chess start** (`rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR`) as a placeholder
enemy to get the fight loop running before wiring any real content. Expand the pools only after
the game is playable and you can feel which enemies are fun.

## 6. Loadouts (starting armies) — PLACEHOLDERS OK

The player picks a starting army. For v1, a single loadout is enough to start; more can be added
later. Each loadout is just a legal starting position (~24 material). Placeholder loadouts exist
in the design notes (e.g. Shield, Speartip); for the first prototype, **even the standard chess
setup is a fine placeholder loadout.** Don't block on loadout design.

---

## 7. Visual design & terminal look

The game is a **terminal app (Textual + Rich)** — installable from GitHub and playable in any
terminal, no browser. A person with only a terminal should be able to clone, run, and play. See
the mockup (`mockup.html`) for the target aesthetic — it's a browser stand-in for the terminal
look, so treat it as a reference for *layout, palette, and interactions*, not for pixel-smooth
animation (terminal animation is cell-based, not sub-pixel).

### 7.1 Layout — four regions
- **Top bar:** left = game title + current enemy name/tier ("the basilisk · mini-boss");
  right = **GOLD**, **RUN #**, **ANTE #/3**, **FIGHT #/3**, current **ELO**. (No HP — you lose
  by being checkmated, not by a health bar.)
- **Left panel — INVENTORY (16 slots):** a 4×4 grid of bench pieces; empty slots shown as
  outlined placeholders; a "swaps left: N" indicator (the 3-swap limit). Core to the game, as
  prominent as the board.
- **Center — the board:** monospace 8×8 cells, chess-piece glyphs, hover-to-inspect.
- **Right panel — MOVES + ECONOMY:**
  - A **live "IF YOU WIN NOW" readout**: current move count, the payout tier it lands in, and the
    resulting boons — with the full tier ladder visible (e.g. ≤10→5, ≤20→4, …) so the player
    *feels* the pressure to win in fewer moves. Show any banked skip/rollover bonus here too.
  - The **move log** below it.
  - An **inspect** box (fills on piece hover: piece type, side, material value).

### 7.2 Interactions to keep (from the mockup)
- **Hover-to-inspect** a piece → shows its identity/value in the inspect box, with a subtle
  outline on the hovered cell. (Textual supports mouse hover.)
- **Capture animation:** cell-based — the moving piece hops square-to-square and the capture
  square flashes. NOT a smooth pixel glide (terminals can't do sub-cell motion; don't promise it).
- **Move / capture highlighting:** the from/to squares tint; captures tint red.

### 7.3 Color & glyph compatibility (graceful degradation)
- **Color enhances, it never carries information alone.** Whose piece is whose is legible from
  **glyph + board position**, not just color — so the game stays fully playable in monochrome.
  Enemy pieces getting a distinct color (e.g. red) is a *treat* for capable terminals, not a
  requirement.
- **Truecolor → 256 → 16 → monochrome:** specify truecolor hex; **Textual auto-downgrades** to
  the nearest available palette. No need to author multiple versions.
- **Chess-piece glyphs need no fallback** — the Unicode chess symbols (♔♕♖♗♘♙ / ♚♛♜♝♞♟) are
  near-universally supported and have been standard for decades. Don't over-engineer an ASCII
  fallback for them.
- **Decorative glyphs stay non-load-bearing.** The only symbol with any real font-support risk is
  the **gold diamond (◇/◆)**. It's kept for now because it looks great — but the *word* "GOLD"
  carries the meaning, so a missing diamond never hides information. **Plan to make the gold
  symbol swappable/configurable later** (fall back to a plain char like `*` or none) rather than
  building a fallback system now.

## 8. Project structure

```
chessrl/
├── __main__.py            # entry point → launches Textual app
├── app.py                 # Textual App; owns screen stack + run lifecycle
│
├── core/                  # PURE LOGIC — no UI, no Stockfish imports. Unit-testable.
│   ├── board.py           # thin helpers over python-chess Board
│   ├── army.py            # persistent army: board pieces + inventory (≤16), legality helpers
│   ├── run.py             # RunState: army, ladder position, boons (+ rollover), rng seed, life
│   ├── economy.py         # payout-by-move-count, shop stock/prices, sell values, rollover logic
│   ├── shop.py            # buy piece → board/inventory; skip→compound; sell (post-close); swaps(≤3)
│   ├── ladder.py          # build a run's fight sequence + per-fight Elo from the enemy library
│   └── fight.py           # one encounter: player vs Stockfish; tracks move count; win/lose/draw
│
├── engine/
│   └── stockfish.py       # locate binary (§1.1) → chess.engine.popen_uci; set Elo; get move; quit
│
├── data/
│   └── enemies.py         # enemy formations as FENs (from the enemy-library doc)
│
├── ui/                    # Textual screens + widgets (presentation only)
│   ├── screens/
│   │   ├── title.py
│   │   ├── loadout.py     # pick starting army
│   │   ├── fight.py       # board + move input + turn loop
│   │   ├── shop.py        # payout → buy pieces → skip/close → sell → swap(≤3)
│   │   ├── victory.py
│   │   └── defeat.py
│   └── widgets/
│       ├── board_view.py  # render a Board via Rich (glyphs, colors, coords)
│       └── move_input.py  # from-to / SAN entry + legal-move highlighting
│
├── config.py              # ALL tunable constants: payout tiers, prices, sell %, rollover,
│                          #   Elo ramp, material targets, swap cap (3), inventory cap (16)
├── persistence/
│   └── save.py            # load/save RunState as JSON
│
└── tests/
    ├── test_army.py       # inventory cap (16); board-legality after buys/swaps
    ├── test_economy.py    # payout scales with move count; rollover compounds on skip
    ├── test_shop.py       # buy places on board/inv; sell only after close; swaps capped at 3
    └── test_fight.py      # win/lose/draw resolution; move-count tracking
```

**Dependency rule:** `core/` never imports Textual or Stockfish. It's plain Python over
python-chess boards. UI and engine depend on core, not the reverse. This keeps every rule
(inventory cap, swap limit, payout math, legality) unit-testable without a running game.

---

## 9. Build order (do these IN ORDER — get to "playable" fast)

1. **Headless fight.** Load a position (use the standard start as placeholder), locate + wire
   Stockfish (§1.1), let the player type moves in plain text (from-to like `e2e4`, or SAN), play
   to checkmate, print win/lose. Track the player's move count.
   *This forces the Stockfish locate + Elo wiring — the one genuinely tricky bit — on day one.*
   No UI yet.
   **Done when:** you can run a script, type legal moves, watch Stockfish reply at a
   *configurable Elo*, and see `you win / you lose in N moves` printed at the end. If Stockfish
   isn't installed, the app exits with the friendly install message from §1.1, not a stack trace.
2. **Economy core (pure, tested).** `economy.py` + `army.py`: payout-by-move-count, boon balance,
   rollover-on-skip, inventory cap (16), swap cap (3), buy/sell affecting board & inventory with
   legality checks. Unit-test all of it headless. No UI.
3. **Board rendering + move input in Textual.** `board_view` + `fight` screen: play one fight in
   the actual TUI.
4. **The shop/post-fight screen.** Payout → buy pieces → skip(compound)/close → sell → swap(≤3).
   Now a WIN leads somewhere and the army changes. This is the core loop closing.
5. **The ladder (3 antes).** Chain 9 fights (low→mid→boss ×3) at the rising Elo ramp (§4.4);
   win/lose screens; one full run start→finish. Stakes (§4.5) can come right after — they're just
   a modifier layered over the ramp and payouts, so add the stake ladder once a base run works.
6. **Everything else later:** more loadouts, real enemy content pass, save/persistence polish,
   balance tuning of ALL the config constants, title/victory/defeat art.

Milestone that matters: **after step 5 you can play one full run.** Only then does balancing the
numbers in `config.py` become a real, answerable activity. Do not balance before you can play.

---

## 10. Open decisions to lock while building (don't discover them late)

1. **Stockfish difficulty mapping:** `UCI_Elo` (default) vs `Skill Level` vs fixed depth. Lock in
   step 1.
2. **Win rule:** strict checkmate (default) vs capture-the-king.
3. **Stalemate rule:** loss (default) vs re-fight vs draw-advance.
4. **Exact payout tiers, piece prices, sell %, rollover/compound formula** — all live in
   `config.py`; pick placeholder values now, tune after step 5.
5. **Run length** (fights per run) and per-fight Elo ramp — `config.py`.