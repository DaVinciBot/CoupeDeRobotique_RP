"""Fail when a word of a yearly theme appears in the core (architecture, section 0).

Usage: theme_words.py [FILE ...]
Without arguments, scans the files tracked by git under CORE_PATHS.
"""

import subprocess
import sys
import unicodedata
from pathlib import Path

# Folded stems (lowercase, no accent), matched as substrings: "stone" also catches pickStones.
# Add the words of each new edition; old editions stay in the repo, so do their words.
# Too generic to be listed: wall/mur, tower/tour, gate/porte, ball, stable, cour.
THEME_WORDS = (
    # cdr_2027
    "pierre",
    "stone",
    "graal",
    "grail",
    "catapult",
    "chateau",
    "castle",
    "rempart",
    "rampart",
    "douve",
    "moat",
    "carriere",
    "quarry",
    "quarries",
    "trone",
    "throne",
    "courtyard",
    "boulet",
    "cannon",
)

# The core is shared between editions: editions/, docs/, config/ and tools/ are not part of it.
CORE_PATHS = ("packages", "dashboard", "firmware", "lidar_driver", "deploy")

REPO_ROOT = Path(__file__).resolve().parents[2]


def fold(text: str) -> str:
    """Lowercase and strip accents, so that "Château" matches "chateau"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def core_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", *CORE_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in listed.split("\0") if name]


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []  # binary file
    hits: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        folded = fold(line)
        hits += [f'{path}:{line_no}: theme word "{word}"' for word in THEME_WORDS if word in folded]
    return hits


def main(argv: list[str]) -> int:
    files = [Path(arg) for arg in argv] or core_files()
    hits = [hit for path in files for hit in scan(path)]
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
