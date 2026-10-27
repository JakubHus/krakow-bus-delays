"""Logika narzędzia do backupu i czyszczenia starych danych."""

from datetime import datetime
from dataclasses import dataclass, field
import subprocess
import logging


log = logging.getLogger("backup")


@dataclass
class DeletionPlan:
    """
    Wynik decyzji czy i co wolno usunąć.

    :param allowed: czy usuwanie jest dozwolone
    :param to_delete: dni zatwierdzone do usunięcia (puste, gdy allowed=False)
    :param reason: wyjaśnienie decyzji
    """
    allowed: bool
    to_delete: list[str] = field(default_factory=list)
    reason: str = ""


def run_cleanup(server: str, remote_data_dir: str, archive_path: str, keep_last_n: int, dry_run: bool = True) -> DeletionPlan:
    """
    Główna procedura czyszczenia serwera w oparciu o istniejący backup.

    Przechodzi przez wszystkie zabezpieczenia, a usuwa tylko gdy:
    - backup (archive_path) daje się odczytać, czyli nie jest uszkodzony
    - plan_deletion zatwierdzi usuwanie

    Tryb dry_run=True (domyślny) niczego nie usuwa, tylko zwraca plan.
    Tryb dry_run=False wykonuje usuwanie zatwierdzonych dni.

    :param server: adres serwera, np. 'nazwa@11.111.1.11'
    :param remote_data_dir: katalog danych na serwerze
    :param archive_path: ścieżka do istniejącego pliku backupu
    :param keep_last_n: ile ostatnich dni zostawić na serwerze
    :param dry_run: True - tylko pokaż plan, False - wykonaj usuwanie
    :return: DeletionPlan z decyzją i listą dni
    """
    # Odczytanie zawartości backupu. Jeśli jest uszkodzony -> nic nie usuwamy
    log.info("Weryfikuję backup: %s", archive_path)
    archive_paths = list_archive_contents(archive_path)

    # Odczytanie dni będących na serwerze
    log.info("Odczytuję dni z serwera: %s", server)
    server_dates = list_server_dates(server, remote_data_dir)

    # Bramka bezpieczeństwa (decyzja o usuwaniu)
    plan = plan_deletion(server_dates, archive_paths, keep_last_n, backup_ok=True)

    # Pokazanie planu
    if plan.allowed:
        log.info("PLAN: usunąć %d dni: %s", len(plan.to_delete), plan.to_delete)
    else:
        log.info("PLAN: nic nie zostanie usunięte. Powód: %s", plan.reason)

    # Tutaj kończy się dry-run
    if dry_run:
        log.info("Niczego nie usunięto (dry-run)")
        return plan

    # Tryb właściwy, który usuwa, jeśli bramka wszystko zatwierdziła
    if not plan.allowed:
        log.info("Usuwanie zablokowane przez zabezpieczenia - zakończono bez zmian")
        return plan

    for date in plan.to_delete:
        log.info("Usuwany dzień %s z serwera...", date)
        delete_server_day(server, remote_data_dir, date)
    log.info("Usunięto %d dni. Zostają ostatnie %d", len(plan.to_delete), keep_last_n)

    return plan


def parse_date_folders(folder_names: list[str]) -> list[str]:
    """
    Z listy nazw folderów (pattern 'date=2026-10-20') wyłuskuje same daty,
    posortowane rosnąco. Ignoruje nazwy, które nie pasują do wzorca.

    :param folder_names: nazwy folderów, np. ['date=2026-10-20', 'date=2026-10-21']
    :return: posortowana lista dat jako tekst
    """
    dates = []
    for name in folder_names:
        if name.startswith("date="):
            date_str = name[len("date="):]
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                dates.append(date_str)
            except ValueError:
                continue
    return sorted(dates)


def days_to_delete(all_dates: list[str], keep_last_n: int) -> list[str]:
    """
    Wybiera dni do usunięcia, wszystkie oprócz ostatnich 'keep_last_n'.

    Jeśli dni jest mniej lub tyle samo, co bufor do zostawienia,
    zwraca pustą listę. Nic nie usuwa, bo nie ma czego bezpiecznie usunąć.

    :param all_dates: wszystkie daty na serwerze (posortowane rosnąco)
    :param keep_last_n: ile ostatnich dni zostawić
    :return: lista dat do usunięcia (najstarsze), może być pusta
    """
    if keep_last_n < 0:
        raise ValueError("keep_last_n nie może być ujemne")
    # Gdy mamy tyle samo lub mniej dni niż bufor nic nie usuwamy
    if len(all_dates) < keep_last_n:
        return []
    return all_dates[:-keep_last_n] if keep_last_n > 0 else all_dates[:]


def archive_contains_date(archive_paths: list[str], date: str) -> bool:
    """
    Sprawdza, czy archiwum zawiera dane dla podanego dnia.

    Szuka w ścieżkach archiwum wzorca 'date=<data>' w katalogu raw.
    Służy jako bezpiecznik: przed usunięciem dnia z serwera potwierdzamy,
    że ten dzień jest w backupie.

    :param archive_paths: lista ścieżek z archiwum (wynik 'tar -tzf')
    :param date: data sprawdzenia
    :return: True, jeśli archiwum zawiera pliki danych dla tego dnia
    """
    marker = f"date={date}"
    for path in archive_paths:
        if "raw/" in path and marker in path:
            return True
    return False


def verify_backup_covers_days(archive_paths: list[str], days: list[str]) -> tuple[bool, list[str]]:
    """
    Sprawdza, czy archiwum zawiera wszystkie podane dni.

    Kluczowy bezpiecznik przed usuwaniem, który zwraca (True, []) tylko gdy każdy
    dzień z listy jest w archiwum. Jeśli którykolwiek jest brakujący zwraca
    (False, lista_brakujących), co ma zablokować usuwanie.

    :param archive_paths: lista ścieżek z archiwum
    :param days: dni, które mają być w archiwum przed ich usunięciem
    :return: tuple z bool'em, czy wszystkie dni są w archiwum i listą tych, które są brakujące
    """
    missing = [d for d in days if not archive_contains_date(archive_paths, d)]
    return (len(missing) == 0, missing)


def plan_deletion(server_dates: list[str], archive_paths: list[str], keep_last_n: int, backup_ok: bool) -> DeletionPlan:
    """
    Jedyna bramka do usuwania. Zbiera wszystkie zabezpieczenia i decyduje,
    czy i które dni wolno usunąć. Jeśli cokolwiek jest nie tak, to blokuje
    usuwanie w całości.

    Zabezpieczenia po kolei:
        1. Backup musi się udać (backup_ok)
        2. Muszą istnieć stare dni do usunięcia
        3. Każdy dzień di usunięcia musi być potwierdzony w archiwum

    :param server_dates: daty obecne na serwerze
    :param archive_paths: ścieżki do archiwum backupu
    :param keep_last_n: ile ostatnich dni zostawić
    :param backup_ok: czy backup zakończył się sukcesem
    :return: DeletionPlan - decyzja z uzasadnieniem
    """
    if not backup_ok:
        return DeletionPlan(
            allowed=False,
            reason="Backup nie powiódł się - usuwanie zablokowane"
        )

    candidates = days_to_delete(server_dates, keep_last_n)

    if not candidates:
        return DeletionPlan(
            allowed=False,
            reason=f"Brak dni do usunięcia (zostawiamy ostatnie {keep_last_n})"
        )

    covered, missing = verify_backup_covers_days(archive_paths, candidates)
    if not covered:
        return DeletionPlan(
            allowed=False,
            reason=f"Backup nie zawiera dni: {missing} - usuwanie zablokowane"
        )

    return DeletionPlan(
        allowed=True,
        to_delete=candidates,
        reason=f"Zweryfikowano. Do usunięcia {len(candidates)} dni, "
               f"zostają ostatnie {keep_last_n}"
    )


def list_server_dates(server: str, remote_data_dir: str, dataset: str = "trip_updates") -> list[str]:
    """
    Pobiera z serwera listę dat obecnych w danych (poprzez SSH)

    :param server: adres serwera, czyli np. 'nazwa@11.111.1.11'
    :param remote_data_dir: katalog danych na serwerze
    :param dataset: typ danych, po których listujemy dni
    :return: posortowana lista dat na serwerze
    :raises RuntimeError: gdy polecenie SSH się nie powiedzie
    """
    remote_path = f"{remote_data_dir}/raw/{dataset}"
    cmd = ["ssh", server, f"ls {remote_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Nie udało się odczytać dni z serwera: {result.stderr.strip()}")
    folders = result.stdout.split()
    return parse_date_folders(folders)


def list_archive_contents(archive_path: str) -> list[str]:
    """
    Listuje zawartość archiwum .tar.gz (lokalnie).

    :param archive_path: ścieżka do pliku archiwum
    :return: lista ścieżek w archiwum
    :raises RuntimeError: gdy archiwum jest uszkodzone lub nieczytelne
    """
    cmd = ["tar", "-tzf", archive_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Archiwum nieczytelne lub uszkodzone: {result.stderr.strip()}")
    return result.stdout.splitlines()


def delete_server_day(server: str, remote_data_dir: str, date: str) -> None:
    """
    Usuwa jeden dzień ze wszystkich typów danych na serwerze (poprzez SSH).
    Wywoływane tylko dla dni zatwierdzonych przez plan_detection

    :param server: adres serwera
    :param remote_data_dir: katalog danych na serwerze
    :param date: data do usunięcia, np. '2026-10-27'
    :raises RuntimeError: gdy usuwanie się nie powiedzie
    """
    # Usunięty zostanie folder date=... we wszystkich typach (raw/*/date=...)
    remote_glob = f"{remote_data_dir}/raw/*/date={date}"
    cmd = ["ssh", server, f"sudo rm -rf {remote_glob}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Nie udało się usunąć dnia {date}: {result.stderr.strip()}")


