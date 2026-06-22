"""Import behavior tests for the stable package surface."""

import subprocess
import sys


def test_quantik_core_import_is_fast_enough_for_library_startup():
    code = (
        "import time; "
        "start = time.perf_counter(); "
        "import quantik_core; "
        "print(time.perf_counter() - start)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert float(completed.stdout.strip()) < 1.0


def test_basic_state_does_not_require_optional_compression_imports():
    code = (
        "import sys; "
        "from quantik_core import State; "
        "State.empty(); "
        "print('zstandard' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "False"
