"""rule's helpers for numeric code: V3 and friends as numpy floats, and back to an exact scalar."""

import numpy as np

from kumiki.rule import as_floats, create_v3, exact_scalar, unit_floats


def test_a_v3_an_array_and_a_list_are_the_same_three_floats():
    expected = np.array([1.0, 2.0, 3.0])
    for given in (create_v3(1, 2, 3), np.array([1, 2, 3]), [1, 2, 3], (1.0, 2.0, 3.0)):
        assert np.array_equal(as_floats(given), expected)


def test_a_unit_vector_and_a_zero_one_given_a_fallback():
    assert np.allclose(unit_floats(np.array([3.0, 0.0, 4.0])), [0.6, 0.0, 0.8])
    up = np.array([0.0, 0.0, 1.0])
    assert unit_floats(np.zeros(3), up) is up


def test_an_exact_scalar_is_the_float_it_was_given():
    assert float(exact_scalar(0.1)) == 0.1
