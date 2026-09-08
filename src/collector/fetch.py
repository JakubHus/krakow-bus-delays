"""Pobieranie surowych danych GTFS-RT z sieci"""

import time
from dataclasses import dataclass

import requests

from src.collector.config import USER_AGENT, BASE_URL, RT_DATASETS

@dataclass
class FetchResult:
    """
    Wynik jednej próby pobrania. Zawsze zwracany (przy błędzie też).

    :param ok: czy pobieranie się powiodło
    :param url: adres spod którego pobierano
    :param observed_at: epoch UTC momentu pobierania
    :param content: pobrane surowe bajty (tylko jeśli ok=True, inaczej None)
    :param status_code: kod HTTP odpowiedzi
    :param size_bytes: rozmiar pobranych danych w bajtach
    :param error: opis błędu (tylko jeśli ok=False, inaczej None)
    :param duration_ms: ile trwała próba w milisekundach
    """
    ok: bool
    url: str
    observed_at: int
    content: bytes | None = None
    status_code: int | None = None
    size_bytes: int | None = None
    error: str | None = None
    duration_ms: float | None = None


def fetch_url(url: str, timeout: int = 20) -> FetchResult:
    """
    Pobiera zawartość z danego URL. Nigdy nie rzuca wyjątku (błąd sieci,
    timeout czy zły kod HTTP zwraca jako FetchResult z ok=False).

    :param url: adres do pobierania
    :param timeout: maksymalny czas oczekiwania w sekundach
    :return: FetchResult z wynikiem próby pobierania
    """
    observed_at = int(time.time())
    start = time.perf_counter()
    headers = {'User-Agent': USER_AGENT}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # Zły kod HTTP (4xx, 5xx) traktujemy jako błąd, ale kontrolowany
        resp.raise_for_status()

        return FetchResult(
            ok=True,
            url=url,
            observed_at=observed_at,
            content=resp.content,
            status_code=resp.status_code,
            size_bytes=len(resp.content),
            duration_ms=duration_ms
        )

    except requests.exceptions.RequestException as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        # Jeśli wiadomość w ogóle nadeszła dołączamy jej kod HTTP
        status = exc.response.status_code if exc.response is not None else None

        return FetchResult(
            ok=False,
            url=url,
            observed_at=observed_at,
            status_code=status,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=duration_ms
        )


def build_feed_url(dataset: str, feed_code: str) -> str:
    """
    Buduje adres feedu GTFS-RT z konfiguracji.

    Przykład:
        build_feed_url("trip_updates", "A")
        -> "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"

    :param dataset: typ danych (klucz z RT_DATASETS)
    :param feed_code: kod feedu (A/M/T)
    :return: pełny URL pliku .pb
    :raises KeyError: gdy dataset nie istnieje w konfiguracji
    """
    prefix = RT_DATASETS[dataset]
    return f"{BASE_URL}/{prefix}_{feed_code}.pb"


def fetch_feed(dataset: str, feed_code: str, timeout: int = 20) -> FetchResult:
    """
    Pobiera konkretny feed GTFS-RT (składa URL i pobiera).

    :param dataset: typ danych (trip_updates / vehicle_positions / service_alerts)
    :param feed_code: kod feedu (A/M/T)
    :param timeout: maksymalny czas oczekiwania w sekundach
    :return: FetchResult z wynikiem próby
    """
    url = build_feed_url(dataset, feed_code)
    return fetch_url(url, timeout=timeout)