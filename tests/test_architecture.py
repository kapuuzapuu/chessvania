"""The dependency rule, enforced.

`core/` must stay free of Textual and Stockfish. Everything else in the design
leans on this: it is why the rules are testable without a terminal or an engine
binary, and why the UI can be rewritten without touching game logic.
"""

import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parent.parent / "chessvania" / "core"
FORBIDDEN = ("textual", "rich", "chessvania.engine", "chess.engine")


def imported_modules(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            # level>0 is a relative import; reconstruct enough to spot `engine`
            yield ("." * node.level) + (node.module or "")


def test_core_is_pure():
    offenders = []
    for path in sorted(CORE.glob("*.py")):
        for module in imported_modules(path):
            bare = module.lstrip(".")
            if bare.startswith(("textual", "rich")) or "engine" in bare:
                offenders.append("%s imports %s" % (path.name, module))
    assert not offenders, "core must not depend on UI or engine: %s" % offenders


def test_core_modules_exist():
    expected = {
        "army.py", "economy.py", "fight.py", "ladder.py",
        "legality.py", "placement.py", "postfight.py", "run.py",
        "threat.py",
    }
    assert expected <= {p.name for p in CORE.glob("*.py")}


def test_the_two_arrangement_words_stay_apart():
    """`deployment` is the player's, `formation` is the enemy's.

    The old name for the player's squares was `board_pieces`, which read as a
    live position and caused a real bug. If it comes back, so does the
    confusion.
    """
    offenders = [
        path.name for path in CORE.glob("*.py")
        if "board_pieces" in path.read_text()
    ]
    assert not offenders, "player squares are `deployment`, not `board_pieces`: %s" % offenders


def test_the_glossary_is_present():
    """core/__init__ is where a new reader learns the vocabulary."""
    doc = (CORE / "__init__.py").read_text()
    assert "DEPLOYMENT" in doc and "FORMATION" in doc
