"""Dziennik prób pobrania (log kompletności) -> zapis do CSV"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.collector.fetch import Fetchresult

# Stała kolejność kolumn w pliku CSV, aby log był spójny między dniami
LOG_COLUMNS = [
    "observed_at",
    "ok",
    "dataset",
    "feed",
    "url",
    "status_code",
    "size_bytes",
    "duration_ms",
    "error"
]


def append_to_logbook(results: list[tuple[str, str, Fetchresult]],
                      logs_dir: Path) -> Path | None:
    """
    Dopisuje wyniki pobrań do dziennego pliku CSV (log kompletności).

    Nagłówek zapisywany jest tylko przy tworzeniu pliku, nie przy dopisywaniu.
    Plik jest partycjonowany po dacie: logs_dir/date=YYYY-MM-DD/poll_log.csv

    :param results: lista krotek (dataset, feed_code, FetchResult)
    :param logs_dir: katalog bazowy na logi
    :return: ścieżka pliku logu albo None gdy nie było czego zapisać
    """
    if not results:
        return None

    # Datę pliku bierzemy z pierwszego wyniku (moment pobrania, UTC)
    first_result = results[0][2]
    dt = datetime.fromtimestamp(first_result.observed_at, tz=timezone.utc)

    log_dir = logs_dir / f"date={dt:%Y-%m-%d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "poll_log.csv"

    # Nagłówek tylko wtedy gdy plik jeszcze nie istnieje
    write_header = not log_path.exists()

    with open(log_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if write_header:
            writer.writeheader()

        for dataset, feed_code, result in results:
            writer.writerow({
                "observed_at": result.observed_at,
                "ok": result.ok,
                "dataset": dataset,
                "feed": feed_code,
                "url": result.url,
                "status_code": result.status_code,
                "size_bytes": result.size_bytes,
                "duration_ms": result.duration_ms,
                "error": result.error
            })

    return log_path