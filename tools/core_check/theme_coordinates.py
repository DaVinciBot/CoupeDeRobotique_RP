"""Fail when a coordinate of a yearly table appears in the core (architecture, section 0).

Usage: theme_coordinates.py [--arena ARENA_JSON]... [FILE ...]
Without --arena, reads every editions/*/arena.json. Without files, scans the files tracked by
git under the core paths (see theme_words.py).

The coordinates are the points of the arena files, in mm: polygon vertices, centres of circles
and rectangles, poses. Points on the edge of the table, such as (0, 400), are too common to be
searched. Two numbers separated by a comma, and maybe a field name, that give such a point in mm
or in m are reported: "0.85, 0.75", "x=850, y=750", '"x_mm": 850, "y_mm": 750'.
"""

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

from theme_words import REPO_ROOT, core_files

type Point = tuple[float, float]

# A number that is not part of a name or a version: "0.75" and "1e-9", but not "x2".
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
# What separates the x and the y of a point.
SEPARATOR = re.compile(r"""\s*,\s*(?:["']?\w+["']?\s*[:=]\s*)?""")


def key(x: float, y: float) -> Point:
    return (round(x, 1), round(y, 1))


def arena_points(path: Path) -> set[Point]:
    arena: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    points: list[tuple[float, float]] = []
    for zone in arena["zones"]:
        points += [(x, y) for x, y in zone.get("polygon_mm", [])]
        points += [(zone[s]["x"], zone[s]["y"]) for s in ("circle_mm", "rect_mm") if s in zone]
        points += [(pose["x_mm"], pose["y_mm"]) for pose in zone.get("robot_poses", [])]
    points += [(element["pose"]["x_mm"], element["pose"]["y_mm"]) for element in arena["elements"]]
    width, depth = arena["width_mm"], arena["depth_mm"]
    return {key(x, y) for x, y in points if 0 < x < width and 0 < y < depth}


def text(point: Point) -> str:
    return "(" + ", ".join(f"{v:g}" for v in point) + ")"


def scan(path: Path, points: set[Point]) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []  # binary file
    hits: list[str] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        for first, second in itertools.pairwise(NUMBER.finditer(line)):
            if not SEPARATOR.fullmatch(line, first.end(), second.start()):
                continue
            a, b = float(first.group()), float(second.group())
            found = {key(a * scale, b * scale) for scale in (1.0, 1000.0)} & points  # mm or m
            hits += [f"{path}:{line_no}: theme coordinate {text(point)}" for point in found]
    return hits


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arena", type=Path, action="append", default=[])
    parser.add_argument("files", type=Path, nargs="*")
    args = parser.parse_args(argv)
    arenas: list[Path] = args.arena or sorted(REPO_ROOT.glob("editions/*/arena.json"))
    files: list[Path] = args.files or core_files()
    points = set[Point]().union(*(arena_points(arena) for arena in arenas))
    hits = [hit for path in files for hit in scan(path, points)]
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
