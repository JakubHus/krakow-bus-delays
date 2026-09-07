"""Testy zapisu do Parquet"""

import pandas as pd
from pathlib import Path
from src.collector.storage import (
    write_rows_to_parquet,
    build_partition_path,
    save_dataset
)

def test_writes_rows_and_returns_count(tmp_path): # tmp_path jest automatycznie tworzony przez pytest, a później czyszczony
    """Zapisuje wiersze i zwraca ich liczbę"""
    rows = [
        {"trip_id": "A1", "delay": 0},
        {"trip_id": "A2", "delay": 65}
    ]
    target = tmp_path / "test.parquet"

    count = write_rows_to_parquet(rows, target)

    assert count == 2
    assert target.exists() # Sprawdzenie czy plik faktycznie powstał


def test_roundtrip_data_identical(tmp_path):
    """Dane po zapisie i odczycie są takie same (nic nie gubi się podczas zmiany na Parquet i odczytu)"""
    rows = [
        {"trip_id": "A1", "delay": 0, "stop_id": "13065"},
        {"trip_id": "A2", "delay": 65, "stop_id": "11951"}
    ]
    target = tmp_path / "test.parquet"

    write_rows_to_parquet(rows, target)
    back = pd.read_parquet(target)

    assert len(back) == 2
    assert back.iloc[1]["delay"] == 65
    assert back.iloc[1]["stop_id"] == "11951"


def test_empty_rows_writes_nothing(tmp_path):
    """Pusta lista -> nie powstaje plik, zwraca 0"""
    target = tmp_path / "empty.parquet"

    count = write_rows_to_parquet([], target)

    assert count == 0
    assert not target.exists() # Plik nie istnieje, tylko zwracane jest 0


def test_partition_path_structure():
    """Ścieżka ma poprawną strukturę Hive: dataset/date/hour/feed"""
    base = Path("data/raw")
    path = build_partition_path(base, "trip_updates", "A", 1788561398)

    parts = path.parts
    assert "trip_updates" in parts
    assert "date=2026-09-04" in parts
    assert "hour=22" in parts
    assert "feed=A" in parts

def test_partition_path_uses_utc():
    """Godzina wynika z czasu UTC, niezależnie od strefy lokalnej"""
    base = Path("data/raw")
    path = build_partition_path(base, "vehicle_positions", "T", 0)

    assert "date=1970-01-01" in path.parts
    assert "hour=00" in path.parts


def test_partition_path_different_feeds():
    """Ten sam moment, ale różne feedy -> różne foldery feed="""
    base = Path("data/raw")
    path_a = build_partition_path(base, "trip_updates", "A", 1788561398)
    path_t = build_partition_path(base, "trip_updates", "T", 1788561398)

    assert "feed=A" in path_a.parts
    assert "feed=T" in path_t.parts
    assert path_a != path_t


def test_save_dataset_creates_partitioned_file(tmp_path):
    """save_dataset tworzy plik we właściwej partycji i zwraca jego ścieżkę"""
    rows = [{"trip_id": "A1", "arrival_delay": 65}]
    result = save_dataset(rows, tmp_path, "trip_updates", "A", 1788561398)

    assert result is not None
    assert result.exists()

    # Plik jest w oczekiwanej strukturze folderów
    assert "date=2026-09-04" in result.parts
    assert "hour=22" in result.parts
    assert "feed=A" in result.parts

    # Nazwa pliku zaczyna się od "part-" a kończy na ".parquet"
    assert result.name.startswith("part-")
    assert result.name.endswith(".parquet")


def test_save_dataset_roundtrip(tmp_path):
    """Dane zapisane przez save_dataset dają się odczytać bez zmian"""
    rows = [
        {"trip_id": "A1", "arrival_delay": 0, "stop_id": "13065"},
        {"trip_id": "A2", "arrival_delay": 65, "stop_id": "11951"}
    ]
    result = save_dataset(rows, tmp_path, "trip_updates", "A", 1788561398)

    back = pd.read_parquet(result)
    assert len(back) == 2
    assert back.iloc[1]["arrival_delay"] == 65


def test_save_dataset_empty_returns_none(tmp_path):
    """Pusta lista -> None -> żaden plik nie powstaje"""
    result = save_dataset([], tmp_path, "service_alerts", "A", 1788561398)
    assert result is None


def test_save_dataset_no_leftover_tmp_file(tmp_path):
    """Po udanym zapisie nie zostaje żaden plik tymczasowy (.tmp)"""
    rows = [{"trip_id": "A1", "arrival_delay": 65}]
    save_dataset(rows, tmp_path, "trip_updates", "A", 1788561398)

    # Przeszukujemy całe drzewo, nie może być plików .tmp
    tmp_files = list(tmp_path.rglob("*.tmp"))
    assert tmp_files == []