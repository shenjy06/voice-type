"""Run the full test suite one file per subprocess to cap memory usage.

pytest-forked relies on os.fork() which is unavailable on Windows, so this
script achieves the same effect by spawning a fresh Python process per test
file.  Each subprocess exits after its file finishes, and the OS reclaims
all memory (module bytecode, linecache, Qt caches) before the next file
starts.  Peak memory stays under ~200 MB instead of ~600 MB for a single
in-process run.

Usage:
    python run_tests.py                  # run all tests
    python run_tests.py tests/test_foo.py  # run a single file
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TEST_DIR = ROOT / "tests"


def _discover_files() -> list[Path]:
    return sorted(p for p in TEST_DIR.rglob("test_*.py") if p.is_file())


def main() -> int:
    files = [Path(f).resolve() for f in sys.argv[1:]] or _discover_files()
    total = len(files)
    width = len(str(total))
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        label = f.relative_to(ROOT).as_posix()
        print(f"[{i:>{width}}/{total}] {label} ...", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(f), "-q", "--tb=short"],
            cwd=str(ROOT),
            timeout=120,
        )
        if result.returncode != 0:
            failures.append(label)
            print(f"  FAIL {label}", flush=True)

    print()
    if failures:
        print(f"{len(failures)} file(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All {total} test files passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
