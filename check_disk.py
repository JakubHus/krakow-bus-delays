"""
Sprawdzenie ilości zajętej pamięci dysku z alarmem mailowym.

Uruchamiane raz dziennie. Sprawdza dysk i wysyła mail, gdy przekroczono próg.
Zapisuje stan do pliku. Samodzielnie nic nie usuwa, wysyła jedynie alert.
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.collector.disk_monitor import check_disk_and_alert
from src.collector.config import DISK_PATH, DISK_THRESHOLDS

STATE_PATH = Path("data/disk_monitor_state.json")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    check_disk_and_alert(DISK_PATH, DISK_THRESHOLDS, STATE_PATH)

if __name__ == '__main__':
    main()