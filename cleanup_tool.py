"""
Narzędzie do czyszczenia starych danych po backupie z serwera.
Usuwa stare dni z serwera, ale tylko, gdy wskazany backup
nie jest uszkodzony i zawiera te dni. Domyślnie działa w trybie
dry-run i nic nie usuwa.

Użycie:
    Bezpieczny tryb dry-run, który nic nie usuwa, tylko pokazuje plan
        python cleanup_tool.py --server kubbah@48.209.8.32 --archive /d/kmk-backup/ztp-backup-2026-10-26.tar.gz

    Tryb usuwania
        python cleanup_tool.py --server kubbah@48.209.8.32 --archive /d/kmk-backup/ztp-backup-2026-10-26.tar.gz --execute

Backup robi się wcześniej osobno (info w deploy/BACKUP.md).
To narzędzie tylko weryfikuje backup i sprząta serwer.
"""

import argparse
import logging

from src.collector.backup import run_cleanup

REMOTE_DATA_DIR = "/opt/ztp-collector/data"
KEEP_LAST_DAYS = 7


def main():
    parser = argparse.ArgumentParser(description="Czyszczenie starych danych z serwera z danymi ZTP")

    parser.add_argument("--server", required=True, help="adres serwera, np. 'kubbah@48.209.8.32'")
    parser.add_argument("--archive", required=True, help="ścieżka do istniejącego backupu")
    parser.add_argument("--keep", type=int, default=KEEP_LAST_DAYS,
                        help=f"ile ostatnich dni zostawić (domyślnie {KEEP_LAST_DAYS})")
    parser.add_argument("--execute", action="store_true", help="faktyczne usuwanie, bez tej flagi tylko dry-run")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Domyślnie dry-run
    dry_run = not args.execute

    if dry_run:
        print("----- TRYB PRÓBNY - nic nie zostanie usunięte -----")
    else:
        print("----- TRYB USUWANIA - dni zostaną usunięte z serwera -----")

    plan = run_cleanup(
        server=args.server,
        remote_data_dir=REMOTE_DATA_DIR,
        archive_path=args.archive,
        keep_last_n=args.keep,
        dry_run=dry_run
    )

    print()
    if plan.allowed and not dry_run:
        print(f"Usunięto {len(plan.to_delete)} dni: {plan.to_delete}")
    elif plan.allowed and dry_run:
        print(f"PLAN: usunięte zostałyby {len(plan.to_delete)} dni: {plan.to_delete}")
        print("Aby wykonać, uruchom ponownie z flagą --execute")
    else:
        print(f"Brak akcji. {plan.reason}")


if __name__ == "__main__":
    main()


