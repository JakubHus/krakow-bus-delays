"""Testy wykrywania awarii pobierania"""

from src.collector.health import (
    count_trailing_errors,
    count_errors_in_window,
    is_unhealthy,
)

# Skróty: S = sukces (True), E = błąd (False)
S = True
E = False

# --- count_trailing_errors ---

def test_trailing_all_success():
    """Same sukcesy → zero błędów pod rząd."""
    assert count_trailing_errors([S, S, S, S]) == 0


def test_trailing_counts_from_end():
    """Liczy błędy na końcu, aż do pierwszego sukcesu."""
    assert count_trailing_errors([S, S, E, E, E]) == 3


def test_trailing_reset_by_success():
    """Sukces na końcu zeruje licznik pod rząd."""
    assert count_trailing_errors([E, E, E, S]) == 0


def test_trailing_empty_history():
    """Pusta historia → zero."""
    assert count_trailing_errors([]) == 0


# --- count_errors_in_window ---

def test_window_counts_recent_errors():
    """Liczy błędy w ostatnich N próbach."""
    history = [S, S, E, S, E]
    assert count_errors_in_window(history, window_size=15) == 2


def test_window_limits_to_size():
    """Bierze tylko ostatnie N, ignoruje starsze."""
    # 20 błędów, ale okno = 5 → widzi tylko 5
    history = [E] * 20
    assert count_errors_in_window(history, window_size=5) == 5


# --- is_unhealthy: warunek "pod rząd" ---

def test_healthy_when_few_errors():
    """Kilka rozproszonych błędów → zdrowo."""
    history = [S, S, E, S, S, E, S, S]
    assert is_unhealthy(history) is False


def test_unhealthy_on_consecutive_errors():
    """5 błędów pod rząd → alarm (nagła awaria)."""
    history = [S, S, S, E, E, E, E, E]
    assert is_unhealthy(history) is True


# --- is_unhealthy: warunek "okno" (Twój scenariusz!) ---

def test_unhealthy_on_intermittent_failures():
    """
    Awaria przerywana: błędy poprzeplatane sukcesami, żaden ciąg
    nie sięga 5 pod rząd — ale w oknie jest ich za dużo.
    Licznik 'pod rząd' by to przegapił; okno łapie.
    """
    # 8 błędów, każdy "uratowany" sukcesem, więc max 1 pod rząd
    history = [E, S, E, S, E, S, E, S, E, S, E, S, E, S, E]
    # pod rząd: 1 (kończy się na E, ale poprzedza S) — poniżej progu 5
    assert count_trailing_errors(history) == 1
    # ale w oknie 15 jest 8 błędów → alarm
    assert is_unhealthy(history) is True


def test_healthy_empty_history():
    """Brak historii (start kolektora) → zdrowo, nie alarmuj."""
    assert is_unhealthy([]) is False