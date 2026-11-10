import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dvb_brain.domain.units import deg_to_rad, m_to_mm, mm_to_m, rad_to_deg

values = st.floats(min_value=-1e4, max_value=1e4)


def test_mm_to_m() -> None:
    assert mm_to_m(1500.0) == pytest.approx(1.5)


def test_m_to_mm() -> None:
    assert m_to_mm(1.5) == pytest.approx(1500.0)


def test_deg_to_rad() -> None:
    assert deg_to_rad(180.0) == pytest.approx(math.pi)
    assert deg_to_rad(-90.0) == pytest.approx(-math.pi / 2)


def test_rad_to_deg() -> None:
    assert rad_to_deg(math.pi) == pytest.approx(180.0)


@given(values)
def test_length_round_trip(value_mm: float) -> None:
    assert m_to_mm(mm_to_m(value_mm)) == pytest.approx(value_mm)


@given(values)
def test_angle_round_trip(value_deg: float) -> None:
    assert rad_to_deg(deg_to_rad(value_deg)) == pytest.approx(value_deg)
