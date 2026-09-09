"""Main menu, with the boot animation that precedes it.

The animation is cell-based on purpose: pieces land square by square rather than
gliding, because that is what a terminal can honestly do. It is skippable with
any key -- nobody wants a title sequence on their fortieth run.
"""

from __future__ import annotations

from typing import List, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Static

from ...core.progress import Profile
from .. import theme

BANNER = [
    "  ___ _  _ ___ ___ ___ _   _   _   _  _ ___ _   ",
    " / __| || | __/ __/ __| \\ / /_\\ | \\| |_ _/ \\  ",
    "| (__| __ | _|\\__ \\__ \\ V / _ \\| .` || | | |  ",
    " \\___|_||_|___|___/___/\\_/_/ \\_\\_|\\_|___\\_/  ",
]

MARCH = "♜♞♝♛♚♝♞♜"
"""The pieces that walk in under the banner during the boot sequence."""

FRAME_SECONDS = 0.07


class MenuItem:
    __slots__ = ("id", "label", "hint", "enabled")

    def __init__(self, id: str, label: str, hint: str, enabled: bool = True) -> None:
        self.id = id
        self.label = label
        self.hint = hint
        self.enabled = enabled


class MenuScreen(Screen):
    """Title, boot animation, and the top-level choices."""

    BINDINGS = [
        ("up", "cursor(-1)", "Up"),
        ("down", "cursor(1)", "Down"),
        ("enter", "select", "Select"),
        ("space", "select", "Select"),
        ("escape", "skip", "Skip"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, profile: Profile, animate: bool = True) -> None:
        super().__init__()
        self.profile = profile
        self.index = 0
        self.frame = 0
        # The caller asks for an animation; the profile decides whether it gets
        # one. Keeping the veto here means no future caller can forget it.
        self.animating = animate and profile.settings.boot_animation
        self._timer = None

    # -- layout ----------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(id="banner")
            with Center():
                yield Static(id="march")
            with Center():
                yield Static(id="menu")
            with Center():
                yield Static(id="menu-foot")

    def on_mount(self) -> None:
        self.items = self._build_items()
        if self.animating:
            self._timer = self.set_interval(FRAME_SECONDS, self._advance)
        else:
            self.frame = self._final_frame()
        self.redraw()

    def _build_items(self) -> List[MenuItem]:
        from ...persistence import has_saved_run

        resumable = has_saved_run()
        return [
            MenuItem("new", "new game", "start a fresh run"),
            MenuItem(
                "load", "load game",
                "resume your run in progress" if resumable else "no run in progress",
                enabled=resumable,
            ),
            MenuItem("bestiary", "bestiary", "armies and enemies you have met"),
            MenuItem("achievements", "achievements",
                     "%s earned" % self.profile.completion),
            MenuItem("settings", "settings", "pieces and presentation"),
            MenuItem("quit", "quit", "leave"),
        ]

    # -- animation -------------------------------------------------------

    def _final_frame(self) -> int:
        return len(BANNER) + len(MARCH) + len(self.items) + 1

    def _advance(self) -> None:
        self.frame += 1
        if self.frame >= self._final_frame():
            self._stop_animation()
        self.redraw()

    def _stop_animation(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.animating = False
        self.frame = self._final_frame()

    def action_skip(self) -> None:
        """Any key jumps to the finished state rather than waiting it out."""
        if self.animating:
            self._stop_animation()
            self.redraw()

    def on_key(self, event) -> None:
        if self.animating:
            self._stop_animation()
            self.redraw()
            event.stop()

    # -- rendering -------------------------------------------------------

    def _visible_counts(self) -> Tuple[int, int, int]:
        """How much of each stage the current frame has revealed."""
        banner = min(len(BANNER), self.frame)
        march = min(len(MARCH), max(0, self.frame - len(BANNER)))
        menu = min(len(self.items), max(0, self.frame - len(BANNER) - len(MARCH)))
        return banner, march, menu

    def redraw(self) -> None:
        banner_rows, march_count, menu_count = self._visible_counts()

        banner = Text()
        for line in BANNER[:banner_rows]:
            banner.append(line + "\n", style=theme.GOLD)
        self.query_one("#banner", Static).update(banner)

        march = Text()
        for glyph in MARCH[:march_count]:
            march.append("%s " % glyph, style=theme.SEASONED)
        self.query_one("#march", Static).update(march)

        self.query_one("#menu", Static).update(self._menu_text(menu_count))
        self.query_one("#menu-foot", Static).update(self._foot(menu_count))

    def _menu_text(self, count: int) -> Text:
        text = Text()
        for position, item in enumerate(self.items[:count]):
            selected = position == self.index and not self.animating
            if not item.enabled:
                style = theme.GHOST
            elif selected:
                style = "%s bold" % theme.GOLD
            else:
                style = theme.TEXT
            text.append("  %s " % ("›" if selected else " "),
                        style=theme.GOLD if selected else theme.GHOST)
            text.append("%-14s" % item.label, style=style)
            text.append("%s\n" % item.hint,
                        style=theme.FAINT if item.enabled else theme.GHOST)
        return text

    def _foot(self, count: int) -> Text:
        if count < len(self.items) or self.animating:
            return Text("")
        text = Text()
        text.append("\n↑↓", style=theme.GREEN)
        text.append(" move · ", style=theme.DIM)
        text.append("enter", style=theme.GREEN)
        text.append(" choose", style=theme.DIM)
        if self.profile.runs_played:
            text.append("      %d run%s · %d won" % (
                self.profile.runs_played,
                "" if self.profile.runs_played == 1 else "s",
                self.profile.runs_won), style=theme.GHOST)
        return text

    # -- interaction -----------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        if self.animating:
            return
        for _ in range(len(self.items)):
            self.index = (self.index + delta) % len(self.items)
            if self.items[self.index].enabled:
                break
        self.redraw()

    def action_select(self) -> None:
        if self.animating:
            self._stop_animation()
            self.redraw()
            return
        item = self.items[self.index]
        if not item.enabled:
            return
        self.app.menu_choice(item.id)

    def action_quit(self) -> None:
        self.app.exit()
