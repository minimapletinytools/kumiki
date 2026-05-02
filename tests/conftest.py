"""
Pytest configuration and fixtures for Kumiki tests.
"""

import pytest
from kumiki.rule import set_numeric_mode, get_numeric_mode


@pytest.fixture
def symbolic_mode():
    """
    Fixture that sets NUMERIC_MODE to 'symbolic' for the duration of the test.
    
    Usage:
        def test_something(symbolic_mode):
            # NUMERIC_MODE is 'symbolic' here
            pass
    """
    original_mode = get_numeric_mode()
    set_numeric_mode("symbolic")
    yield
    # Restore original mode after test
    set_numeric_mode(original_mode)


@pytest.fixture
def float_mode():
    """
    Fixture that ensures NUMERIC_MODE is 'float' for the duration of the test.
    
    Usage:
        def test_something(float_mode):
            # NUMERIC_MODE is 'float' here
            pass
    """
    original_mode = get_numeric_mode()
    set_numeric_mode("float")
    yield
    # Restore original mode after test
    set_numeric_mode(original_mode)


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "symbolic: mark test to run with NUMERIC_MODE='symbolic'"
    )
    config.addinivalue_line(
        "markers", "float_mode: mark test to run with NUMERIC_MODE='float'"
    )


@pytest.fixture(autouse=True)
def reset_numeric_mode_after_each_test():
    """
    Autouse fixture to ensure NUMERIC_MODE is reset to 'float' after each test.
    This prevents test pollution where one test's mode changes affect subsequent tests.
    """
    yield
    # After each test, reset to default 'float' mode
    set_numeric_mode("float")
