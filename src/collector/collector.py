"""Kolektor — spina pobieranie, parsowanie i zapis w jeden cykl"""

from pathlib import Path
import time
import signal
import logging

from google.transit import gtfs_realtime_pb2

from src.collector.fetch import fetch_feed, Fetchresult
from src.collector.parse import (
    parse_trip_updates,
    parse_vehicle_positions,
    parse_service_alerts,
)
from src.collector.storage import save_dataset
from src.collector.config import FEED_CODES, RT_DATASETS
from src.collector.logbook import append_to_logbook
from src.collector.health import is_unhealthy
from src.collector.config import (
    FEED_CODES,
    RT_DATASETS,
    POLL_INTERVAL_SECONDS,
    HEALTH_HISTORY_SIZE
)

# Tabelka: typ danych → funkcja parsera.
# Wszystkie parsery mają tę samą sygnaturę (feed, observed_at, feed_code),
# więc kolektor wybiera właściwy przez zwykłe wyszukanie w słowniku.
PARSERS = {
    "trip_updates": parse_trip_updates,
    "vehicle_positions": parse_vehicle_positions,
    "service_alerts": parse_service_alerts,
}


def collect_one_feed(dataset: str,
                     feed_code: str,
                     base_dir: Path) -> Fetchresult:
    """
    Obsługuje jeden feed: pobiera, parsuje i zapisuje.

    Zwraca wynik pobierania (FetchResult) potrzebny do logu i oceny poprawności.
    Gdy pobranie się nie powiodło, parsowania i zapisu nie ma, ale funkcja
    i tak zwraca wynik (z ok=False), żeby kolektor mógł go zanotować.

    :param dataset: typ danych (klucz z PARSERS)
    :param feed_code: kod feedu (A/M/T)
    :param base_dir: katalog bazowy na dane surowe
    :return: FetchResult z próby pobrania
    """
    # 1. Pobranie. Nigdy nie rzuca tylko zwraca wynik z ok=True/False.
    result = fetch_feed(dataset, feed_code)

    # Pobranie się nie udało -> nie ma czego parsować. Zwracamy wynik do logu.
    if not result.ok:
        return result

    # 2. Parsowanie -> rozpakowujemy bajty i wybieramy parser ze słownika.
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(result.content)

    parser = PARSERS[dataset]
    rows = parser(feed, result.observed_at, feed_code)

    # 3. Zapis. save_dataset sam ogarnia pustą listę (zwróci None).
    save_dataset(rows, base_dir, dataset, feed_code, result.observed_at)

    return result


def run_one_cycle(base_dir: Path, logs_dir: Path) -> list[bool]:
    """
    Wykonuje jeden pełny cykl: wszystkie typy danych × wszystkie feedy.

    Dla każdej kombinacji pobiera, parsuje i zapisuje. Zbiera wyniki pobrań,
    dopisuje je do logu kompletności i zwraca listę sukcesów/porażek
    (do oceny poprawności przez moduł health).

    :param base_dir: katalog bazowy na dane surowe
    :param logs_dir: katalog bazowy na logi
    :return: lista wyników pobrań (True=sukces, False=błąd) z tego cyklu
    """
    log_entries = [] # (dataset, feed_code, FetchResult) do logu
    outcomes = [] # True/False do oceny poprawności

    for dataset in RT_DATASETS:
        for feed_code in FEED_CODES:
            result = collect_one_feed(dataset, feed_code, base_dir)
            log_entries.append((dataset, feed_code, result))
            outcomes.append(result.ok)

    # Jeden zapis do logu na cały cykl (wszystkie 9 prób naraz).
    append_to_logbook(log_entries, logs_dir)

    return outcomes


log = logging.getLogger("collector")


def run_forever(base_dir: Path,
                logs_dir: Path,
                max_cycles: int | None = None) -> None:
    """
    Uruchamia kolektor w pętli ciągłej.

    Po każdym cyklu ocenia poprwność pobierania i loguje ostrzeżenie,
    gdy jest źle. Można to zatrzymać (Ctrl+C / SIGTERM): dokańcza
    bieżący cykl i wychodzi.

    :param base_dir: katalog bazowy na dane surowe
    :param logs_dir: katalog bazowy na logi
    :param max_cycles: ile cykli wykonać (None = w nieskończoność).
                       Parametr istnieje głównie po to, by dało się to testować.
    """
    # Historia ostatnich wyników (True/False) do oceny poprawności
    history: list[bool] = []

    # Flaga zatrzymania, sygnał ją podniesie, pętla ją sprawdzi
    should_stop = {"value": False}

    def _handle_stop(signum, frame):
        log.info("Otrzymano sygnał zatrzymania — kończę po bieżącym cyklu.")
        should_stop["value"] = True

    # Przechwytujemy Ctrl+C (SIGINT) i SIGTERM (zatrzymanie przez system/serwer)
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    cycle_count = 0
    while not should_stop["value"]:
        outcomes = run_one_cycle(base_dir, logs_dir)

        # Dokładamy wyniki do historii, przycinając ją do ostatnich N
        history.extend(outcomes)
        history = history[-HEALTH_HISTORY_SIZE:]

        # Ocena poprawności, na razie tylko ostrzeżenie w logu
        if is_unhealthy(history):
            log.warning("Wykryto problem z pobieraniem — sprawdź połączenie/ZTP")

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            break
        if should_stop["value"]:
            break

        time.sleep(POLL_INTERVAL_SECONDS)