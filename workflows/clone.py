"""Run with: tg workflows/clone.py init|sync|refresh|roster SOURCE [options]."""

from tg.clone import main

await main(client)  # noqa: F704, F821 - injected by tg
