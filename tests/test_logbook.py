"""Testy dziennika prób (log kompletności)."""

import csv
from pathlib import Path

from src.collector.fetch import Fetchresult
from src.collector.logbook import append_to_logbook


def _make_result(ok=True, observed_at=1788561398, error=None):
    """Pomocnik: tworzy FetchResult do testów."""
    return Fetchresult(
        ok=ok,
        url="https://przyklad.pl/TripUpdates_A.pb",
        observed_at=observed_at,
        status_code=200 if ok else None,
        size_bytes=25510 if ok else None,
        error=error,
        duration_ms=42.0,
    )


def _read_csv(path):
    """Pomocnik: wczytuje CSV jako listę słowników."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_creates_log_with_header(tmp_path):
    """Pierwszy zapis tworzy plik z nagłówkiem i jednym wierszem danych."""
    results = [("trip_updates", "A", _make_result())]
    log_path = append_to_logbook(results, tmp_path)

    assert log_path is not None
    assert log_path.exists()
    assert "date=2026-09-04" in log_path.parts

    rows = _read_csv(log_path)
    assert len(rows) == 1
    assert rows[0]["dataset"] == "trip_updates"
    assert rows[0]["feed"] == "A"
    assert rows[0]["ok"] == "True"


def test_append_does_not_duplicate_header(tmp_path):
    """Dwa zapisy tego samego dnia → jeden nagłówek, dwa wiersze danych."""
    append_to_logbook([("trip_updates", "A", _make_result())], tmp_path)
    append_to_logbook([("vehicle_positions", "A", _make_result())], tmp_path)

    # Znajdujemy plik logu
    log_path = tmp_path / "date=2026-09-04" / "poll_log.csv"

    # Czytamy surowe linie — sprawdzamy, że nagłówek jest tylko raz
    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()

    # 1 nagłówek + 2 wiersze danych = 3 linie
    assert len(lines) == 3
    # nagłówek zaczyna się od "observed_at"
    assert lines[0].startswith("observed_at")
    # druga i trzecia linia to dane, NIE nagłówek
    assert not lines[1].startswith("observed_at")
    assert not lines[2].startswith("observed_at")


def test_logs_errors_too(tmp_path):
    """Log zapisuje też nieudane próby, z treścią błędu."""
    results = [
        ("trip_updates", "A", _make_result(ok=False, error="ConnectTimeout: timeout")),
    ]
    log_path = append_to_logbook(results, tmp_path)

    rows = _read_csv(log_path)
    assert rows[0]["ok"] == "False"
    assert "ConnectTimeout" in rows[0]["error"]


def test_empty_results_returns_none(tmp_path):
    """Pusta lista → None, żaden plik nie powstaje."""
    result = append_to_logbook([], tmp_path)
    assert result is None