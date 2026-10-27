"""Testy monitora dysku."""

from collections import namedtuple
from unittest.mock import patch

from src.collector.disk_monitor import (
    get_disk_usage_percent,
    is_disk_low,
    newly_crossed_thresholds,
    load_last_percent,
    save_last_percent,
    check_disk_and_alert,
)

FakeUsage = namedtuple("FakeUsage", ["total", "used", "free"])


# --- get_disk_usage_percent / is_disk_low ---

def test_usage_percent_half_full():
    """Dysk w połowie pełny -> 50%."""
    fake = FakeUsage(total=100, used=50, free=50)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake):
        assert get_disk_usage_percent("/") == 50.0


def test_usage_percent_nearly_full():
    """Dysk prawie pełny -> wysoki procent."""
    fake = FakeUsage(total=1000, used=850, free=150)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake):
        assert get_disk_usage_percent("/") == 85.0


def test_disk_low_above_threshold():
    """Zajęta pamięć dysku powyżej progu -> True."""
    fake = FakeUsage(total=100, used=80, free=20)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake):
        assert is_disk_low("/", threshold_percent=75) is True


def test_disk_low_below_threshold():
    """Zajęta pamięć dysku poniżej progu -> False."""
    fake = FakeUsage(total=100, used=60, free=40)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake):
        assert is_disk_low("/", threshold_percent=75) is False


def test_disk_low_exactly_at_threshold():
    """Zajęta pamięć dysku dokładnie na progu -> True."""
    fake = FakeUsage(total=100, used=75, free=25)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake):
        assert is_disk_low("/", threshold_percent=75) is True


# --- newly_crossed_thresholds ---

def test_crossing_one_threshold():
    """Wzrost z 70 na 78 -> przekracza tylko próg 75."""
    assert newly_crossed_thresholds(70, 78, [75, 85, 92]) == [75]


def test_crossing_nothing_new():
    """Wzrost z 80 na 83 -> nic nowego (75 już było, 85 jeszcze nie)."""
    assert newly_crossed_thresholds(80, 83, [75, 85, 92]) == []


def test_crossing_multiple_at_once():
    """Skok z 70 na 95 -> przekracza wszystkie trzy progi."""
    assert newly_crossed_thresholds(70, 95, [75, 85, 92]) == [75, 85, 92]


def test_no_cross_when_falling():
    """Spadek zajętej pamięci dysku -> nie alarmuje."""
    assert newly_crossed_thresholds(90, 50, [75, 85, 92]) == []


# --- stan w pliku (odczyt i zapis) ---

def test_load_missing_state_returns_zero(tmp_path):
    """Brak pliku stanu -> 0.0 (pierwsze uruchomienie)."""
    assert load_last_percent(tmp_path / "state.json") == 0.0


def test_save_then_load_roundtrip(tmp_path):
    """Zapisana zajęta pamięć dysku jest potem poprawnie wczytana."""
    state = tmp_path / "state.json"
    save_last_percent(state, 83.5)
    assert load_last_percent(state) == 83.5


def test_load_corrupt_state_returns_zero(tmp_path):
    """Uszkodzony plik stanu -> 0.0."""
    state = tmp_path / "state.json"
    state.write_text("to nie jest JSON")
    assert load_last_percent(state) == 0.0


# --- check_disk_and_alert ---

def test_alerts_and_persists(tmp_path):
    """Pierwsze przekroczenie progu -> alarm, stan zapisany."""
    state = tmp_path / "state.json"
    fake = FakeUsage(total=100, used=78, free=22)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake), \
         patch("src.collector.disk_monitor.send_alert") as mock_send:
        crossed = check_disk_and_alert("/", [75, 85, 92], state)
    assert crossed == [75]
    mock_send.assert_called_once()
    assert load_last_percent(state) == 78.0


def test_no_spam_across_runs(tmp_path):
    """Dwa uruchomienia przy tym samym poziomie -> alarm tylko z pierwszego."""
    state = tmp_path / "state.json"
    fake = FakeUsage(total=100, used=88, free=12)
    with patch("src.collector.disk_monitor.shutil.disk_usage", return_value=fake), \
         patch("src.collector.disk_monitor.send_alert") as mock_send:
        check_disk_and_alert("/", [75, 85, 92], state)   # 1. raz: 75 i 85
        check_disk_and_alert("/", [75, 85, 92], state)   # 2. raz: cisza (stan trwały)
    assert mock_send.call_count == 2


def test_escalation_across_runs(tmp_path):
    """Wzrost między uruchomieniami: 78% -> 87%, alarmy przy 75 potem 85."""
    state = tmp_path / "state.json"
    with patch("src.collector.disk_monitor.send_alert") as mock_send:
        with patch("src.collector.disk_monitor.shutil.disk_usage",
                   return_value=FakeUsage(100, 78, 22)):
            assert check_disk_and_alert("/", [75, 85, 92], state) == [75]
        with patch("src.collector.disk_monitor.shutil.disk_usage",
                   return_value=FakeUsage(100, 87, 13)):
            assert check_disk_and_alert("/", [75, 85, 92], state) == [85]
    assert mock_send.call_count == 2