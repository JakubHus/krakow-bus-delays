"""Monitorowanie dostępnego miejsca na dysku. Ostrzega mailem, gdy miejsce się kończy"""

import logging
import shutil
import json
from pathlib import Path

from src.collector.notify import send_alert, AlertGate

log = logging.getLogger("disk_monitor")


def get_disk_usage_percent(path: str = "/") -> float:
    """
    Zwraca procent miejsca na dysku, które jest zajęte dla podanej ścieżki.

    :param path:  ścieżka na sprawdzanym dysku (domyślnie katalog główny)
    :return: procent używanej pamięci (0.0 - 100.0)
    """
    usage = shutil.disk_usage(path)
    return usage.used / usage.total * 100.0


def is_disk_low(path: str, threshold_percent: float) -> bool:
    """
    Sprawdza, czy ilość używanej przestrzeni dysku przekroczyła próg alarmowy.

    :param path: ścieżka na sprawdzanym dysku
    :param threshold_precent: próg w procentach, powyżej którego alarmujemy
    :return: True, jeśli zajęta pamięć przekroczyła próg lub jest mu równa
    """
    return get_disk_usage_percent(path) >= threshold_percent


def newly_crossed_thresholds(previous_percent: float,
                             current_percent: float,
                             thresholds: list[float]) -> list[float]:
    """
    Zwraca progi, które zostały właśnie przekroczone.

    Próg jest nowo przekroczony, gdy obecnie zajęta pamięć dysku go osiąga,
    a poprzednia jeszcze nie. To wykrywa moment przekroczenia bez pamiętania stanu obiektów,
    wystarczą dwie liczby.

    :param previous_percent: zajęta pamięć dysku przy poprzednim sprawdzeniu
    :param current_percent: aktualnie zajęta pamięć
    :param thresholds: progi
    :return: lista nowo przekroczonych progów (rosnąco)
    """
    return sorted(
        t for t in thresholds
        if current_percent >= t > previous_percent
    )


def load_last_percent(state_path: Path) -> float:
    """
    Wczytuje ostatni zapisany stan zajętej pamięci dysku.

    Gdy pliku nie ma (pierwsze uruchomienie), zwraca 0.0,
    czyli sytuacja jakby dysk był pusty, więc pierwszy
    pomiar nad progiem zaalarmuje.

    :param state_path: ścieżka pliku stanu
    :return: ostatni stan zajętej pamięci dysku lub 0.0
    """
    if not state_path.exists():
        return 0.0
    try:
        data = json.loads(state_path.read_text())
        return float(data.get("last_percent", 0.0))
    except (ValueError, OSError):
        return 0.0


def save_last_percent(state_path: Path, percent: float) -> None:
    """
    Zapisuje obecną ilość zajętego miejsca na dysku do pliku stanu.

    :param state_path: ścieżka pliku stanu
    :param percent: ilość zajętego miejsca do zapisania
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_percent": percent}))
    tmp.replace(state_path)


def check_disk_and_alert(path: str,
                         thresholds: list[float],
                         state_path: Path) -> list[float]:
    """
    Sprawdza dysk i wysyła alarm dla każdego nowo przekroczonych progów.
    Zapisuje stan do pliku.

    :param path: ścieżka na sprawdzanym dysku
    :param thresholds: progi w procentach
    :param state_path: plik stanu
    :return: lista progów, dla których wysłano alarm
    """
    current = get_disk_usage_percent(path)
    previous = load_last_percent(state_path)

    log.info("Zajęta pamięć na dysku %s: %.1f%% (poprzednio %.1f%%)", path, current, previous)

    crossed = newly_crossed_thresholds(previous, current, thresholds)
    for threshold in crossed:
            send_alert(
                f"Kolektor ZTP: dysk zajęty w {threshold:.0f}%+",
                f"Pamięć dysku na serwerze zajęta w {current:.1f}% "
                f"(przekroczono próg {threshold:.0f}%).\n\n"
                f"Zrób backup i wyczyść stare dane!"
            )
            log.warning("Alarm: przekroczono próg %.0f%% (dysk: %.1f%%)", threshold, current)

    save_last_percent(state_path, current)
    return crossed


