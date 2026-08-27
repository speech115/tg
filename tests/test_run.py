import asyncio

import pytest

from tg.run import execute


def test_execute_supports_top_level_await() -> None:
    namespace = {"asyncio": asyncio, "result": 0}

    asyncio.run(execute("await asyncio.sleep(0)\nresult = 42\n", "<test>", namespace))

    assert namespace["result"] == 42


def test_execute_propagates_script_exceptions() -> None:
    with pytest.raises(RuntimeError, match="boundary"):
        asyncio.run(execute("raise RuntimeError('boundary')", "<test>", {}))
