from __future__ import annotations

from scripts.run_windows_service import RotatingTextStream


def test_windows_service_log_rotation_is_bounded(tmp_path) -> None:
    path = tmp_path / "service.log"
    stream = RotatingTextStream(path, max_bytes=12, backup_count=2)

    stream.write("12345678")
    stream.write("abcdefgh")
    stream.write("ABCDEFGH")
    stream.flush()

    assert path.read_text(encoding="utf-8") == "ABCDEFGH"
    assert path.with_suffix(".log.1").read_text(encoding="utf-8") == "abcdefgh"
    assert path.with_suffix(".log.2").read_text(encoding="utf-8") == "12345678"
