"""Hidden tests for the example calculator task.

Copied into /home/root/tests/ at Docker build time — the agent cannot see these.
"""

import sys
import subprocess

sys.path.insert(0, "/home/ubuntu/workspace")


def test_add():
    from calc import add
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_sub():
    from calc import sub
    assert sub(5, 3) == 2
    assert sub(0, 0) == 0


def test_mul():
    from calc import mul
    assert mul(3, 4) == 12
    assert mul(-2, 5) == -10
    assert mul(0, 100) == 0


def test_div():
    from calc import div
    assert div(10, 2) == 5.0
    assert div(7, 3) == pytest.approx(2.333333)


def test_div_by_zero():
    import pytest as _pytest
    from calc import div
    with _pytest.raises(ZeroDivisionError):
        div(1, 0)


def test_evaluate():
    from calc import evaluate
    assert evaluate("3 + 4") == 7.0
    assert evaluate("10 / 3") == pytest.approx(3.333333)
    assert evaluate("6 * 7") == 42.0


def test_cli():
    result = subprocess.run(
        [sys.executable, "/home/ubuntu/workspace/calc.py", "3", "+", "4"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert float(result.stdout.strip()) == 7.0


import pytest  # noqa: E402
