"""Wysyłka powiadomień mailowych (alarmy o awariach kolektora)"""

import logging
import smtplib
from email.message import EmailMessage

from src.collector.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    ALERT_TO
)

log = logging.getLogger("notify")


class AlertGate:
    """
    Strażnik alarmów -> pilnuje, by mail szedł tylko przy zmianie stanu,
    a nie przy każdym sprawdzeniu.

    Zapobiega zasypaniu skrzynki mailami, gdy awaria trwa długo.
    """

    def __init__(self):
        # Na starcie zakładamy stan poprawny (brak alarmu)
        self._was_unhealthy = False

    def should_alert(self, is_unhealthy_now: bool) -> bool:
        """
        Decyduje, czy wysłać alarm przy tym sprawdzeniu.

        Zwraca True tylko przy przejściu poprawny → niepoprawny.
        Aktualizuje zapamiętany stan.

        :param is_unhealthy_now: czy stan jest niepoprawny w tej chwili
        :return: True tylko gdy stan właśnie zmienił się na niepoprawny
        """
        # Alarm tylko gdy: teraz niepoprawny, a wcześniej był poprawny
        crossing_into_unhealthy = is_unhealthy_now and not self._was_unhealthy

        # Zapamiętujemy obecny stan na następne wywołanie
        self._was_unhealthy = is_unhealthy_now

        return crossing_into_unhealthy


def send_alert(subject: str, body: str) -> bool:
    """
    Wysyła maila z alarmem przez Gmaila.

    Nie rzuca wyjątku tylko loguje błąd wysyłki i zwraca False, żeby problem
    z pocztą nigdy nie przerwał pracy kolektora.

    Gdy brakuje konfiguracji (zmiennych środowiskowych), nie próbuje wysyłać
    i zwraca False, a kolektor działa dalej, tylko bez powiadomień.

    :param subject: temat wiadomości
    :param body: treść wiadomości
    :return: True gdy wysłano, False gdy nie (brak konfiguracji lub błąd)
    """
    # Bez kompletu ustawień nie ma jak wysłać, więc tylko pomijamy
    if not (SMTP_USER and SMTP_PASSWORD and ALERT_TO):
        log.warning("Brak konfiguracji SMTP - pomijam wysyłkę alarmu")
        return False

    # Budujemy wiadomość
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ALERT_TO
    msg.set_content(body)

    try:
        # Łączymy się z Gmailem, szyfrujemy połączenie (starttls), logujemy, wysyłamy
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        log.info("Wysłano alarm mailowy: %s", subject)
        return True
    except Exception as exc:
        log.error("Nie udało się wysłać alarmu: %s", exc)
        return False