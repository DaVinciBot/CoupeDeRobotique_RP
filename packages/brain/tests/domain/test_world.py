import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shapely import box

from dvb_brain.domain.geometry import Pose, Vec2, angle_diff
from dvb_brain.domain.remote_vision import MarkerObservation, RemoteObservations
from dvb_brain.domain.world import (
    Construction,
    ElementState,
    Observed,
    PoseHistory,
    Source,
    Track,
    TrackSet,
    Velocity,
    WorldLifetimes,
    WorldModel,
)

LIFETIMES = WorldLifetimes(lidar_tracks=0.3, remote=0.3, element_seen=2.0, odometry_history=2.0)
ELEMENTS = ("a", "b")
T0 = 10.0  # s, creation of the world model

IN_PLACE = ElementState(
    present=True, taken=False, placed_at=None, carried_by_us=False, confidence=1.0
)
CARRIED = ElementState(
    present=False, taken=True, placed_at=None, carried_by_us=True, confidence=1.0
)
GONE = ElementState(present=False, taken=True, placed_at=None, carried_by_us=False, confidence=0.8)


def world() -> WorldModel:
    return WorldModel(ELEMENTS, LIFETIMES, T0)


def track(track_id: int, x: float) -> Track:
    return Track(id=track_id, center=Vec2(x, 1.0), radius=0.2, velocity=Vec2(0, 0), confirmed=True)


def observations(stamp: float) -> RemoteObservations:
    return RemoteObservations(stamp=stamp, markers=(MarkerObservation(3, Pose(1, 1, 0)),))


def assert_pose(actual: Pose | None, expected: Pose) -> None:
    assert actual is not None
    assert actual.x == pytest.approx(expected.x)
    assert actual.y == pytest.approx(expected.y)
    assert actual.theta == pytest.approx(expected.theta)


# Observed


def test_observed_age_is_the_time_since_the_measurement() -> None:
    observed = Observed(value=1, stamp=2.0, source=Source.LIDAR)

    assert observed.age(2.5) == pytest.approx(0.5)


@pytest.mark.parametrize(("now", "fresh"), [(2.0, True), (2.5, True), (2.51, False)])
def test_observed_is_fresh_up_to_its_lifetime_included(now: float, fresh: bool) -> None:
    observed = Observed(value=1, stamp=2.0, source=Source.LIDAR)

    assert observed.is_fresh(now, 0.5) is fresh


# PoseHistory


def history_with(*points: tuple[float, Pose]) -> PoseHistory:
    history = PoseHistory(window=2.0)
    for stamp, pose in points:
        history.add(stamp, pose)
    return history


def test_pose_at_a_sample_gives_that_sample() -> None:
    history = history_with((1.0, Pose(0, 0, 0)), (1.1, Pose(1, 2, 0.5)))

    assert history.pose_at(1.1) == Pose(1, 2, 0.5)


def test_pose_at_interpolates_between_the_two_samples_around() -> None:
    history = history_with((1.0, Pose(0, 0, 0)), (2.0, Pose(1, 2, 1.0)), (3.0, Pose(5, 5, 1.0)))

    assert_pose(history.pose_at(1.25), Pose(0.25, 0.5, 0.25))


def test_pose_at_turns_the_short_way_across_pi() -> None:
    history = history_with((1.0, Pose(0, 0, math.pi - 0.1)), (2.0, Pose(0, 0, -math.pi + 0.1)))

    assert_pose(history.pose_at(1.5), Pose(0, 0, math.pi))


@pytest.mark.parametrize("t", [0.99, 2.01])
def test_pose_at_is_none_outside_the_history(t: float) -> None:
    history = history_with((1.0, Pose(0, 0, 0)), (2.0, Pose(1, 0, 0)))

    assert history.pose_at(t) is None


def test_pose_at_is_none_for_an_empty_history() -> None:
    assert PoseHistory(window=2.0).pose_at(1.0) is None


def test_history_forgets_samples_older_than_its_window() -> None:
    history = history_with(
        (1.0, Pose(0, 0, 0)), (2.0, Pose(1, 0, 0)), (3.5, Pose(2, 0, 0)), (4.5, Pose(3, 0, 0))
    )

    assert history.pose_at(1.5) is None
    assert_pose(history.pose_at(2.0), Pose(1, 0, 0))


def test_history_covers_its_whole_window() -> None:
    history = history_with((1.0, Pose(0, 0, 0)), (3.5, Pose(2.5, 0, 0)))

    assert_pose(history.pose_at(1.5), Pose(0.5, 0, 0))


coords = st.floats(min_value=-10.0, max_value=10.0)
headings = st.floats(min_value=-math.pi, max_value=math.pi)
poses = st.builds(Pose, coords, coords, headings)


@given(poses, poses, st.floats(min_value=0.0, max_value=1.0))
def test_pose_at_stays_between_its_two_samples(p0: Pose, p1: Pose, r: float) -> None:
    pose = history_with((1.0, p0), (2.0, p1)).pose_at(1.0 + r)

    assert pose is not None
    assert min(p0.x, p1.x) - 1e-9 <= pose.x <= max(p0.x, p1.x) + 1e-9
    assert min(p0.y, p1.y) - 1e-9 <= pose.y <= max(p0.y, p1.y) + 1e-9
    assert abs(angle_diff(pose.theta, p0.theta)) <= abs(angle_diff(p1.theta, p0.theta)) + 1e-9


def test_a_sample_at_the_same_time_replaces_the_last_one() -> None:
    history = history_with((1.0, Pose(0, 0, 0)), (2.0, Pose(1, 0, 0)), (2.0, Pose(3, 0, 0)))

    assert_pose(history.pose_at(1.5), Pose(1.5, 0, 0))


def test_a_sample_older_than_the_last_one_is_refused() -> None:
    history = history_with((2.0, Pose(0, 0, 0)))

    with pytest.raises(ValueError, match="older"):
        history.add(1.0, Pose(1, 0, 0))


# WorldModel and WorldSnapshot


def test_new_world_has_every_element_in_place_from_the_config() -> None:
    snapshot = world().snapshot(T0)

    assert set(snapshot.our_elements) == set(ELEMENTS)
    for element_id in ELEMENTS:
        assert snapshot.element(element_id) == Observed(IN_PLACE, T0, Source.CONFIG)
    assert snapshot.carrying == frozenset()


def test_new_world_has_no_measurement() -> None:
    snapshot = world().snapshot(T0)

    assert snapshot.t == T0
    assert snapshot.robot_pose is None
    assert snapshot.robot_velocity is None
    assert snapshot.opponents == ()
    assert snapshot.remote is None
    assert not snapshot.lidar_alive
    assert not snapshot.remote_alive
    assert snapshot.our_constructions == {}


def test_odometry_gives_the_pose_the_velocity_and_the_history() -> None:
    model = world()
    model.update_odometry(Pose(1, 1, 0), Velocity(0.2, 0.0), stamp=11.0)
    model.update_odometry(Pose(2, 1, 0), Velocity(0.3, 0.1), stamp=12.0)

    snapshot = model.snapshot(12.0)

    assert snapshot.robot_pose == Observed(Pose(2, 1, 0), 12.0, Source.ODOMETRY)
    assert snapshot.robot_velocity == Observed(Velocity(0.3, 0.1), 12.0, Source.ODOMETRY)
    assert_pose(model.pose_at(11.5), Pose(1.5, 1, 0))


def test_odometry_history_lasts_the_configured_window() -> None:
    model = world()
    model.update_odometry(Pose(0, 0, 0), Velocity(0, 0), stamp=11.0)
    model.update_odometry(Pose(0.2, 0, 0), Velocity(0, 0), stamp=11.2)
    model.update_odometry(Pose(2.5, 0, 0), Velocity(0, 0), stamp=13.5)

    assert model.pose_at(11.0) is None
    assert model.pose_at(11.5) is not None


def test_an_odometry_measurement_older_than_the_last_one_is_ignored() -> None:
    model = world()
    model.update_odometry(Pose(1, 1, 0), Velocity(0.2, 0), stamp=12.0)
    model.update_odometry(Pose(0, 0, 0), Velocity(0, 0), stamp=11.9)

    snapshot = model.snapshot(12.0)

    assert snapshot.robot_pose == Observed(Pose(1, 1, 0), 12.0, Source.ODOMETRY)
    assert snapshot.robot_velocity == Observed(Velocity(0.2, 0), 12.0, Source.ODOMETRY)
    assert model.pose_at(12.0) == Pose(1, 1, 0)


def test_opponents_are_the_tracks_of_the_last_scan() -> None:
    model = world()
    model.update_tracks(TrackSet(stamp=11.0, tracks=(track(1, 0.5),)))
    model.update_tracks(TrackSet(stamp=11.1, tracks=(track(2, 1.5), track(3, 2.5))))

    snapshot = model.snapshot(11.1)

    assert snapshot.opponents == (
        Observed(track(2, 1.5), 11.1, Source.LIDAR),
        Observed(track(3, 2.5), 11.1, Source.LIDAR),
    )


@pytest.mark.parametrize(("now", "alive"), [(11.0, True), (11.29, True), (11.31, False)])
def test_lidar_is_alive_while_its_last_scan_is_fresh(now: float, alive: bool) -> None:
    model = world()
    model.update_tracks(TrackSet(stamp=11.0, tracks=()))

    assert model.snapshot(now).lidar_alive is alive


@pytest.mark.parametrize(("now", "alive"), [(11.0, True), (11.29, True), (11.31, False)])
def test_remote_is_alive_while_its_last_picture_is_fresh(now: float, alive: bool) -> None:
    model = world()
    model.update_remote(observations(11.0))

    snapshot = model.snapshot(now)

    assert snapshot.remote_alive is alive
    assert snapshot.remote == Observed(observations(11.0), 11.0, Source.REMOTE)


def test_stale_opponents_are_kept_with_their_stamp() -> None:
    model = world()
    model.update_tracks(TrackSet(stamp=11.0, tracks=(track(1, 0.5),)))

    snapshot = model.snapshot(12.0)

    assert not snapshot.lidar_alive
    assert snapshot.opponents[0].age(snapshot.t) == pytest.approx(1.0)


def test_our_element_state_comes_from_the_strategy() -> None:
    model = world()
    model.mark_element("a", CARRIED, stamp=12.0, source=Source.STRATEGY)

    snapshot = model.snapshot(12.0)

    assert snapshot.element("a") == Observed(CARRIED, 12.0, Source.STRATEGY)
    assert snapshot.carrying == frozenset({"a"})


def test_carrying_ends_when_the_element_is_put_down() -> None:
    model = world()
    model.mark_element("a", CARRIED, stamp=12.0, source=Source.STRATEGY)
    placed = ElementState(
        present=False, taken=True, placed_at=Pose(1, 1, 0), carried_by_us=False, confidence=1.0
    )
    model.mark_element("a", placed, stamp=13.0, source=Source.STRATEGY)

    assert model.snapshot(13.0).carrying == frozenset()


def test_a_fresh_remote_view_newer_than_our_state_wins() -> None:
    model = world()
    model.mark_element("a", GONE, stamp=12.0, source=Source.REMOTE)

    snapshot = model.snapshot(13.0)

    assert snapshot.element("a") == Observed(GONE, 12.0, Source.REMOTE)
    assert snapshot.our_elements["a"].source is Source.CONFIG
    assert snapshot.carrying == frozenset()


PLACED = ElementState(
    present=False, taken=True, placed_at=Pose(1, 1, 0), carried_by_us=False, confidence=1.0
)


@pytest.mark.parametrize("ours", [CARRIED, PLACED])
def test_a_remote_view_keeps_what_only_our_robot_knows(ours: ElementState) -> None:
    model = world()
    model.mark_element("a", ours, stamp=12.0, source=Source.STRATEGY)
    model.mark_element("a", GONE, stamp=12.5, source=Source.REMOTE)

    element = model.snapshot(13.0).element("a")

    assert (element.stamp, element.source) == (12.5, Source.REMOTE)
    assert element.value.confidence == GONE.confidence
    assert element.value.carried_by_us == ours.carried_by_us
    assert element.value.placed_at == ours.placed_at


def test_a_remote_view_older_than_our_state_does_not_win() -> None:
    model = world()
    model.mark_element("a", CARRIED, stamp=12.0, source=Source.STRATEGY)
    model.mark_element("a", GONE, stamp=11.9, source=Source.REMOTE)

    assert model.snapshot(12.0).element("a").value == CARRIED


def test_a_stale_remote_view_gives_way_to_our_state() -> None:
    model = world()
    model.mark_element("a", GONE, stamp=12.0, source=Source.REMOTE)

    snapshot = model.snapshot(14.01)

    assert snapshot.element("a") == Observed(IN_PLACE, T0, Source.CONFIG)
    assert snapshot.seen_elements["a"].value == GONE


def test_an_unknown_element_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown element"):
        world().mark_element("z", GONE, stamp=12.0, source=Source.STRATEGY)


def test_a_construction_is_replaced_by_one_with_the_same_id() -> None:
    model = world()
    model.add_construction(Construction("wall", box(1, 1, 1.2, 1.4)), stamp=12.0)
    bigger = Construction("wall", box(1, 1, 1.2, 1.8))
    model.add_construction(bigger, stamp=13.0)

    assert model.snapshot(13.0).our_constructions == {
        "wall": Observed(bigger, 13.0, Source.STRATEGY)
    }


def test_constructions_are_the_same_object_until_one_is_added() -> None:
    model = world()
    model.add_construction(Construction("wall", box(1, 1, 1.2, 1.4)), stamp=12.0)
    before = model.snapshot(12.0).our_constructions

    model.update_odometry(Pose(1, 1, 0), Velocity(0, 0), stamp=12.1)
    model.update_tracks(TrackSet(stamp=12.1, tracks=()))
    model.mark_element("a", CARRIED, stamp=12.1, source=Source.STRATEGY)

    assert model.snapshot(12.1).our_constructions is before


def test_a_snapshot_never_changes_after_an_update() -> None:
    model = world()
    model.update_odometry(Pose(1, 1, 0), Velocity(0.1, 0), stamp=11.0)
    model.update_tracks(TrackSet(stamp=11.0, tracks=(track(1, 0.5),)))
    model.update_remote(observations(11.0))
    snapshot = model.snapshot(11.0)
    copy = (
        snapshot.robot_pose,
        snapshot.robot_velocity,
        snapshot.opponents,
        dict(snapshot.our_elements),
        dict(snapshot.seen_elements),
        dict(snapshot.our_constructions),
        snapshot.carrying,
        snapshot.remote,
    )

    model.update_odometry(Pose(2, 1, 0), Velocity(0.2, 0), stamp=12.0)
    model.update_tracks(TrackSet(stamp=12.0, tracks=(track(2, 2.5),)))
    model.update_remote(observations(12.0))
    model.mark_element("a", CARRIED, stamp=12.0, source=Source.STRATEGY)
    model.mark_element("b", GONE, stamp=12.0, source=Source.REMOTE)
    model.add_construction(Construction("wall", box(1, 1, 1.2, 1.4)), stamp=12.0)

    assert (
        snapshot.robot_pose,
        snapshot.robot_velocity,
        snapshot.opponents,
        dict(snapshot.our_elements),
        dict(snapshot.seen_elements),
        dict(snapshot.our_constructions),
        snapshot.carrying,
        snapshot.remote,
    ) == copy


def test_snapshot_collections_are_read_only() -> None:
    snapshot = world().snapshot(T0)

    with pytest.raises(TypeError):
        snapshot.our_elements["a"] = Observed(GONE, T0, Source.STRATEGY)  # type: ignore[index]
