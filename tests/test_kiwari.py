"""What a frame is proportioned from, and what it will refuse to be."""
from __future__ import annotations

import warnings
from enum import Enum

import pytest

from kumiki.kiwari import Kiwari, kiwari
from kumiki.rule import create_v2, create_v3, degrees, inches, mm
from kumiki.timber import Frame, TimberEnd


class Finish(Enum):
    ROUGH_SAWN = 1
    HAND_PLANED = 2


def a_kiwari() -> Kiwari:
    return kiwari(
        legs=kiwari.count(4, minimum=3, maximum=12, about="Number of legs"),
        seat_height=kiwari.length(mm(450)),
        splay=kiwari.angle(degrees(10)),
        waste=kiwari.number(0.1),
        pegged=kiwari.flag(True),
        label=kiwari.text("stool"),
        butt_end=kiwari.choice(TimberEnd, TimberEnd.TOP),
        size=kiwari.point2(create_v2(inches(2), inches(4))),
        origin=kiwari.point3(create_v3(0.0, 0.0, 0.0)),
    )


# --- reading -----------------------------------------------------------------


def test_a_bare_kiwari_reads_its_own_defaults() -> None:
    k = a_kiwari()
    assert k.count("legs") == 4
    assert k.length("seat_height") == pytest.approx(0.45)
    assert k.angle("splay") == pytest.approx(degrees(10))
    assert k.number("waste") == pytest.approx(0.1)
    assert k.flag("pegged") is True
    assert k.text("label") == "stool"
    assert k.choice("butt_end") is TimberEnd.TOP
    assert k.v2("size")[0] == pytest.approx(inches(2))
    assert k.v3("origin")[2] == pytest.approx(0.0)


def test_asking_for_the_wrong_kind_says_so_at_the_call_site() -> None:
    k = a_kiwari()
    with pytest.raises(TypeError, match="'legs' is a count, not a length"):
        k.length("legs")
    with pytest.raises(TypeError, match="Read it with .count()"):
        k.number("legs")


def test_asking_for_a_key_that_is_not_declared_lists_the_ones_that_are() -> None:
    k = a_kiwari()
    with pytest.raises(KeyError) as caught:
        k.length("seat_heigth")
    assert "legs" in str(caught.value) and "seat_height" in str(caught.value)


def test_a_choice_can_be_asked_to_confirm_which_enum_it_chooses_from() -> None:
    k = a_kiwari()
    assert k.choice("butt_end", TimberEnd) is TimberEnd.TOP
    with pytest.raises(TypeError, match="chooses from TimberEnd"):
        k.choice("butt_end", Finish)


# --- binding -----------------------------------------------------------------


def test_resolving_none_leaves_the_defaults_alone() -> None:
    k = a_kiwari()
    assert k.resolve(None) is k


def test_resolving_a_mapping_lays_values_over_the_defaults() -> None:
    k = a_kiwari().resolve({"legs": 6, "pegged": False})
    assert k.count("legs") == 6
    assert k.flag("pegged") is False
    assert k.length("seat_height") == pytest.approx(0.45)  # untouched


def test_resolving_takes_text_and_reads_it_as_a_measurement() -> None:
    k = a_kiwari().resolve({"seat_height": '18"', "splay": "30deg"})
    assert k.length("seat_height") == pytest.approx(inches(18))
    assert k.angle("splay") == pytest.approx(degrees(30))


def test_a_value_keeps_the_text_it_was_typed_with() -> None:
    k = a_kiwari().resolve({"seat_height": {"value": inches(1.25), "text": '1 1/4"'}})
    assert k.written("seat_height") == '1 1/4"'
    assert k.value_payload("seat_height")["text"] == '1 1/4"'


def test_resolving_merges_over_what_is_already_bound_not_over_the_defaults() -> None:
    """The runner lays one changed value onto the kiwari it already holds."""
    held = a_kiwari().resolve({"legs": 6, "seat_height": inches(20)})
    after = held.resolve({"legs": 8})
    assert after.count("legs") == 8
    assert after.length("seat_height") == pytest.approx(inches(20))


def test_resolving_against_another_kiwari_takes_its_values() -> None:
    incoming = a_kiwari().resolve({"legs": 5})
    assert a_kiwari().resolve(incoming).count("legs") == 5


def test_a_declaration_made_fresh_this_run_wins_over_a_stale_value() -> None:
    """Editing the file while the viewer is open: the new declaration governs."""
    was = kiwari(legs=kiwari.count(4), rails=kiwari.count(2)).resolve({"legs": 6, "rails": 3})
    now = kiwari(legs=kiwari.count(4))  # the author deleted 'rails'
    with pytest.warns(UserWarning, match="rails"):
        resolved = now.resolve(was)
    assert resolved.count("legs") == 6
    with pytest.raises(KeyError):
        resolved.count("rails")


def test_resolving_refuses_something_that_is_not_values_at_all() -> None:
    with pytest.raises(TypeError):
        a_kiwari().resolve(["legs", 6])


# --- what a value is allowed to be -------------------------------------------


def test_a_count_must_be_whole_and_within_its_bounds() -> None:
    with pytest.raises(ValueError, match="whole number"):
        a_kiwari().resolve({"legs": 4.5})
    with pytest.raises(ValueError, match="at least 3"):
        a_kiwari().resolve({"legs": 2})
    with pytest.raises(ValueError, match="at most 12"):
        a_kiwari().resolve({"legs": 13})
    assert a_kiwari().resolve({"legs": 6.0}).count("legs") == 6


def test_a_measurement_that_does_not_read_as_one_is_refused() -> None:
    with pytest.raises(ValueError):
        a_kiwari().resolve({"seat_height": "about yea high"})
    with pytest.raises(ValueError):
        a_kiwari().resolve({"splay": "30grads"})


def test_a_flag_takes_the_words_a_checkbox_sends() -> None:
    for yes in (True, 1, "true", "on", "YES"):
        assert a_kiwari().resolve({"pegged": yes}).flag("pegged") is True
    for no in (False, 0, "false", "off", "NO"):
        assert a_kiwari().resolve({"pegged": no}).flag("pegged") is False
    with pytest.raises(ValueError, match="on or off"):
        a_kiwari().resolve({"pegged": "maybe"})


def test_a_choice_comes_back_as_the_real_enum_member() -> None:
    k = a_kiwari().resolve({"butt_end": "BOTTOM"})
    assert k.choice("butt_end") is TimberEnd.BOTTOM
    assert isinstance(k.choice("butt_end"), TimberEnd)
    with pytest.raises(ValueError, match="must be one of"):
        a_kiwari().resolve({"butt_end": "SIDEWAYS"})


def test_a_point_takes_the_shapes_the_viewer_and_python_both_send() -> None:
    for sent in ({"x": "10mm", "y": "20mm", "z": "30mm"}, ["10mm", "20mm", "30mm"],
                 create_v3(0.01, 0.02, 0.03)):
        origin = a_kiwari().resolve({"origin": sent}).v3("origin")
        assert origin[0] == pytest.approx(0.01)
        assert origin[2] == pytest.approx(0.03)
    with pytest.raises(ValueError, match="needs 3 numbers"):
        a_kiwari().resolve({"origin": [1, 2]})
    with pytest.raises(ValueError, match="missing z"):
        a_kiwari().resolve({"origin": {"x": 1, "y": 2}})


def test_nothing_is_allowed_only_where_the_declaration_says_so() -> None:
    with pytest.raises(ValueError, match="not allowed to be nothing"):
        a_kiwari().resolve({"seat_height": None})
    optional = kiwari(trim=kiwari.length(mm(10), optional=True))
    assert optional.resolve({"trim": None}).length("trim") is None


def test_a_parameter_with_no_default_has_nothing_to_build_with() -> None:
    with pytest.raises(ValueError, match="nothing to build with"):
        kiwari.length(None)
    assert kiwari.length(None, optional=True).default is None


def test_a_default_that_is_not_what_it_claims_fails_where_it_was_written() -> None:
    with pytest.raises(ValueError):
        kiwari(legs=kiwari.count("four"))
    with pytest.raises(ValueError, match="at least 3"):
        kiwari(legs=kiwari.count(1, minimum=3))


def test_a_declaration_has_to_be_one() -> None:
    with pytest.raises(TypeError, match="must be declared with"):
        kiwari(legs=4)


def test_a_choice_must_name_an_enum() -> None:
    with pytest.raises(ValueError, match="Enum"):
        kiwari.choice(str)


def test_a_choice_with_no_default_takes_the_first_member_declared() -> None:
    assert kiwari(finish=kiwari.choice(Finish)).choice("finish") is Finish.ROUGH_SAWN


# --- describing --------------------------------------------------------------


def test_only_the_values_that_differ_from_the_code_count_as_changed() -> None:
    k = a_kiwari()
    assert k.changed_from_defaults() == ()
    assert k.resolve({"legs": 4}).changed_from_defaults() == ()
    assert k.resolve({"legs": 6}).changed_from_defaults() == ("legs",)
    both = k.resolve({"legs": 6, "pegged": False}).changed_from_defaults()
    assert set(both) == {"legs", "pegged"}


def test_a_point_that_was_not_touched_is_not_reported_as_changed() -> None:
    k = a_kiwari().resolve({"origin": create_v3(0.0, 0.0, 0.0)})
    assert k.changed_from_defaults() == ()


def test_the_payload_carries_the_schema_the_values_and_what_changed() -> None:
    payload = a_kiwari().resolve({"legs": 6}).to_payload()
    keys = [entry["key"] for entry in payload["schema"]]
    assert keys[0] == "legs" and "butt_end" in keys
    legs = payload["schema"][0]
    assert legs["kind"] == "count" and legs["minimum"] == 3 and legs["about"] == "Number of legs"
    assert payload["applied"]["legs"] == {"value": 6}
    assert payload["applied"]["seat_height"]["text"] == "450mm"
    assert payload["changed"] == ["legs"]


def test_the_payload_names_an_enums_members_for_a_dropdown() -> None:
    entry = next(e for e in a_kiwari().to_payload()["schema"] if e["key"] == "butt_end")
    assert {"value": "TOP", "label": "Top"} in entry["choices"]
    assert entry["default"] == {"value": "TOP"}


def test_the_payload_is_json() -> None:
    import json
    json.dumps(a_kiwari().resolve({"legs": 6}).to_payload())


# --- on the frame ------------------------------------------------------------


def test_a_frame_carries_what_it_was_built_from() -> None:
    k = a_kiwari().resolve({"legs": 6})
    frame = Frame(cut_timbers=[], kiwari=k)
    assert frame.kiwari.count("legs") == 6


def test_a_frame_without_parameters_carries_no_kiwari() -> None:
    assert Frame(cut_timbers=[]).kiwari is None


def test_a_kiwari_is_immutable_and_resolving_makes_a_new_one() -> None:
    k = a_kiwari()
    after = k.resolve({"legs": 6})
    assert k.count("legs") == 4 and after.count("legs") == 6
    with pytest.raises(Exception):
        k.values["legs"] = 9  # type: ignore[index]
