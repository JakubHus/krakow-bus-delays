"""Testy wysyłki powiadomień mailowych (z mockowaniem SMTP)"""

from unittest.mock import patch, MagicMock

from src.collector.notify import send_alert, AlertGate


def test_send_alert_success():
    """Przy komplecie konfiguracji mail jest wysyłany, zwraca True"""
    fake_server = MagicMock()

    with patch("src.collector.notify.SMTP_USER", "test@gmail.com"), \
         patch("src.collector.notify.SMTP_PASSWORD", "haslo_aplikacji"), \
         patch("src.collector.notify.ALERT_TO", "odbiorca@gmail.com"), \
         patch("src.collector.notify.smtplib.SMTP") as mock_smtp:
        # SMTP używany jako context manager (with ...), podstawiamy fake_server
        mock_smtp.return_value.__enter__.return_value = fake_server
        result = send_alert("Test alarm", "Treść alarmu")

    assert result is True
    fake_server.starttls.assert_called_once()
    fake_server.login.assert_called_once_with("test@gmail.com", "haslo_aplikacji")
    fake_server.send_message.assert_called_once()


def test_send_alert_no_config_skips():
    """Brak konfiguracji -> nie próbuje wysyłać, zwraca False"""
    with patch("src.collector.notify.SMTP_USER", None), \
         patch("src.collector.notify.SMTP_PASSWORD", None), \
         patch("src.collector.notify.ALERT_TO", None):
        result = send_alert("Temat", "Treść")

    assert result is False


def test_send_alert_smtp_error_returns_false():
    """Błąd SMTP -> False, ale bez wyjątku (kolektor działa dalej)"""
    with patch("src.collector.notify.SMTP_USER", "test@gmail.com"), \
         patch("src.collector.notify.SMTP_PASSWORD", "haslo"), \
         patch("src.collector.notify.ALERT_TO", "odbiorca@gmail.com"), \
         patch("src.collector.notify.smtplib.SMTP",
               side_effect=Exception("połączenie odrzucone")):
        result = send_alert("Temat", "Treść")

    assert result is False


def test_send_alert_partial_config_skips():
    """Niepełna konfiguracja (brak hasła) -> pomija wysyłkę"""
    with patch("src.collector.notify.SMTP_USER", "test@gmail.com"), \
         patch("src.collector.notify.SMTP_PASSWORD", None), \
         patch("src.collector.notify.ALERT_TO", "odbiorca@gmail.com"):
        result = send_alert("Temat", "Treść")

    assert result is False


def test_gate_alerts_on_transition_to_unhealthy():
    """Przejście zdrowy -> chory wyzwala alarm"""
    gate = AlertGate()
    # start zdrowy, teraz chory -> alarm
    assert gate.should_alert(is_unhealthy_now=True) is True


def test_gate_silent_while_staying_unhealthy():
    """Trwająca awaria nie spamuje -> alarm tylko raz"""
    gate = AlertGate()
    assert gate.should_alert(True) is True      # pierwszy raz — alarm
    assert gate.should_alert(True) is False     # nadal chory — cisza
    assert gate.should_alert(True) is False     # nadal chory — cisza


def test_gate_silent_while_healthy():
    """Zdrowy stan nie wyzwala alarmów"""
    gate = AlertGate()
    assert gate.should_alert(False) is False
    assert gate.should_alert(False) is False


def test_gate_realerts_after_recovery():
    """Po naprawie i ponownej awarii alarm leci znowu"""
    gate = AlertGate()
    assert gate.should_alert(True) is True      # awaria — alarm
    assert gate.should_alert(True) is False     # trwa — cisza
    assert gate.should_alert(False) is False    # naprawiło się — cisza
    assert gate.should_alert(True) is True      # NOWA awaria — znów alarm


def test_gate_full_realistic_sequence():
    """Realistyczny przebieg: spokój, awaria, trwanie, naprawa, spokój."""
    gate = AlertGate()
    results = [gate.should_alert(state) for state in
               [False, False, True, True, True, False, False, True]]
    #           spokój      AWARIA  trwa  trwa  naprawa    NOWA AWARIA
    assert results == [False, False, True, False, False, False, False, True]