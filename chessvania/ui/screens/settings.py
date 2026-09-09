"""Player preferences.

Deliberately separate from `DEV_MODE`, which is hidden in `config.py` on
purpose. These are the opposite kind of switch: things a player legitimately
wants to change on their fortieth run without editing Python. Nothing here
touches the rules, so nothing here can be used to cheat -- which is exactly why
it can live in a menu.

Every change saves immediately. There is no confirm step and no cancel: a
two-item preferences screen does not need a transaction, and a setting that
silently failed to persist would be worse than one that applied too eagerly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import chess
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...core.progress import Profile
from .. import theme

PREVIEW_ORDER = (
    chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING,
)


@dataclass(frozen=True)
class Toggle:
    """One boolean preference, bound to a field on `Settings` by name."""

    id: str
    label: str
    attribute: str
    on_label: str
    off_label: str
    blurb: str

    def label_for(self, value: bool) -> str:
        return self.on_label if value else self.off_label


TOGGLES: List[Toggle] = [
    Toggle(
        id="pieces",
        label="piece style",
        attribute="filled_player_pieces",
        on_label="yours filled",
        off_label="yours outlined",
        blurb="which army draws with the solid glyphs",
    ),
    Toggle(
        id="animation",
        label="boot animation",
        attribute="boot_animation",
        on_label="on",
        off_label="off",
        blurb="the title sequence before the menu",
    ),
]


class SettingsScreen(Screen):
    BINDINGS = [
        ("up", "cursor(-1)", "Up"),
        ("down", "cursor(1)", "Down"),
        ("enter", "toggle", "Toggle"),
        ("space", "toggle", "Toggle"),
        ("left", "toggle", "Toggle"),
        ("right", "toggle", "Toggle"),
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile
        self.index = 0

    def compose(self) -> ComposeResult:
        yield Static(self._heading(), id="page-heading")
        with VerticalScroll(id="page-body"):
            yield Static(id="settings-list")
        yield Static(self._foot(), id="page-foot")

    def on_mount(self) -> None:
        self.redraw()

    # -- rendering -------------------------------------------------------

    def _heading(self) -> Text:
        text = Text()
        text.append("SETTINGS", style="%s bold" % theme.GOLD)
        text.append("      cosmetic only · nothing here changes the rules",
                    style=theme.DIM)
        return text

    def redraw(self) -> None:
        self.query_one("#settings-list", Static).update(self._list())

    def _list(self) -> Text:
        text = Text()
        for position, toggle in enumerate(TOGGLES):
            selected = position == self.index
            value = getattr(self.profile.settings, toggle.attribute)

            text.append("  %s " % ("›" if selected else " "),
                        style=theme.GOLD if selected else theme.GHOST)
            text.append("%-17s" % toggle.label,
                        style="%s bold" % theme.GOLD if selected else theme.TEXT)
            text.append("%-16s" % toggle.label_for(value),
                        style=theme.GREEN if selected else theme.SEASONED)
            text.append("%s\n" % toggle.blurb, style=theme.FAINT)

            if toggle.id == "pieces":
                text.append_text(self._preview())
        return text

    def _preview(self) -> Text:
        """Show both armies as they will actually be drawn.

        The point of the setting is a visual one, so describing it in words
        would be the wrong call -- you have to be able to see the swap.
        """
        text = Text("\n      yours  ", style=theme.DIM)
        for piece_type in PREVIEW_ORDER:
            text.append(theme.piece_glyph(piece_type, chess.WHITE),
                        style=theme.SEASONED)
        text.append("      enemy  ", style=theme.DIM)
        for piece_type in PREVIEW_ORDER:
            text.append(theme.piece_glyph(piece_type, chess.BLACK),
                        style=theme.ENEMY_PIECE)
        text.append("\n\n")
        return text

    def _foot(self) -> Text:
        text = Text()
        text.append("↑↓", style=theme.GREEN)
        text.append(" move · ", style=theme.DIM)
        text.append("enter", style=theme.GREEN)
        text.append(" toggle · ", style=theme.DIM)
        text.append("esc", style=theme.GREEN)
        text.append(" back · ", style=theme.DIM)
        text.append("saved as you go", style=theme.GHOST)
        return text

    # -- interaction -----------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        self.index = (self.index + delta) % len(TOGGLES)
        self.redraw()

    def action_toggle(self) -> None:
        toggle = TOGGLES[self.index]
        current = getattr(self.profile.settings, toggle.attribute)
        setattr(self.profile.settings, toggle.attribute, not current)
        self.app.apply_settings()
        self.app.save_settings()
        self.redraw()

    def action_back(self) -> None:
        self.app.open_menu(animate=False)
