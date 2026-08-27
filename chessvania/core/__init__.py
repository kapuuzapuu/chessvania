"""Pure game logic.

Nothing in this package imports Textual or Stockfish. Every rule here -- payout
math, the inventory cap, the swap budget, legality, fight resolution -- is
testable without a terminal or an engine binary.

Vocabulary
----------
Two different things are both "an arrangement of pieces", so they get two
different words and the codebase does not mix them:

  DEPLOYMENT  the player's side. `Army.deployment` maps home square -> piece and
              persists for the whole run. It is where pieces START a fight, not
              where they stand during one; only the swap phase edits it.

  FORMATION   the enemy's side. `ladder.Formation` is an authored FEN with a
              tier. `placement.py` decides which of its variants a given
              deployment can actually be fought against.

A fight composes the two into one ordinary chess position (`army.compose_board`)
and then mutates a copy. Nothing a fight does leaks back into the deployment
except deaths, which are permanent.

Module map
----------
  army        the player's army: pieces, identity, veterancy, the deployment
  legality    position and army rule checks, mostly via chess.Board.status()
  economy     pure arithmetic: payouts, prices, sale values
  placement   choosing where the enemy stands, given a deployment
  ladder      the enemy library's shape: formations, tiers, the 9-fight ramp
  fight       one encounter; the opponent is injected, so no engine import
  threat      a static read of what is attacked, framed around permanent loss
  postfight   the payout -> shop -> sell -> swap phase machine
  run         RunState and the phase machine the app renders
"""
