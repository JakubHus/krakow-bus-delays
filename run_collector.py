"""
Punkt wejścia kolektora GTFS-RT ZTP Kraków.

Uruchomienie:
    python run_collector.py             # Praca ciągła
    python run_collector.py --cycles 3  # Tylko N cykli (test)
"""

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.collector.collector import run_forever

# Katalogi na dane i logi (względem miejsca uruchomienia)
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
LOGS_DIR = DATA_DIR / "logs"
STATIC_DIR = DATA_DIR / "static"

def main():
    parser = argparse.ArgumentParser(description="Kolektor GTFS-RT ZTP Kraków")
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Ile cykli wykonać (domyślnie: bez końca)"
    )
    args = parser.parse_args()

    # Konfiguracja logowania: czas, poziom, treść -> na ekran
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    log = logging.getLogger("run")
    log.info("Start kolektora. Dane: %s, logi: %s", RAW_DIR, LOGS_DIR)
    if args.cycles:
        log.info("Tryb testowy: %d cykli", args.cycles)

    run_forever(RAW_DIR, LOGS_DIR, STATIC_DIR, max_cycles=args.cycles)

    log.info("Kolektor zakończył pracę")

if __name__ == "__main__":
    main()