"""Zapis sparsowanych wierszy do plików Parquet"""

from pathlib import Path
from datetime import datetime, timezone
import uuid

import pandas as pd

def build_partition_path(base_dir: Path,
                         dataset: str,
                         feed_code: str,
                         observed_at: int) -> Path:
    """
    Buduje ścieżkę partycji w stylu Hive na podstawie momentu pobrania.

    Przykład wyniku:
        data/raw/trip_updates/date=2026-09-01/hour=07/feed=A

    :param base_dir: katalog bazowy na dane surowe
    :param dataset: typ danych (trip_updates / vehicle_positions / service_alerts)
    :param feed_code: kod feedu (A/M/T)
    :param observed_at: epoch UTC momentu pobrania
    :return: ścieżka do folderu partycji (bez nazwy pliku)
    """
    # Zamieniamy epoch (liczbę sekund) na datę i godzinę w UTC
    dt = datetime.fromtimestamp(observed_at, tz=timezone.utc)

    return (
        base_dir
        / dataset
        / f"date={dt:%Y-%m-%d}"
        / f"hour={dt:%H}"
        / f"feed={feed_code}"
    )


def write_rows_to_parquet(rows: list[dict], target_path: Path) -> int:
    """
    Zapisuje listę wierszy (słowników) jako pojedynczy plik Parquet

    :param rows: lista słowników, które są zwracane przez parsery
    :param target_path: pełna ścieżka docelowa pliku parquet
    :return: liczba zapisanych wierszy
    """
    # Pusta lista -> jeśli nie ma czego zapisywać to zwracamy 0
    if not rows:
        return 0

    # Upewniamy się, że folder docelowy oraz foldery pośrednie istnieją
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Lista słowników -> DataFrame -> Parquet
    df = pd.DataFrame(rows)
    df.to_parquet((target_path), engine="pyarrow", compression="zstd", index=False)

    return len(rows)


def save_dataset(rows: list[dict],
                 base_dir: Path,
                 dataset: str,
                 feed_code: str,
                 observed_at: int) -> Path | None:
    """
    Zapisuje wiersze we właściwej partycji, atomowo.

    Składa w całość: budowę ścieżki partycji, nazwę pliku ze znacznikiem
    czasu i bezpieczny (atomowy) zapis. To jest funkcja, której używa kolektor.

    :param rows: lista słowników z parsera
    :param base_dir: katalog bazowy na dane surowe
    :param dataset: typ danych (trip_updates / vehicle_positions / service_alerts)
    :param feed_code: kod feedu (A/M/T)
    :param observed_at: epoch UTC momentu pobrania
    :return: ścieżka zapisanego pliku, albo None gdy nie było czego zapisać
    """
    # Nie ma czego zapisać (np. pusty feed alertów)
    if not rows:
        return None

    # Folder partycji: data/raw/trip_updates/date=.../hour=.../feed=A
    partition_dir = build_partition_path(base_dir, dataset, feed_code, observed_at)
    partition_dir.mkdir(parents=True, exist_ok=True)

    # Nazwa pliku ze znacznikiem czasu unikalnym w obrębie godziny
    dt = datetime.fromtimestamp(observed_at, tz=timezone.utc)
    # Krótki losowy sufiks gwarantuje unikalność nawet przy wielu zapisach
    # w tej samej sekundzie (np. dwa cykle o tym samym observed_at).
    unique = uuid.uuid4().hex[:8]
    filename = f"part-{dt:%Y%m%dT%H%M%S}-{unique}.parquet"
    final_path = partition_dir / filename

    # Zapis atomowy -> najpierw plik tymczasowy potem rename
    tmp_path = partition_dir / f".{filename}.tmp"
    df = pd.DataFrame(rows)
    try:
        df.to_parquet(tmp_path, engine="pyarrow", compression="zstd", index=False)
        tmp_path.rename(final_path)
    except Exception:
        # Nieudany zapis nie może zostawić pliku tymczasowego
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return final_path

