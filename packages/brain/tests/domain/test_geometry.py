import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dvb_brain.domain.geometry import (
    Pose,
    Vec2,
    angle_diff,
    normalize_angle,
    shortest_rotation,
)

angles = st.floats(min_value=-100.0, max_value=100.0)
coords = st.floats(min_value=-10.0, max_value=10.0)
vecs = st.builds(Vec2, coords, coords)
poses = st.builds(Pose, coords, coords, angles)


@pytest.mark.parametrize(
    ("angle", "expected"),
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (math.pi, math.pi),
        (-math.pi, math.pi),
        (3 * math.pi, math.pi),
        (-math.pi / 2, -math.pi / 2),
        (2 * math.pi + 0.5, 0.5),
        (-2 * math.pi - 0.5, -0.5),
    ],
)
def test_normalize_angle_wraps_into_half_open_interval(angle: float, expected: float) -> None:
    assert normalize_angle(angle) == pytest.approx(expected)


@given(angles)
def test_normalize_angle_result_is_in_range(angle: float) -> None:
    assert -math.pi < normalize_angle(angle) <= math.pi


@given(angles)
def test_normalize_angle_is_idempotent(angle: float) -> None:
    once = normalize_angle(angle)
    assert normalize_angle(once) == once


def test_angle_diff_is_first_minus_second() -> None:
    assert angle_diff(0.5, 0.2) == pytest.approx(0.3)
    assert angle_diff(0.2, 0.5) == pytest.approx(-0.3)


def test_angle_diff_wraps_across_pi() -> None:
    assert angle_diff(math.pi - 0.1, -math.pi + 0.1) == pytest.approx(-0.2)


def test_shortest_rotation_goes_from_first_to_second() -> None:
    assert shortest_rotation(0.2, 0.5) == pytest.approx(0.3)
    assert shortest_rotation(0.5, 0.2) == pytest.approx(-0.3)


def test_shortest_rotation_takes_the_short_way_across_pi() -> None:
    assert shortest_rotation(math.pi - 0.1, -math.pi + 0.1) == pytest.approx(0.2)


def assert_vec_close(actual: Vec2, expected: Vec2) -> None:
    assert actual.x == pytest.approx(expected.x, abs=1e-9)
    assert actual.y == pytest.approx(expected.y, abs=1e-9)


def test_vec2_is_immutable() -> None:
    v = Vec2(1.0, 2.0)
    with pytest.raises(AttributeError):
        v.x = 3.0  # type: ignore[misc]


def test_vec2_add_and_sub() -> None:
    assert Vec2(1.0, 2.0) + Vec2(0.5, -1.0) == Vec2(1.5, 1.0)
    assert Vec2(1.0, 2.0) - Vec2(0.5, -1.0) == Vec2(0.5, 3.0)


def test_vec2_scales_by_a_scalar_on_either_side() -> None:
    assert Vec2(1.0, -2.0) * 2.0 == Vec2(2.0, -4.0)
    assert 2.0 * Vec2(1.0, -2.0) == Vec2(2.0, -4.0)


def test_vec2_norm() -> None:
    assert Vec2(3.0, 4.0).norm() == pytest.approx(5.0)


def test_vec2_dot() -> None:
    assert Vec2(1.0, 2.0).dot(Vec2(3.0, 4.0)) == pytest.approx(11.0)
    assert Vec2(1.0, 0.0).dot(Vec2(0.0, 1.0)) == 0.0


def test_vec2_cross_is_positive_when_other_is_counter_clockwise() -> None:
    assert Vec2(1.0, 0.0).cross(Vec2(0.0, 1.0)) == pytest.approx(1.0)
    assert Vec2(0.0, 1.0).cross(Vec2(1.0, 0.0)) == pytest.approx(-1.0)


def test_vec2_rotate_is_counter_clockwise() -> None:
    assert_vec_close(Vec2(1.0, 0.0).rotate(math.pi / 2), Vec2(0.0, 1.0))
    assert_vec_close(Vec2(0.0, 2.0).rotate(math.pi / 2), Vec2(-2.0, 0.0))


def test_vec2_angle() -> None:
    assert Vec2(1.0, 0.0).angle() == 0.0
    assert Vec2(0.0, 1.0).angle() == pytest.approx(math.pi / 2)
    assert Vec2(-1.0, 0.0).angle() == pytest.approx(math.pi)
    assert Vec2(0.0, -1.0).angle() == pytest.approx(-math.pi / 2)


def test_pose_position() -> None:
    assert Pose(1.0, 2.0, 0.3).position == Vec2(1.0, 2.0)


def test_pose_heading_vector_is_the_unit_vector_along_theta() -> None:
    assert_vec_close(Pose(1.0, 2.0, 0.0).heading_vector, Vec2(1.0, 0.0))
    assert_vec_close(Pose(1.0, 2.0, math.pi / 2).heading_vector, Vec2(0.0, 1.0))


def test_pose_to_world_maps_a_robot_frame_point_onto_the_table() -> None:
    pose = Pose(1.0, 2.0, math.pi / 2)
    assert_vec_close(pose.to_world(Vec2(0.5, 0.0)), Vec2(1.0, 2.5))
    assert_vec_close(pose.to_world(Vec2(0.0, 0.5)), Vec2(0.5, 2.0))


def test_pose_to_local_maps_a_table_point_into_the_robot_frame() -> None:
    pose = Pose(1.0, 2.0, math.pi / 2)
    assert_vec_close(pose.to_local(Vec2(1.0, 2.5)), Vec2(0.5, 0.0))


def test_pose_compose_applies_other_in_self_frame() -> None:
    result = Pose(1.0, 2.0, math.pi / 2).compose(Pose(0.5, 0.0, math.pi / 4))
    assert_vec_close(result.position, Vec2(1.0, 2.5))
    assert result.theta == pytest.approx(3 * math.pi / 4)


def test_pose_compose_normalizes_theta() -> None:
    result = Pose(0.0, 0.0, 3.0).compose(Pose(0.0, 0.0, 3.0))
    assert result.theta == pytest.approx(6.0 - 2 * math.pi)


@given(poses)
def test_pose_composed_with_its_inverse_is_identity(pose: Pose) -> None:
    for result in (pose.compose(pose.inverse()), pose.inverse().compose(pose)):
        assert_vec_close(result.position, Vec2(0.0, 0.0))
        assert angle_diff(result.theta, 0.0) == pytest.approx(0.0, abs=1e-9)


@given(poses, vecs)
def test_pose_to_world_undoes_to_local(pose: Pose, point: Vec2) -> None:
    assert_vec_close(pose.to_world(pose.to_local(point)), point)
