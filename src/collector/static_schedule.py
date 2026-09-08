"""Pobieranie i wersjonowanie rozkładu statycznego GTFS"""

import hashlib
from pathlib import Path
import csv
from datetime import datetime, timezone
import logging

from src.collector.fetch import fetch_url
from src.collector.config import BASE_URL

# Kolumny rejestru wersji rozkładu.
VERSION_COLUMNS = ["first_seen_utc", "feed", "hash", "filename", "size_bytes"]

log = logging.getLogger("static_schedule")


def compute_hash(content: bytes) -> str:
    """
    Liczy hash (SHA-256) zawartości pliku.

    Plik taki sam bajt w bajt zawsze da ten sam hash. Zmiana choćby
    jednego bajtu da inny. Służy do wykrywania, czy rozkład się zmienił.

    :param content: surowe bajty pliku
    :return: skrócony hash (12 znaków heksadecymalnych)
    """
    full_hash = hashlib.sha256(content).hexdigest()
    return full_hash[:12]


def is_new_version(content: bytes, known_hashes: set[str]) -> bool:
    """
    Sprawdza, czy zawartość to nowa wersja (nieznany dotąd hash).

    :param content: surowe bajty pobranego rozkładu
    :param known_hashes: zbiór hashy już zarchiwizowanych wersji
    :return: True gdy nowa wersja, False gdy już ją mamy
    """
    return compute_hash(content) not in known_hashes


def read_known_hashes(static_dir: Path, feed_code: str) -> set[str]:
    """
    Wczytuje z rejestru hashe wersji rozkładu już zarchiwizowanych dla feedu.

    Gdy rejestr nie istnieje (pierwsze uruchomienie), zwraca pusty zbiór.

    :param static_dir: katalog z rozkładami
    :param feed_code: kod feedu (A/M/T)
    :return: zbiór znanych hashy dla tego feedu
    """
    registry = static_dir / "versions.csv"
    if not registry.exists():
        return set()

    known = set()
    with open(registry, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["feed"] == feed_code:
                known.add(row["hash"])
    return known


def record_version(static_dir: Path,
                   feed_code: str,
                   content_hash: str,
                   filename: str,
                   size_bytes: int) -> None:
    """
    Dopisuje nową wersję rozkładu do rejestru versions.csv.

    Nagłówek zapisywany tylko przy tworzeniu pliku.

    :param static_dir: katalog z rozkładami
    :param feed_code: kod feedu (A/M/T)
    :param content_hash: hash zarchiwizowanej wersji
    :param filename: nazwa zapisanego pliku .zip
    :param size_bytes: rozmiar pliku w bajtach
    """
    static_dir.mkdir(parents=True, exist_ok=True)
    registry = static_dir / "versions.csv"
    write_header = not registry.exists()

    with open(registry, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=VERSION_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "first_seen_utc": datetime.now(timezone.utc).isoformat(),
            "feed": feed_code,
            "hash": content_hash,
            "filename": filename,
            "size_bytes": size_bytes,
        })


def archive_if_new(feed_code: str, static_dir: Path) -> str | None:
    """
    Pobiera rozkład statyczny feedu i archiwizuje go, jeśli to nowa wersja.

    Nie rzuca wyjątku na błędzie sieci tylko zwraca None i loguje ostrzeżenie.
    Gdy wersja nie jest nowa, również zwraca None (nic do zapisania).

    :param feed_code: kod feedu (A/M/T)
    :param static_dir: katalog na rozkłady
    :return: hash zarchiwizowanej wersji, albo None (błąd / brak zmian)
    """
    url = f"{BASE_URL}/GTFS_KRK_{feed_code}.zip"
    result = fetch_url(url, timeout=120)   # duży plik -> dłuższy timeout

    if not result.ok:
        log.warning("Nie udało się pobrać rozkładu %s: %s", feed_code, result.error)
        return None

    content = result.content
    known = read_known_hashes(static_dir, feed_code)

    if not is_new_version(content, known):
        log.info("Rozkład %s bez zmian - pomijam.", feed_code)
        return None

    # Nowa wersja -> zapisujemy plik i wpis do rejestru
    content_hash = compute_hash(content)
    filename = f"GTFS_KRK_{feed_code}_{content_hash}.zip"

    static_dir.mkdir(parents=True, exist_ok=True)
    target = static_dir / filename

    # Zapis atomowy: najpierw plik tymczasowy, potem zmiana nazwy
    tmp = static_dir / f".{filename}.tmp"
    try:
        tmp.write_bytes(content)
        tmp.rename(target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise

    record_version(static_dir, feed_code, content_hash, filename, len(content))
    log.info("Zarchiwizowano nowy rozkład %s (%s, %.1f MB)",
             feed_code, content_hash, len(content) / 1e6)

    return content_hash