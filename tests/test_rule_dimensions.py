"""Reading and writing measurements — the table is shared with the JS mirror.

kigumi/test-fixtures/dimension-parsing.json is read by this file and by
kigumi/__tests__/dimension-text.test.js, so the two implementations cannot
drift apart without one of them going red.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from kumiki.rule import INCH_TO_METER, format_angle, format_length, parse_angle, parse_length

FIXTURE = json.loads(
    (Path(__file__).resolve().parent.parent / "kigumi" / "test-fixtures" / "dimension-parsing.json")
    .read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", FIXTURE["length"]["valid"], ids=lambda c: c["input"])
def test_a_written_length_reads_back_in_meters(case) -> None:
    assert parse_length(case["input"], case["defaultUnit"]) == pytest.approx(case["meters"])


@pytest.mark.parametrize("case", FIXTURE["length"]["invalid"], ids=lambda c: c["why"])
def test_a_length_that_is_not_a_measurement_is_refused(case) -> None:
    with pytest.raises(ValueError):
        parse_length(case["input"])


@pytest.mark.parametrize("case", FIXTURE["angle"]["valid"], ids=lambda c: c["input"])
def test_a_written_angle_reads_back_in_radians(case) -> None:
    assert parse_angle(case["input"], case["defaultUnit"]) == pytest.approx(case["radians"])


@pytest.mark.parametrize("case", FIXTURE["angle"]["invalid"], ids=lambda c: c["why"])
def test_an_angle_that_is_not_a_measurement_is_refused(case) -> None:
    with pytest.raises(ValueError):
        parse_angle(case["input"])


@pytest.mark.parametrize("case", FIXTURE["formatLength"], ids=lambda c: c["text"])
def test_a_length_is_written_the_way_a_cut_list_would(case) -> None:
    assert format_length(case["meters"], case["unit"]) == case["text"]


@pytest.mark.parametrize("case", FIXTURE["formatAngle"], ids=lambda c: c["text"])
def test_an_angle_is_written_for_people(case) -> None:
    assert format_angle(case["radians"], case["unit"]) == case["text"]


def test_a_decimal_length_round_trips_through_its_own_formatting() -> None:
    """What we write back in a decimal unit has to read as the same measurement."""
    for meters in (0.45, 1.5, 0.0254, 0.03175, 0.9144, 0.0):
        for unit in ("mm", "m", "cm"):
            assert parse_length(format_length(meters, unit)) == pytest.approx(meters, abs=1e-9)


def test_an_imperial_length_comes_back_snapped_to_the_nearest_tick() -> None:
    """A tape measure has 1/32 marks on it, so writing a length in inches is
    lossy by up to half a tick. This is why a value the viewer shows keeps the
    text it was typed with rather than being reformatted and re-read."""
    half_a_tick = INCH_TO_METER / 64
    for meters in (0.45, 1.5, 0.0254, 0.03175, 0.9144, 0.0):
        for unit in ('"', "in"):
            written = parse_length(format_length(meters, unit))
            assert written == pytest.approx(meters, abs=half_a_tick)
    # 450mm is not a round number of thirty-seconds, and says so.
    assert format_length(0.45, '"') == '17 23/32"'
    assert parse_length('17 23/32"') != 0.45


def test_a_fraction_is_a_literal_and_never_arithmetic() -> None:
    """The grammar is closed: nothing typed here is evaluated as an expression."""
    assert parse_length("1/2in") == pytest.approx(0.0127)
    for formula in ("2*3mm", "2+3mm", "__import__('os')", "width/2"):
        with pytest.raises(ValueError):
            parse_length(formula)


def test_an_unknown_default_unit_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_length("10", "furlongs")
    with pytest.raises(ValueError):
        parse_angle("10", "grads")


def test_the_shaku_family_keeps_its_traditional_ratios() -> None:
    assert parse_length("1shaku") == pytest.approx(10 / 33)
    assert parse_length("10sun") == pytest.approx(parse_length("1shaku"))
    assert parse_length("10bu") == pytest.approx(parse_length("1sun"))


def test_degrees_and_radians_agree_at_a_half_turn() -> None:
    assert parse_angle("180deg") == pytest.approx(math.pi)
    assert parse_angle(f"{math.pi}rad") == pytest.approx(math.pi)
