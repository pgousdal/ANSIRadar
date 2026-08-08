"""Verify embedded-safe imports do not load optional network dependencies."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"


def run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def assert_clean(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr


def test_import_ansiradar_is_network_free() -> None:
    result = run_isolated(
        """
import ansiradar
import sys
assert not any(name in sys.modules for name in ('httpx', 'httpcore', 'anyio'))
"""
    )
    assert_clean(result)


def test_import_mystic_is_network_free() -> None:
    result = run_isolated(
        """
import ansiradar.mystic
import sys
assert not any(name in sys.modules for name in ('httpx', 'httpcore', 'anyio'))
assert 'ansiradar.sources.url' not in sys.modules
"""
    )
    assert_clean(result)


def test_import_source_spec_is_network_free() -> None:
    result = run_isolated(
        """
from ansiradar.sources import SourceSpec
import sys
assert not any(name in sys.modules for name in ('httpx', 'httpcore', 'anyio'))
"""
    )
    assert_clean(result)


def test_build_file_source_is_network_free() -> None:
    result = run_isolated(
        """
from ansiradar.sources import SourceSpec, build_source
import sys
source = build_source(SourceSpec(kind='file', file='aircraft.json'))
assert type(source).__name__ == 'FileSource'
assert not any(name in sys.modules for name in ('httpx', 'httpcore', 'anyio'))
assert 'ansiradar.sources.url' not in sys.modules
"""
    )
    assert_clean(result)


def test_build_url_source_loads_network_backend() -> None:
    result = run_isolated(
        """
from ansiradar.sources import SourceSpec, build_source
import sys
source = build_source(SourceSpec(kind='url', url='https://example.test/aircraft.json'))
assert type(source).__name__ == 'UrlSource'
assert 'httpx' in sys.modules
source.close()
"""
    )
    assert_clean(result)
