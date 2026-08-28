import asyncio
import sys
from pathlib import Path

import pytest

from tg.cli import execute


def test_execute_supports_top_level_await() -> None:
    namespace = {"asyncio": asyncio, "result": 0}

    asyncio.run(execute("await asyncio.sleep(0)\nresult = 42\n", "<test>", namespace))

    assert namespace["result"] == 42


def test_execute_propagates_script_exceptions() -> None:
    with pytest.raises(RuntimeError, match="boundary"):
        asyncio.run(execute("raise RuntimeError('boundary')", "<test>", {}))


def test_execute_exposes_script_argv_and_local_imports(tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 42\n")
    filename = str(tmp_path / "script.py")
    namespace: dict[str, object] = {}
    previous_argv = sys.argv
    previous_path = sys.path[:]

    asyncio.run(
        execute(
            "import sys\n"
            "from helper import VALUE\n"
            "argv_seen = sys.argv\n"
            "file_seen = __file__\n"
            "value_seen = VALUE\n",
            filename,
            namespace,
            argv=[filename, "one", "--two"],
        )
    )

    assert namespace["argv_seen"] == [filename, "one", "--two"]
    assert namespace["file_seen"] == filename
    assert namespace["value_seen"] == 42
    assert sys.argv is previous_argv
    assert sys.path == previous_path
