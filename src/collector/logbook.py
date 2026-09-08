"""Dziennik prób pobrania (log kompletności) -> zapis do CSV"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.collector.fetch import FetchResult

# Stała kolejność kolumn w pliku CSV, aby log był spójny między dniami
LOG_COLUMNS = [
    "observed_at",
    "ok",
    "outcome",
    "dataset",
    "feed",
    "url",
    "status_code",
    "size_bytes",
    "duration_ms",
    "error"
]


def append_to_logbook(results: list[tuple[str, str, "CollectResult"]],
                      logs_dir: Path) -> Path | None:
    """
    Dopisuje wyniki pobrań do dziennego pliku CSV (log kompletności).

    Rozróżnia trzy wyniki w kolumnie 'outcome':
        - "ok"          - pobrano i sparsowano
        - "fetch_error" - nie udało się pobrać
        - "parse_error" - pobrano, ale nie udało się sparsować

    Nagłówek zapisywany jest tylko przy tworzeniu pliku, nie przy dopisywaniu.
    Plik jest partycjonowany po dacie: logs_dir/date=YYYY-MM-DD/poll_log.csv

    :param results: lista krotek (dataset, feed_code, FetchResult)
    :param logs_dir: katalog bazowy na logi
    :return: ścieżka pliku logu albo None gdy nie było czego zapisać
    """
    if not results:
        return None

    # Datę pliku bierzemy z pierwszego wyniku (moment pobrania, UTC)
    first_fetch = results[0][2].fetch_result
    dt = datetime.fromtimestamp(first_fetch.observed_at, tz=timezone.utc)

    log_dir = logs_dir / f"date={dt:%Y-%m-%d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "poll_log.csv"

    # Nagłówek tylko wtedy gdy plik jeszcze nie istnieje
    write_header = not log_path.exists()

    with open(log_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if write_header:
            writer.writeheader()

        for dataset, feed_code, collect_result in results:
            fr = collect_result.fetch_result

            # wynik
            if not collect_result.fetch_ok:
                outcome = "fetch_error"
            elif collect_result.parse_ok is False:
                outcome = "parse_error"
            else:
                outcome = "ok"

            writer.writerow({
                "observed_at": fr.observed_at,
                "ok": collect_result.fetch_ok and (collect_result.parse_ok is not False),
                "outcome": outcome,
                "dataset": dataset,
                "feed": feed_code,
                "url": fr.url,
                "status_code": fr.status_code,
                "size_bytes": fr.size_bytes,
                "duration_ms": fr.duration_ms,
                "error": fr.error
            })

    return log_path