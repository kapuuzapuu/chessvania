"""Player preferences.

Deliberately separate from `DEV_MODE`, which is hidden in `config.py` on
purpose. These are the opposite kind of switch: things a player legitimately
wants to change on their fortieth run without editing Python. Nothing here
touches the rules, so nothing here can be used to cheat -- which is exactly why
it can live in a menu.

Every change saves immediately. There is no confirm step and no cancel: a
short preferences screen does not need a transaction, and a setting that
silently failed to persist would be worse than one that applied too eagerly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Union

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...core.progress import Profile
from .. import theme


@dataclass(frozen=True)
class Toggle:
    """A boolean preference, bound to a field on `Settings` by name."""

    id: str
    label: str
    attribute: str
    on_label: str
    off_label: str
    blurb: str

    def value_label(self, settings) -> str:
        return self.on_label if getattr(settings, self.attribute) else self.off_label

    def adjust(self, settings, delta: int) -> None:
        """Either direction flips it; a two-state row has nothing to scroll."""
        setattr(settings, self.attribute, not getattr(settings, self.attribute))


@dataclass(frozen=True)
class Stepper:
    """A numeric preference nudged in fixed steps by the arrow keys."""

    id: str
    label: str
    attribute: str
    blurb: str
    minimum: int = 0
    maximum: int = 100
    step: int = 10
    suffix: str = ""

    def value_label(self, settings) -> str:
        return "%d%s" % (getattr(settings, self.attribute), self.suffix)

    def adjust(self, settings, delta: int) -> None:
        value = getattr(settings, self.attribute) + delta * self.step
        setattr(settings, self.attribute,
                max(self.minimum, min(self.maximum, value)))

    def bar(self, settings, width: int = 10) -> str:
        """A coarse meter, so the number is not the only cue."""
        span = self.maximum - self.minimum or 1
        filled = round((getattr(settings, self.attribute) - self.minimum)
                       / span * width)
        return "█" * filled + "·" * (width - filled)


Row = Union[Toggle, Stepper]

ROWS: List[Row] = [
    Toggle(
        id="audio",
        label="sound",
        attribute="audio",
        on_label="on",
        off_label="off",
        blurb="8-bit effects for moves, captures and menus",
    ),
    Stepper(
        id="volume",
        label="volume",
        attribute="volume",
        blurb="← → to adjust",
        suffix="%",
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
        ("left", "adjust(-1)", "Less"),
        ("right", "adjust(1)", "More"),
        ("enter", "adjust(1)", "Change"),
        ("space", "adjust(1)", "Change"),
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
        settings = self.profile.settings
        text = Text()
        for position, row in enumerate(ROWS):
            selected = position == self.index
            muted = row.id == "volume" and not settings.audio

            text.append("  %s " % ("›" if selected else " "),
                        style=theme.GOLD if selected else theme.GHOST)
            text.append("%-17s" % row.label,
                        style="%s bold" % theme.GOLD if selected else theme.TEXT)

            value_style = theme.GHOST if muted else (
                theme.GREEN if selected else theme.SEASONED)
            text.append("%-10s" % row.value_label(settings), style=value_style)

            if isinstance(row, Stepper):
                text.append("%s  " % row.bar(settings),
                            style=theme.GHOST if muted else theme.GREEN)
            text.append("%s\n" % row.blurb, style=theme.FAINT)

        text.append_text(self._audio_note())
        return text

    def _audio_note(self) -> Text:
        """Say so when the machine simply cannot play anything.

        Otherwise a user on a box with no sound device toggles sound on, hears
        nothing, and concludes the setting is broken.
        """
        text = Text()
        audio = getattr(self.app, "audio", None)
        if audio is not None and not audio.available:
            text.append("\n      no audio backend on this machine — "
                        "sound will stay silent\n", style=theme.RED)
        return text

    def _foot(self) -> Text:
        text = Text()
        text.append("↑↓", style=theme.GREEN)
        text.append(" move · ", style=theme.DIM)
        text.append("←→", style=theme.GREEN)
        text.append(" change · ", style=theme.DIM)
        text.append("esc", style=theme.GREEN)
        text.append(" back · ", style=theme.DIM)
        text.append("saved as you go", style=theme.GHOST)
        return text

    # -- interaction -----------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        self.index = (self.index + delta) % len(ROWS)
        self.app.play_sound("cursor")
        self.redraw()

    def action_adjust(self, delta: int) -> None:
        ROWS[self.index].adjust(self.profile.settings, delta)
        self.app.apply_settings()
        self.app.save_settings()
        # After the change, so toggling sound on is audible immediately and
        # toggling it off is the last thing you hear.
        self.app.play_sound("select")
        self.redraw()

    def action_back(self) -> None:
        self.app.play_sound("back")
        self.app.open_menu(animate=False)
