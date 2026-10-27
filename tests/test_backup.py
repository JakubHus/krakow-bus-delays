"""Testy logiki backupu"""

import pytest
from unittest.mock import patch, MagicMock
from src.collector.backup import (
    parse_date_folders,
    days_to_delete,
    archive_contains_date,
    verify_backup_covers_days,
    plan_deletion,
    DeletionPlan,
    list_server_dates,
    list_archive_contents,
    delete_server_day,
    run_cleanup
)


# --- parse_date_folders ---

def test_parse_extracts_dates():
    """Wyłuskuje daty z nazw folderów"""
    folders = ["date=2026-10-20", "date=2026-10-21", "date=2026-10-19"]
    assert parse_date_folders(folders) == ["2026-10-19", "2026-10-20", "2026-10-21"]


def test_parse_ignores_non_date_folders():
    """Ignoruje nazwy, które nie są date=YYYY-MM-DD"""
    folders = ["date=2026-10-20", "cokolwiek", "date=smieci", "feed=A"]
    assert parse_date_folders(folders) == ["2026-10-20"]


def test_parse_empty_list():
    """Pusta lista -> pusta lista"""
    assert parse_date_folders([]) == []


# --- days_to_delete ---

def test_delete_keeps_last_n():
    """Zostawia ostatnie N dni, resztę oddaje do usunięcia"""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]
    # zostaw ostatnie 2 -> usuń pierwsze 3
    assert days_to_delete(dates, keep_last_n=2) == ["2026-10-01", "2026-10-02", "2026-10-03"]


def test_delete_returns_oldest_first():
    """Do usunięcia idą najstarsze dni"""
    dates = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    result = days_to_delete(dates, keep_last_n=2)
    assert result == ["2026-10-20", "2026-10-21"]


def test_delete_nothing_when_too_few_days():
    """Mniej dni niż bufor -> nie usuwa nic"""
    dates = ["2026-10-25", "2026-10-26"]
    assert days_to_delete(dates, keep_last_n=7) == []


def test_delete_nothing_when_exactly_buffer():
    """Dokładnie tyle dni co bufor -> nie usuwa nic"""
    dates = ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert days_to_delete(dates, keep_last_n=3) == []


def test_delete_one_when_buffer_plus_one():
    """Bufor + 1 dzień -> usuwa dokładnie najstarszy"""
    dates = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    assert days_to_delete(dates, keep_last_n=3) == ["2026-10-20"]


def test_delete_negative_buffer_raises():
    """Ujemny bufor -> błąd"""
    with pytest.raises(ValueError):
        days_to_delete(["2026-10-20"], keep_last_n=-1)


def test_delete_empty_dates():
    """Brak dni -> nic do usunięcia"""
    assert days_to_delete([], keep_last_n=7) == []


# --- archive_contains_date ---

def test_archive_contains_existing_date():
    """Dzień obecny w archiwum → True."""
    paths = [
        "data/raw/trip_updates/date=2026-10-19/hour=07/feed=A/part.parquet",
        "data/raw/vehicle_positions/date=2026-10-19/hour=07/feed=A/part.parquet",
    ]
    assert archive_contains_date(paths, "2026-10-19") is True


def test_archive_missing_date():
    """Dzień nieobecny w archiwum → False."""
    paths = ["data/raw/trip_updates/date=2026-10-19/hour=07/feed=A/part.parquet"]
    assert archive_contains_date(paths, "2026-10-20") is False


def test_archive_ignores_static_only():
    """Dzień tylko w static (nie raw) → False (interesują nas dane surowe)."""
    paths = ["data/static/GTFS_KRK_A_abc123.zip"]
    assert archive_contains_date(paths, "2026-10-19") is False


# --- verify_backup_covers_days ---

def test_verify_all_days_present():
    """Wszystkie dni w archiwum → (True, [])."""
    paths = [
        "data/raw/trip_updates/date=2026-10-18/h/f/part.parquet",
        "data/raw/trip_updates/date=2026-10-19/h/f/part.parquet",
    ]
    ok, missing = verify_backup_covers_days(paths, ["2026-10-18", "2026-10-19"])
    assert ok is True
    assert missing == []


def test_verify_detects_missing_day():
    """BEZPIECZNIK: brakujący dzień → (False, [brakujący])."""
    paths = ["data/raw/trip_updates/date=2026-10-18/h/f/part.parquet"]
    ok, missing = verify_backup_covers_days(paths, ["2026-10-18", "2026-10-19"])
    assert ok is False
    assert missing == ["2026-10-19"]


def test_verify_empty_archive_all_missing():
    """BEZPIECZNIK: puste archiwum, a chcemy usuwać → wszystko brakuje, blokada."""
    ok, missing = verify_backup_covers_days([], ["2026-10-18", "2026-10-19"])
    assert ok is False
    assert missing == ["2026-10-18", "2026-10-19"]


def test_verify_no_days_to_check():
    """Brak dni do sprawdzenia → (True, []) — nie ma czego weryfikować."""
    ok, missing = verify_backup_covers_days(["cokolwiek"], [])
    assert ok is True
    assert missing == []


# --- plan_deletion ---

def _archive_with_days(days):
    """Pomocnik: buduje ścieżki archiwum zawierające podane dni."""
    return [f"data/raw/trip_updates/date={d}/hour=07/feed=A/part.parquet" for d in days]


def test_plan_blocks_when_backup_failed():
    """BEZPIECZNIK 1: backup zawiódł → zablokowane, nic do usunięcia."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03"]
    plan = plan_deletion(dates, archive_paths=[], keep_last_n=1, backup_ok=False)
    assert plan.allowed is False
    assert plan.to_delete == []
    assert "Backup" in plan.reason


def test_plan_blocks_when_nothing_old():
    """BEZPIECZNIK 2: brak starych dni → zablokowane (łagodnie)."""
    dates = ["2026-10-25", "2026-10-26"]
    plan = plan_deletion(dates, _archive_with_days(dates), keep_last_n=7, backup_ok=True)
    assert plan.allowed is False
    assert plan.to_delete == []


def test_plan_blocks_when_day_missing_from_backup():
    """BEZPIECZNIK 3: dzień do usunięcia NIE jest w backupie → zablokowane."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03"]
    # archiwum zawiera tylko 10-02 i 10-03, brakuje 10-01
    archive = _archive_with_days(["2026-10-02", "2026-10-03"])
    plan = plan_deletion(dates, archive, keep_last_n=1, backup_ok=True)
    assert plan.allowed is False
    assert "2026-10-01" in plan.reason


def test_plan_allows_when_all_safe():
    """Wszystkie bezpieczniki OK → usuwanie dozwolone, właściwe dni."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    archive = _archive_with_days(dates)  # wszystko w backupie
    plan = plan_deletion(dates, archive, keep_last_n=2, backup_ok=True)
    assert plan.allowed is True
    assert plan.to_delete == ["2026-10-01", "2026-10-02"]  # dwa najstarsze


def test_plan_allows_only_verified_days():
    """Usuwa tylko dni faktycznie w backupie, zostawia bufor."""
    dates = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]
    archive = _archive_with_days(dates)
    plan = plan_deletion(dates, archive, keep_last_n=3, backup_ok=True)
    assert plan.allowed is True
    assert plan.to_delete == ["2026-10-20", "2026-10-21"]
    # ostatnie 3 (22,23,24) NIE są na liście do usunięcia
    assert "2026-10-24" not in plan.to_delete


# --- funkcje wykonawcze ---

def test_list_server_dates_parses_output():
    """Odczyt dni z serwera parsuje wynik ls."""
    fake = MagicMock(returncode=0, stdout="date=2026-10-20\ndate=2026-10-21\n", stderr="")
    with patch("src.collector.backup.subprocess.run", return_value=fake):
        dates = list_server_dates("user@host", "/opt/ztp-collector/data")
    assert dates == ["2026-10-20", "2026-10-21"]


def test_list_server_dates_raises_on_ssh_error():
    """Błąd SSH → RuntimeError (głośny, nie ciche zero dni)."""
    fake = MagicMock(returncode=255, stdout="", stderr="connection refused")
    with patch("src.collector.backup.subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError):
            list_server_dates("user@host", "/opt/ztp-collector/data")


def test_list_archive_contents_splits_lines():
    """Listowanie archiwum zwraca ścieżki jako listę."""
    fake = MagicMock(returncode=0, stdout="data/\ndata/raw/\ndata/raw/trip_updates/\n", stderr="")
    with patch("src.collector.backup.subprocess.run", return_value=fake):
        paths = list_archive_contents("/d/backup.tar.gz")
    assert "data/raw/" in paths


def test_list_archive_raises_on_corrupt():
    """Uszkodzone archiwum → RuntimeError."""
    fake = MagicMock(returncode=2, stdout="", stderr="unexpected EOF")
    with patch("src.collector.backup.subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError):
            list_archive_contents("/d/broken.tar.gz")


def test_delete_server_day_calls_ssh():
    """Usuwanie dnia wywołuje właściwą komendę SSH."""
    fake = MagicMock(returncode=0, stdout="", stderr="")
    with patch("src.collector.backup.subprocess.run", return_value=fake) as mock_run:
        delete_server_day("user@host", "/opt/ztp-collector/data", "2026-10-01")
    # sprawdzamy, że komenda zawiera usunięcie właściwego dnia
    called_cmd = mock_run.call_args[0][0]
    assert "date=2026-10-01" in called_cmd[2]
    assert "rm -rf" in called_cmd[2]


def test_delete_server_day_raises_on_error():
    """Błąd usuwania → RuntimeError."""
    fake = MagicMock(returncode=1, stdout="", stderr="permission denied")
    with patch("src.collector.backup.subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError):
            delete_server_day("user@host", "/opt/ztp-collector/data", "2026-10-01")


# --- run_cleanup ---

def _patch_executors(server_dates, archive_days):
    """
    Pomocnik: podstawia wyniki odczytu serwera i archiwum.
    Zwraca context managerów do użycia w teście.
    """
    archive_paths = [f"data/raw/trip_updates/date={d}/h/f/part.parquet" for d in archive_days]
    return (
        patch("src.collector.backup.list_server_dates", return_value=server_dates),
        patch("src.collector.backup.list_archive_contents", return_value=archive_paths),
    )


def test_dry_run_never_deletes():
    """DRY-RUN: nawet gdy plan pozwala, NIC nie jest usuwane."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    p1, p2 = _patch_executors(dates, dates)
    with p1, p2, patch("src.collector.backup.delete_server_day") as mock_del:
        plan = run_cleanup("u@h", "/data", "/d/b.tar.gz", keep_last_n=2, dry_run=True)
    assert plan.allowed is True              # plan mówi "można"
    assert plan.to_delete == ["2026-10-01", "2026-10-02"]
    mock_del.assert_not_called()             # ale NIC nie usunięto


def test_real_run_deletes_approved_days():
    """TRYB WŁAŚCIWY: usuwa dokładnie zatwierdzone dni."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    p1, p2 = _patch_executors(dates, dates)
    with p1, p2, patch("src.collector.backup.delete_server_day") as mock_del:
        run_cleanup("u@h", "/data", "/d/b.tar.gz", keep_last_n=2, dry_run=False)
    # usunięto dwa najstarsze, każdy osobnym wywołaniem
    assert mock_del.call_count == 2
    deleted = [call.args[2] for call in mock_del.call_args_list]
    assert deleted == ["2026-10-01", "2026-10-02"]


def test_real_run_blocked_when_backup_incomplete():
    """TRYB WŁAŚCIWY: backup nie zawiera dnia → NIC nie usunięte."""
    dates = ["2026-10-01", "2026-10-02", "2026-10-03"]
    # archiwum NIE zawiera 10-01 (brakuje w backupie)
    p1, p2 = _patch_executors(dates, ["2026-10-02", "2026-10-03"])
    with p1, p2, patch("src.collector.backup.delete_server_day") as mock_del:
        plan = run_cleanup("u@h", "/data", "/d/b.tar.gz", keep_last_n=1, dry_run=False)
    assert plan.allowed is False
    mock_del.assert_not_called()             # bezpiecznik zadziałał mimo trybu właściwego


def test_real_run_nothing_to_delete():
    """TRYB WŁAŚCIWY: za mało dni → nic nie usunięte, bez błędu."""
    dates = ["2026-10-25", "2026-10-26"]
    p1, p2 = _patch_executors(dates, dates)
    with p1, p2, patch("src.collector.backup.delete_server_day") as mock_del:
        plan = run_cleanup("u@h", "/data", "/d/b.tar.gz", keep_last_n=7, dry_run=False)
    assert plan.allowed is False
    mock_del.assert_not_called()