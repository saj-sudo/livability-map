from __future__ import annotations

import json

import pytest

from pipeline import timing


def test_read_is_empty_without_a_file_or_with_a_corrupt_one(settings):
    assert timing.read(settings) == {}
    (settings.interim_dir / "timings.json").write_text("{not json", encoding="utf-8")
    assert timing.read(settings) == {}


def test_timed_records_the_stage_and_prints_a_line(settings, capsys):
    with timing.timed(settings, "grid"):
        pass
    row = timing.read(settings)["grid"]
    assert row["res"] == [4] and row["bbox"] is None and row["seconds"] >= 0
    assert row["at"].endswith("+00:00")
    assert "grid   took" in capsys.readouterr().out


def test_timed_records_a_failing_stage_and_lets_the_error_through(settings):
    with pytest.raises(ValueError, match="bad"), timing.timed(settings, "pop"):
        raise ValueError("bad")
    assert "pop" in timing.read(settings)


def test_stages_do_not_overwrite_each_other_and_the_file_is_sorted(settings):
    with timing.timed(settings, "pop"):
        pass
    with timing.timed(settings, "admin"):
        pass
    assert set(timing.read(settings)) == {"pop", "admin"}
    text = (settings.interim_dir / "timings.json").read_text(encoding="utf-8")
    assert list(json.loads(text)) == ["admin", "pop"]


def test_max_seconds_keeps_the_slowest_run(settings, monkeypatch):
    clock = iter([0.0, 5.0, 10.0, 11.0, 20.0, 21.0, 30.0, 31.0])  # t0 / end pairs, spare ticks for the rest
    monkeypatch.setattr(timing.time, "time", lambda: next(clock))
    with timing.timed(settings, "grid"):
        pass
    first = timing.read(settings)["grid"]
    with timing.timed(settings, "grid"):
        pass
    second = timing.read(settings)["grid"]
    assert first["seconds"] == 5.0 and first["max_seconds"] == 5.0
    assert second["seconds"] == 1.0 and second["max_seconds"] == 5.0  # the quick rerun keeps the old maximum


def test_peak_rss_is_none_when_it_cannot_be_read(settings, monkeypatch, capsys):
    monkeypatch.setattr(timing, "_peak_rss_bytes", lambda: None)
    with timing.timed(settings, "grid"):
        pass
    assert timing.read(settings)["grid"]["peak_rss_mb"] is None
    assert "peak RSS" not in capsys.readouterr().out


def test_peak_rss_is_reported_in_megabytes(settings, monkeypatch, capsys):
    monkeypatch.setattr(timing, "_peak_rss_bytes", lambda: 2_500_000_000)
    with timing.timed(settings, "grid"):
        pass
    assert timing.read(settings)["grid"]["peak_rss_mb"] == 2500.0
    assert "peak RSS 2.50 GB" in capsys.readouterr().out


def test_peak_rss_prefers_the_windows_peak_and_survives_a_broken_psutil(monkeypatch):
    import psutil

    class Info:
        rss = 100
        peak_wset = 700

    class Proc:
        def memory_info(self):
            return Info()

    monkeypatch.setattr(psutil, "Process", Proc)
    assert timing._peak_rss_bytes() == 700
    Info.peak_wset = 0
    assert timing._peak_rss_bytes() == 100

    def boom():
        raise OSError("no access")

    monkeypatch.setattr(psutil, "Process", boom)
    assert timing._peak_rss_bytes() is None


def test_a_bbox_run_writes_under_its_own_interim_dir(settings):
    settings.bbox = (10.0, 40.0, 12.0, 42.0)
    with timing.timed(settings, "hazards"):
        pass
    assert settings.interim_dir.name.startswith("bbox_")
    assert (settings.interim_dir / "timings.json").exists()
    assert timing.read(settings)["hazards"]["bbox"] == [10.0, 40.0, 12.0, 42.0]
