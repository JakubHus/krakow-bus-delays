"""Testy wersjonowania rozkładu statycznego"""

from unittest.mock import patch, Mock
from src.collector.static_schedule import (
    compute_hash,
    is_new_version,
    read_known_hashes,
    record_version,
    archive_if_new
)


def test_same_content_same_hash():
    """Te same bajty zawsze dają ten sam hash"""
    content = b"jakas zawartosc rozkladu"
    assert compute_hash(content) == compute_hash(content)


def test_different_content_different_hash():
    """Różne bajty dają różne hashe"""
    assert compute_hash(b"wersja pierwsza") != compute_hash(b"wersja druga")


def test_single_byte_change_changes_hash():
    """Zmiana choćby jednego bajtu zmienia hash"""
    assert compute_hash(b"rozklad_A") != compute_hash(b"rozklad_B")


def test_hash_is_short_hex():
    """Hash to 12 znaków heksadecymalnych"""
    h = compute_hash(b"cokolwiek")
    assert len(h) == 12
    # wszystkie znaki to cyfry hex (0-9, a-f)
    assert all(c in "0123456789abcdef" for c in h)


def test_is_new_version_when_unknown():
    """Nieznany hash -> to nowa wersja"""
    content = b"nowy rozklad"
    known = set()   # nic jeszcze nie mamy
    assert is_new_version(content, known) is True


def test_is_not_new_when_known():
    """Znany hash -> to nie nowa wersja"""
    content = b"stary rozklad"
    known = {compute_hash(content)}   # już mamy ten hash
    assert is_new_version(content, known) is False


def test_is_new_when_content_differs_from_known():
    """Inna zawartość niż zapisana -> nowa wersja"""
    known = {compute_hash(b"wersja z wczoraj")}
    assert is_new_version(b"wersja z dzisiaj", known) is True


def test_read_known_hashes_empty_when_no_registry(tmp_path):
    """Brak rejestru -> pusty zbiór (pierwsze uruchomienie)"""
    assert read_known_hashes(tmp_path, "A") == set()


def test_record_then_read_roundtrip(tmp_path):
    """Zapisana wersja jest potem widoczna w odczycie"""
    record_version(tmp_path, "A", "abc123def456", "GTFS_KRK_A_abc123def456.zip", 19671944)

    known = read_known_hashes(tmp_path, "A")
    assert "abc123def456" in known


def test_read_filters_by_feed(tmp_path):
    """Odczyt zwraca hashe tylko dla wskazanego feedu"""
    record_version(tmp_path, "A", "hash_a", "plik_a.zip", 100)
    record_version(tmp_path, "M", "hash_m", "plik_m.zip", 200)

    assert read_known_hashes(tmp_path, "A") == {"hash_a"}
    assert read_known_hashes(tmp_path, "M") == {"hash_m"}


def test_record_multiple_versions_same_feed(tmp_path):
    """Kilka wersji tego samego feedu -> wszystkie w zbiorze"""
    record_version(tmp_path, "A", "wersja1", "plik1.zip", 100)
    record_version(tmp_path, "A", "wersja2", "plik2.zip", 110)

    known = read_known_hashes(tmp_path, "A")
    assert known == {"wersja1", "wersja2"}


def test_full_new_version_flow(tmp_path):
    """Pełny scenariusz: nowa wersja -> zapis -> już nie nowa."""
    content = b"tresc rozkladu"
    h = compute_hash(content)

    # Na starcie: nic nie znamy, więc to nowa wersja
    known = read_known_hashes(tmp_path, "A")
    assert is_new_version(content, known) is True

    # Zapisujemy ją
    record_version(tmp_path, "A", h, f"GTFS_KRK_A_{h}.zip", len(content))

    # Teraz już ją znamy — nie jest nowa
    known_after = read_known_hashes(tmp_path, "A")
    assert is_new_version(content, known_after) is False


def _fake_zip_response(content):
    """Sztuczna udana odpowiedź HTTP z podanymi bajtami"""
    resp = Mock()
    resp.content = content
    resp.status_code = 200
    resp.raise_for_status = Mock()
    return resp


def test_archive_new_version_saves_file(tmp_path):
    """Nowa wersja -> plik .zip powstaje i zwracany jest hash"""
    content = b"udawany rozklad GTFS"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_zip_response(content)):
        result_hash = archive_if_new("A", tmp_path)

    assert result_hash == compute_hash(content)
    # plik .zip z hashem w nazwie powstał
    zips = list(tmp_path.glob("GTFS_KRK_A_*.zip"))
    assert len(zips) == 1
    # rejestr też
    assert (tmp_path / "versions.csv").exists()


def test_archive_same_version_twice_saves_once(tmp_path):
    """Ten sam rozkład dwa razy -> archiwizowany tylko raz"""
    content = b"rozklad bez zmian"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_zip_response(content)):
        first = archive_if_new("A", tmp_path)
        second = archive_if_new("A", tmp_path)   # drugi raz — bez zmian

    assert first == compute_hash(content)
    assert second is None                        # drugie pobranie nic nie zmienia
    # tylko jeden plik
    assert len(list(tmp_path.glob("GTFS_KRK_A_*.zip"))) == 1


def test_archive_new_version_after_change(tmp_path):
    """Zmieniony rozkład -> nowa wersja archiwizowana obok starej"""
    with patch("src.collector.fetch.requests.get",
               return_value=_fake_zip_response(b"wersja pierwsza")):
        archive_if_new("A", tmp_path)

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_zip_response(b"wersja druga zmieniona")):
        archive_if_new("A", tmp_path)

    # dwie różne wersje na dysku
    assert len(list(tmp_path.glob("GTFS_KRK_A_*.zip"))) == 2


def test_archive_network_error_returns_none(tmp_path):
    """Błąd sieci -> None, żaden plik nie powstaje"""
    import requests
    with patch("src.collector.fetch.requests.get",
               side_effect=requests.exceptions.ConnectTimeout("timeout")):
        result = archive_if_new("A", tmp_path)

    assert result is None
    assert list(tmp_path.glob("*.zip")) == []


def test_archive_no_leftover_tmp(tmp_path):
    """Po udanej archiwizacji nie zostaje plik tymczasowy"""
    with patch("src.collector.fetch.requests.get",
               return_value=_fake_zip_response(b"rozklad")):
        archive_if_new("A", tmp_path)

    assert list(tmp_path.rglob("*.tmp")) == []