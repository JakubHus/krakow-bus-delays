"""Wykrywanie awarii pobierania na podstawie historii wyników"""

from src.collector.config import (
    HEALTH_MAX_CONSECUTIVE_ERRORS,
    HEALTH_WINDOW_SIZE,
    HEALTH_MAX_ERRORS_IN_WINDOW,
)

def count_trailing_errors(history: list[bool]) -> int:
    """
    Liczy, ile ostatnich prób POD RZĄD zakończyło się błędem.

    History to lista wyników w kolejności chronologicznej,
    gdzie True = sukces, False = błąd.

    :param history: lista wyników (True=sukces, False=błąd)
    :return: liczba błędów pod rząd na końcu historii
    """
    count = 0
    # Idziemy od końca (najnowsze próby) wstecz, aż trafimy na sukces.
    for ok in reversed(history):
        if ok:
            break
        count += 1
    return count


def count_errors_in_window(history: list[bool], window_size: int) -> int:
    """
    Liczy błędy w ostatnich `window_size` próbach.

    :param history: lista wyników (True=sukces, False=błąd)
    :param window_size: ile ostatnich prób brać pod uwagę
    :return: liczba błędów w oknie
    """
    window = history[-window_size:]        # ostatnie N wyników
    return window.count(False)             # ile z nich to błędy


def is_unhealthy(history: list[bool]) -> bool:
    """
    Ocenia, czy stan pobierania jest niezdrowy (alarm).

    Alarm, gdy spełniony JEDEN z warunków:
      - zbyt wiele błędów pod rząd (nagła awaria),
      - zbyt wiele błędów w oknie ostatnich prób (awaria przerywana).

    :param history: lista wyników (True=sukces, False=błąd)
    :return: True gdy stan wymaga alarmu, False gdy nie
    """
    trailing = count_trailing_errors(history)
    in_window = count_errors_in_window(history, HEALTH_WINDOW_SIZE)

    return (
        trailing >= HEALTH_MAX_CONSECUTIVE_ERRORS
        or in_window >= HEALTH_MAX_ERRORS_IN_WINDOW
    )