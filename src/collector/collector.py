"""Kolektor — spina pobieranie, parsowanie i zapis w jeden cykl"""

from pathlib import Path
import time
import signal
import logging
from dataclasses import dataclass

from google.transit import gtfs_realtime_pb2

from src.collector.fetch import fetch_feed, FetchResult
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
    HEALTH_HISTORY_SIZE,
    STATIC_CHECK_INTERVAL_SECONDS
)
from src.collector.static_schedule import archive_if_new
from src.collector.notify import AlertGate, send_alert

# Tabelka: typ danych → funkcja parsera.
# Wszystkie parsery mają tę samą sygnaturę (feed, observed_at, feed_code),
# więc kolektor wybiera właściwy przez zwykłe wyszukanie w słowniku.
PARSERS = {
    "trip_updates": parse_trip_updates,
    "vehicle_positions": parse_vehicle_positions,
    "service_alerts": parse_service_alerts,
}


@dataclass
class CollectResult:
    """
    Wynik obsługi jednego feedu, który rozróznia 3 stany:
        - pobrano i sparsowano      -> fetch_ok=True, parse_ok=True
        - pobrano i błąd parsowania -> fetch_ok=True, parse_ok=False
        - nie pobrano               -> fetch_ok=False, parse_ok=None

    :param fetch_ok: czy pobieranie się powiodło
    :param parse_ok: czy parsowanie się powiodło (None gdy pobieranie się nie powiodło)
    :param fetch_result: oryginalny wynik pobrania (do logu)
    """
    fetch_ok: bool
    parse_ok: bool | None
    fetch_result: FetchResult


def collect_one_feed(dataset: str,
                     feed_code: str,
                     base_dir: Path) -> FetchResult:
    """
    Obsługuje jeden feed: pobiera, parsuje i zapisuje.

    Nigdy nie rzuca wyjatku. Zarówno błąd pobierania i błąd parsowania
    (np. obcięty plik z serwera) są łapane i zwracane jako CollectResult,
    żeby jeden zły feed nie przerwał całego cyklu.

    :param dataset: typ danych (klucz z PARSERS)
    :param feed_code: kod feedu (A/M/T)
    :param base_dir: katalog bazowy na dane surowe
    :return: CollectorResult z trójstanowym wynikiem
    """
    # 1. Pobranie. Nie rzuca — zwraca FetchResult z ok=True/False.
    result = fetch_feed(dataset, feed_code)

    if not result.ok:
        # Nie pobrano — nie ma czego parsować.
        return CollectResult(fetch_ok=False, parse_ok=None, fetch_result=result)

    # 2. Parsowanie. TU może się wywalić na obciętym/wadliwym pliku —
    #    łapiemy błąd, żeby nie zabił całego cyklu.
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(result.content)
        parser = PARSERS[dataset]
        rows = parser(feed, result.observed_at, feed_code)
    except Exception as exc:
        log.warning("Błąd parsowania %s/%s: %s", dataset, feed_code, exc)
        return CollectResult(fetch_ok=True, parse_ok=False, fetch_result=result)

    # 3. Zapis. save_dataset sam ogarnia pustą listę.
    save_dataset(rows, base_dir, dataset, feed_code, result.observed_at)

    return CollectResult(fetch_ok=True, parse_ok=True, fetch_result=result)


def run_one_cycle(base_dir: Path, logs_dir: Path) -> tuple[list[bool], list[bool]]:
    """
    Wykonuje jeden pełny cykl: wszystkie typy danych * wszystkie feedy.

    Zwraca dwie osobne historie wyników do niezależnej oceny poprawności:
      - sieci (czy pobranie się udało)
      - parsowania (czy udało się rozłożyć pobrane dane)

    :param base_dir: katalog bazowy na dane surowe
    :param logs_dir: katalog bazowy na logi
    :return: (wyniki_sieci, wyniki_parsowania) — dwie listy True/False
    """
    log_entries = []
    fetch_outcomes = []   # True/False — czy pobrano
    parse_outcomes = []   # True/False — czy sparsowano (tylko dla pobranych)

    for dataset in RT_DATASETS:
        for feed_code in FEED_CODES:
            result = collect_one_feed(dataset, feed_code, base_dir)
            log_entries.append((dataset, feed_code, result))

            fetch_outcomes.append(result.fetch_ok)
            # Parsowanie oceniamy tylko wtedy, gdy w ogóle pobrano.
            # Gdy nie pobrano (parse_ok=None), nie zaśmiecamy historii parsowania.
            if result.parse_ok is not None:
                parse_outcomes.append(result.parse_ok)

    append_to_logbook(log_entries, logs_dir)

    return fetch_outcomes, parse_outcomes


log = logging.getLogger("collector")


def check_static_schedules(static_dir: Path) -> None:
    """
    Sprawdza i archiwizuje rozkład statyczny dla wszystkich feedów.
    Wywoływana rzadko (raz na dobę), nie w każdym cyklu.

    :param static_dir: katalog na rozkłady
    """
    for feed_code in FEED_CODES:
        archive_if_new(feed_code, static_dir)


def run_forever(base_dir: Path,
                logs_dir: Path,
                static_dir: Path,
                max_cycles: int | None = None) -> None:
    """
    Uruchamia kolektor w pętli ciągłej.

    Po każdym cyklu ocenia poprwność pobierania i loguje ostrzeżenie,
    gdy jest źle. Raz na dobę (oraz na starcie) sprawdza i archiwizuje
    rozkład statyczny. Można to zatrzymać (Ctrl+C / SIGTERM): dokańcza
    bieżący cykl i wychodzi.

    :param base_dir: katalog bazowy na dane surowe
    :param logs_dir: katalog bazowy na logi
    :param static_dir: katalog bazowy na logi
    :param max_cycles: ile cykli wykonać (None = w nieskończoność).
                       Parametr istnieje głównie po to, by dało się to testować.
    """
    # Historia ostatnich wyników (True/False) do oceny poprawności
    fetch_history: list[bool] = []
    parse_history: list[bool] = []
    fetch_gate = AlertGate() # alarmy sieci
    parse_gate = AlertGate() # alarmy parsowania

    # Flaga zatrzymania, sygnał ją podniesie, pętla ją sprawdzi
    should_stop = {"value": False}

    def _handle_stop(signum, frame):
        log.info("Otrzymano sygnał zatrzymania — kończę po bieżącym cyklu.")
        should_stop["value"] = True

    # Przechwytujemy Ctrl+C (SIGINT) i SIGTERM (zatrzymanie przez system/serwer)
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    # Rozkład sprawdzamy na starcie, a potem raz na dobę
    check_static_schedules(static_dir)
    last_static_check = time.time()

    cycle_count = 0
    while not should_stop["value"]:
        fetch_outcomes, parse_outcomes = run_one_cycle(base_dir, logs_dir)

        # Dokładamy wyniki do historii, przycinając ją do ostatnich N
        fetch_history.extend(fetch_outcomes)
        fetch_history = fetch_history[-HEALTH_HISTORY_SIZE:]
        parse_history.extend(parse_outcomes)
        parse_history = parse_history[-HEALTH_HISTORY_SIZE:]

        # Ocena działania sieci, alarm mailowy przy przejściu w awarię
        fetch_bad = is_unhealthy(fetch_history)
        if fetch_bad:
            log.warning("Problem z pobieraniem - sprawdź połączenie/serwer ZTP")
        if fetch_gate.should_alert(fetch_bad):
            send_alert(
                "Kolektor ZTP: problem z pobieraniem",
                "Wykryto serię błędów pobierania danych z serwera ZTP. "
                "Sprawdź połączenie sieciowe i dostępność gtfs.ztp.krakow.pl."
            )

        # Ocena działania parsowania, osobny alarm
        parse_bad = is_unhealthy(parse_history)
        if parse_bad:
            log.warning("Problem z parsowaniem danych, możliwa zmiana formatu feedu")
        if parse_gate.should_alert(parse_bad):
            send_alert(
                "kolektor ZTP: problem z parsowaniem",
                "Wykryto serię błędów parsowania danych. "
                "Możliwa zmiana formatu feedu GTFS-RT po stronie ZTP."
            )

        # Czy minęła doba od ostatniego sprawdzenia rozkładu
        if time.time() - last_static_check >= STATIC_CHECK_INTERVAL_SECONDS:
            check_static_schedules(static_dir)
            last_static_check = time.time()

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            break
        if should_stop["value"]:
            break

        time.sleep(POLL_INTERVAL_SECONDS)