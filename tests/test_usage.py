import json
import stat
from pathlib import Path

from tg.usage import analyze_source, append_record, format_report, read_records


def test_analyze_source_redacts_values_and_keeps_operation_shape() -> None:
    first = 'await client.get_messages("secret-chat", limit=100)\n'
    second = 'await client.get_messages("other-chat", limit=50)\n'

    first_shape, first_fingerprint = analyze_source(first)
    second_shape, second_fingerprint = analyze_source(second)

    assert first_shape == second_shape == "client.get_messages(peer, limit)"
    assert first_fingerprint == second_fingerprint
    assert "secret-chat" not in first_shape


def test_append_and_read_records_use_private_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "state" / "usage.jsonl"
    record = {
        "ts": "2026-08-27T12:00:00+00:00",
        "account": "main",
        "source": "stdin",
        "shape": "client.get_me()",
        "fingerprint": "abc",
        "ok": True,
    }

    append_record(record, path)

    assert read_records(path) == [record]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert json.loads(path.read_text()) == record


def test_read_records_skips_partial_or_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "usage.jsonl"
    path.write_text(
        "not json\n"
        '{"account":"main","shape":"client.get_me()","fingerprint":"ok","ok":true}\n'
        '{"account":"main"\n'
    )

    assert read_records(path) == [
        {"account": "main", "shape": "client.get_me()", "fingerprint": "ok", "ok": True}
    ]


def test_format_report_marks_frequent_shapes_as_candidates() -> None:
    records = [
        {"account": "main", "shape": "client.get_me()", "fingerprint": "same", "ok": True}
        for _ in range(5)
    ]

    report = format_report(records)

    assert "Repeated shapes" in report
    assert "5×  client.get_me()" in report
    assert "Possible wrapper candidates (5+ runs)" in report


def test_format_report_can_filter_an_account() -> None:
    records = [
        {"account": "main", "shape": "client.get_me()", "fingerprint": "same", "ok": True},
        {"account": "work", "shape": "client.get_me()", "fingerprint": "same", "ok": True},
    ]

    assert format_report(records, account="main") == "No repeated operations."
