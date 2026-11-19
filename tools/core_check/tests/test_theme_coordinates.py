import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "theme_coordinates.py"

ARENA = {
    "width_mm": 3000,
    "depth_mm": 2000,
    "border_thickness_mm": 22,
    "border_height_mm": 70,
    "aruco_tags": {"blue": [1], "yellow": [6]},
    "zones": [
        {"id": "court", "polygon_mm": [[0, 400], [500, 400], [850, 750], [0, 750]]},
        {"id": "disc", "circle_mm": {"x": 850, "y": 1250, "radius": 100}},
        {"id": "bar", "rect_mm": {"x": 679.3, "y": 570.7, "length": 400, "width": 200}},
        {
            "id": "home",
            "polygon_mm": [[0, 0], [10, 0], [10, 10]],
            "robot_poses": [{"x_mm": 250, "y_mm": 1000, "theta_deg": 0}],
        },
    ],
    "elements": [{"id": "crate", "pose": {"x_mm": 750, "y_mm": 55, "theta_deg": 0}}],
}


def run(tmp_path: Path, line: str) -> subprocess.CompletedProcess[str]:
    arena = tmp_path / "arena.json"
    arena.write_text(json.dumps(ARENA), encoding="utf-8")
    source = tmp_path / "planner.py"
    source.write_text(f"x = 1\n{line}\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--arena", str(arena), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("line", "point"),
    [
        ("target = Vec2(0.85, 0.75)", "(850, 750)"),  # polygon vertex, in m
        ("corner = [500, 400]", "(500, 400)"),  # polygon vertex, in mm
        ("tower = Point(0.85, 1.25)", "(850, 1250)"),  # centre of a circle
        ("wall = (679.3, 570.7)", "(679.3, 570.7)"),  # centre of a rectangle
        ("end = Pose(0.25, 1.0, math.pi)", "(250, 1000)"),  # robot pose
        ("pick = Pose(0.75, 0.055, 0.0)", "(750, 55)"),  # element pose
        ("target = Vec2(x=0.85, y=0.75)", "(850, 750)"),  # keyword arguments
        ('{"x_mm": 850, "y_mm": 750}', "(850, 750)"),  # JSON
    ],
)
def test_theme_coordinate_is_reported_with_file_and_line(
    tmp_path: Path, line: str, point: str
) -> None:
    result = run(tmp_path, line)

    assert result.returncode == 1
    assert f"{tmp_path / 'planner.py'}:2: theme coordinate {point}" in result.stdout


@pytest.mark.parametrize(
    "line",
    [
        "square(0.0, 0.4)",  # (0, 400) is on the edge of the table
        "Vec2(0.5, 0.3)",  # not a point of the table
        "Vec2(0.85, 2, 0.75)",  # not in a row
        "assert angle_diff(0.85, 0.2) == pytest.approx(0.75)",  # not separated by a comma
        "x850, 750",  # part of a name
        "tol = 1e-850, 750",  # part of an exponent
    ],
)
def test_other_numbers_pass(tmp_path: Path, line: str) -> None:
    result = run(tmp_path, line)

    assert (result.returncode, result.stdout) == (0, "")
