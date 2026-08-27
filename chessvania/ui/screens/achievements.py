"""The achievements list.

Secret achievements hide their name and description until earned, so the list
still has something to reveal; everything else states its condition up front so
it can be aimed at.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...core.progress import ACHIEVEMENTS, Profile
from .. import theme


class AchievementsScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        yield Static(self._heading(), id="page-heading")
        with VerticalScroll(id="page-body"):
            yield Static(self._list(), id="achievement-list")
        yield Static(self._foot(), id="page-foot")

    def _heading(self) -> Text:
        text = Text()
        text.append("ACHIEVEMENTS", style="%s bold" % theme.GOLD)
        text.append("      %s earned" % self.profile.completion, style=theme.DIM)
        return text

    def _list(self) -> Text:
        text = Text()
        for achievement in ACHIEVEMENTS:
            earned = self.profile.has(achievement.id)
            hidden = achievement.secret and not earned

            marker = "✓" if earned else "·"
            text.append(" %s  " % marker,
                        style=theme.GREEN if earned else theme.GHOST)

            if hidden:
                text.append("%-16s" % "???", style=theme.GHOST)
                text.append("a secret\n", style=theme.GHOST)
                continue

            text.append("%-16s" % achievement.name,
                        style="%s bold" % theme.GOLD if earned else theme.TEXT)
            text.append("%s\n" % achievement.blurb,
                        style=theme.FAINT if earned else theme.GHOST)
        return text

    def _foot(self) -> Text:
        text = Text()
        text.append("esc", style=theme.GREEN)
        text.append(" back to the menu", style=theme.DIM)
        return text

    def action_back(self) -> None:
        self.app.open_menu(animate=False)
