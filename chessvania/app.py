"""The Textual app: owns the screen stack and the engine's lifetime.

Flow decisions live in `core.run`, not here. This class only maps a run phase
onto the screen that draws it.
"""

from __future__ import annotations

import random
from typing import List, Optional

from textual.app import App

from . import config
from .core.army import Piece, army_from_fen
from .core.fight import Fight
from .core.ladder import build_ladder
from .core.placement import choose_placement
from .core.postfight import PostFight
from .core.progress import Achievement, Profile, ProgressEvent, evaluate
from .core.run import Phase, RunState, new_run
from .data.enemies import POOLS
from .data.loadouts import Loadout
from .engine import StockfishOpponent
from .persistence import (
    clear_run,
    load_profile,
    load_run,
    save_profile,
    save_run,
)
from .ui.screens.achievements import AchievementsScreen
from .ui.screens.bestiary import BestiaryScreen
from .ui.screens.fight import FightScreen
from .ui.screens.gameover import GameOverScreen
from .ui.screens.menu import MenuScreen
from .ui.screens.postfight import PostFightScreen
from .ui.screens.settings import SettingsScreen


class ChessvaniaApp(App):
    TITLE = "Chessvania"

    CSS = """
    Screen {
        background: #0b0d12;
        color: #c3c8d2;
    }

    #topbar {
        height: 1;
        padding: 0 1;
        background: #0b0d12;
    }

    #main {
        height: 1fr;
        padding: 1 1 0 1;
    }

    /* 17 + 28 + 33 = 78, which fits the 80-column terminal the game targets */
    #left {
        width: 17;
        height: 1fr;
    }

    #center {
        width: 28;
        height: 1fr;
    }

    #right {
        width: 1fr;
        min-width: 25;
        height: 1fr;
    }

    #bench-label {
        height: 1;
        margin-bottom: 1;
    }

    #bench {
        height: 4;
    }

    #bench-note {
        margin-top: 1;
        height: auto;
    }

    #board {
        height: 9;
        width: 28;
    }

    #status {
        margin-top: 1;
        height: auto;
    }

    .panel {
        border: round #1c1f27;
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }

    #logbox {
        height: 1fr;
        min-height: 6;
    }

    #rail {
        height: auto;
        margin-bottom: 0;
    }

    #controls {
        height: auto;
    }

    #controls Button {
        content-align: left middle;
    }

    #devbar {
        dock: bottom;
        height: auto;
        padding: 0 1;
        background: #12151c;
        border-top: solid #1c1f27;
    }

    #controls Button.focused {
        background: #263041;
        color: #e0b24c;
        text-style: bold;
    }

    Button {
        height: 1;
        min-width: 0;
        width: 100%;
        border: none;
        background: #141720;
        color: #c3c8d2;
        text-align: left;
    }

    #controls Button {
        margin-bottom: 0;
    }

    Button:hover {
        background: #1e222c;
    }

    Button:disabled {
        color: #3a3d45;
    }

    #loadout-heading {
        height: auto;
        padding: 1 2;
    }

    #loadout-row {
        height: auto;
        padding: 0 1;
    }

    .loadout-card {
        width: 1fr;
        height: auto;
        border: round #1c1f27;
        padding: 1;
        margin: 0 1;
    }

    .loadout-body {
        height: auto;
        margin-bottom: 1;
    }

    #stake {
        width: 40;
        margin-top: 1;
    }

    #stake-note {
        height: auto;
        padding: 1 2;
    }

    #banner, #march, #menu, #menu-foot, #over-headline, #over-summary {
        height: auto;
    }

    #page-heading {
        height: auto;
        padding: 1 2 0 2;
    }

    #page-body {
        height: 1fr;
        padding: 1 2;
    }

    .page-column {
        width: 1fr;
        height: 1fr;
        padding-right: 2;
    }

    #page-foot {
        height: auto;
        padding: 0 2 1 2;
    }
    """

    def __init__(
        self,
        engine: Optional[StockfishOpponent] = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._owns_engine = engine is None
        self.rng = random.Random(seed)
        self.run_state: Optional[RunState] = None
        self.run_number = 1
        self.profile: Profile = Profile()
        self.fresh_achievements: List[Achievement] = []
        """Earned during the current fight; the post-fight screen announces them."""

    # -- engine ----------------------------------------------------------

    @property
    def engine(self) -> StockfishOpponent:
        if self._engine is None:
            self._engine = StockfishOpponent()
        return self._engine

    def on_mount(self) -> None:
        self.profile = load_profile()
        self.run_number = self.profile.runs_played + 1
        self.apply_settings()
        self.push_screen(MenuScreen(self.profile))

    # -- settings --------------------------------------------------------

    def apply_settings(self) -> None:
        """Push profile preferences into the presentation layer.

        Called once at startup and again on every change, so a toggle takes
        effect on the screen you toggled it from rather than at the next launch.
        """
        from .ui import theme

        theme.set_piece_fill(self.profile.settings.filled_player_pieces)

    def save_settings(self) -> bool:
        """Persist immediately -- the settings screen has no confirm step."""
        return save_profile(self.profile)

    # -- menu ------------------------------------------------------------

    def open_menu(self, animate: bool = True) -> None:
        self.switch_screen(MenuScreen(self.profile, animate=animate))

    def menu_choice(self, choice: str) -> None:
        if choice == "new":
            from .ui.screens.loadout import LoadoutScreen

            self.switch_screen(LoadoutScreen(self.profile))
        elif choice == "load":
            self.resume_run()
        elif choice == "bestiary":
            self.switch_screen(BestiaryScreen(self.profile))
        elif choice == "achievements":
            self.switch_screen(AchievementsScreen(self.profile))
        elif choice == "settings":
            self.switch_screen(SettingsScreen(self.profile))
        elif choice == "quit":
            self.exit()

    def resume_run(self) -> None:
        restored = load_run()
        if restored is None:
            self.open_menu(animate=False)
            return
        self.run_state = restored
        self.run_number = restored.run_number
        self.begin_fight()

    def on_unmount(self) -> None:
        if self._engine is not None and self._owns_engine:
            self._engine.close()
            self._engine = None

    # -- run lifecycle ---------------------------------------------------

    def start_run(self, loadout: Loadout, stake: config.Stake) -> None:
        self.profile.start_run()
        self.run_number = self.profile.runs_played
        save_profile(self.profile)

        army = army_from_fen(loadout.fen)
        ladder = build_ladder(POOLS, stake, self.rng)
        self.run_state = new_run(army, ladder, stake, self.run_number)
        self.begin_fight()

    def begin_fight(self) -> None:
        run = self.run_state
        assert run is not None
        spec = run.current
        if spec is None:
            self.switch_screen(GameOverScreen(run, won=True))
            return

        # Autosave at the top of every fight -- the resume point is always the
        # start of a fight, never halfway through one.
        save_run(run)

        self.engine.configure(spec.elo)
        formation = choose_placement(run.army, spec.formation, POOLS.get(spec.tier, ()))
        fight = Fight(
            army=run.army,
            enemy_fen=formation.fen,
            opponent=self.engine,
            enemy_name=formation.name,
            tier=spec.tier,
            elo=spec.elo,
        )
        self.switch_screen(FightScreen(run, fight))

    def finish_fight(
        self,
        run: RunState,
        fight: Fight,
        casualties: List[Piece],
        won: bool,
    ) -> None:
        if not won:
            run.on_fight_lost(casualties)
            self._record_progress(run, fight, casualties, won=False)
            clear_run()  # one life; there is nothing left to resume
            self.switch_screen(GameOverScreen(run, won=False))
            return

        phase = run.on_fight_won(casualties)
        self._record_progress(run, fight, casualties, won=True,
                              run_won=phase is Phase.VICTORY)

        if phase is Phase.VICTORY:
            clear_run()
            self.switch_screen(GameOverScreen(run, won=True))
            return

        post = PostFight(run, fight.player_moves, casualties)
        self.switch_screen(PostFightScreen(run, post))

    def _record_progress(
        self,
        run: RunState,
        fight: Fight,
        casualties: List[Piece],
        won: bool,
        run_won: bool = False,
    ) -> None:
        """Update the profile from a finished fight and persist it.

        Dev mode deliberately does not suppress any of this -- a forced win is
        still a win, so what you observe while balancing is what a player gets.
        """
        if won:
            self.profile.record_defeat(fight.enemy_name)
        if run_won:
            self.profile.runs_won += 1

        self.fresh_achievements = evaluate(
            ProgressEvent(
                run=run,
                profile=self.profile,
                won_fight=won,
                fight_moves=fight.player_moves,
                casualties=len(casualties),
                enemy=fight.enemy_name,
                tier=fight.tier,
                run_won=run_won,
            )
        )
        save_profile(self.profile)

    def finish_postfight(self, run: RunState) -> None:
        if run.phase is Phase.FIGHT:
            self.begin_fight()
        else:
            clear_run()
            self.switch_screen(GameOverScreen(run, won=True))
