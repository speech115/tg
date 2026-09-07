import ast
import asyncio
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from tg.cli import execute


def test_execute_supports_top_level_await() -> None:
    results = []
    code = compile(
        "await asyncio.sleep(0)\nresults.append(42)\n",
        "<stdin>",
        "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )

    asyncio.run(execute(code, {"asyncio": asyncio, "results": results}))

    assert results == [42]


@pytest.mark.parametrize("stdin", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_execute_python_semantics_and_cleanup(monkeypatch, tmp_path: Path, stdin, fails) -> None:
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 42\n")
    sys.modules.pop("helper", None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))])
    filename = "<stdin>" if stdin else str(tmp_path / "script.py")
    argv = ["-" if stdin else filename, "one", "--two"]
    previous_argv = sys.argv
    previous_path = sys.path[:]
    previous_main = sys.modules["__main__"]
    source = (
        "import sys, pickle, __main__\n"
        "from helper import VALUE\n"
        "class Record: pass\n"
        "assert VALUE == 42\n"
        "assert type(pickle.loads(pickle.dumps(Record()))) is Record\n"
        "assert vars(__main__) is globals()\n"
        "assert __name__ == '__main__'\n"
        "assert sys.argv == expected_argv\n"
        "assert __file__ == expected_file\n"
    )
    if fails:
        source += "raise RuntimeError('boundary')\n"
    code = compile(source, filename, "exec")
    expected = pytest.raises(RuntimeError, match="boundary") if fails else nullcontext()

    try:
        with expected:
            asyncio.run(
                execute(code, {"expected_argv": argv, "expected_file": filename}, argv=argv)
            )
    finally:
        sys.modules.pop("helper", None)

    assert sys.argv is previous_argv
    assert sys.path == previous_path
    assert sys.modules["__main__"] is previous_main
