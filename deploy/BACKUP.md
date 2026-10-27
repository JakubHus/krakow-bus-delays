# Backup i czyszczenie danych

Kolektor zapisuje dane w sposób ciągły, więc ich ilość stale rośnie
(ok. `0.7-0.8 GB na dobę` przy trzech feedach ZTP). Dysk serwera
ma ograniczoną pojemność, dlatego trzeba okresowo:

1. **Ściągać dane** na własny dysk (backup)
2. **Usuwać stare dni** z serwera, gdy miejsca zaczyna brakować

**Zasada nadrzędna:** nic nie jest usuwane z serwera, dopóki nie znajduje się
w zweryfikowanym backupie. Kolejność jest zawsze ta sama: **najpierw backup, potem czyszczenie.**

W poniższych komendach podmień wartości w `<...>` na własne:

- `<user>@<host>` - użytkownik i adres serwera (np. `nazwa@203.0.113.10`)
- `<ścieżka-dysku>` - katalog na kopie na lokalnym dysku
- `<RRRR-MM-DD>` - dzisiejsza data w nazwie pliku backupu

---

## Wymagania 

Po stronie komputera, z którego jest robiony backup, potrzebne są `ssh` i `tar`.
Na Windowsie najwygodniej używać **Git Bash** (zawiera oba i spójnie obsługuje
ścieżki). Na Linuxie i macOS są dostępne standardowo.

Narzędzie czyszczące (`cleanup_tool.py`) wymaga Pythona z zależnościami
projektu (requirements.txt).

---

## Krok 1 - Backup

Backup wykonuje się **z komputera lokalnego** (nie na serwerze).
Podłączamy dysk docelowy i uruchamiamy:

```bash
mkdir -p <ścieżka-dysku>/backup
ssh <user>@<host> "sudo tar -czf - -C /opt/ztp-collector data" > <ścieżka-dysku>/backup/ztp-backup-<RRRR-MM-DD>.tar.gz
```

Metoda jest strumieniowa: dane pakowane są na serwerze i przesyłane od razu
do pliku na dysku lokalnym, **bez zajmowania miejsca na serwerze**, co jest
istotne, gdy na serwerze brakuje przestrzeni na całe archiwum.

Wskazówki:
- Transfer kilkunastu GB trwa kilkadziesiąt minut. Nie przerywaj połączenia i nie pozwól komputerowi przejść w stan uśpienia.
- Każdy backup ma datę w nazwie, więc **nie nadpisuj** poprzednich. Starsze kopie stanowią dodatkowe zabezpieczenie.

---

## Krok 2 - Weryfikacja backupu

Przed jakimkolwiek usuwaniem upewnij się, że archiwum nie jest uszkodzone:

```bash
tar -tzf <ścieżka-dysku>/backup/ztp-backup-<RRRR-MM-DD>.tar.gz | head -5
```

Poprawny backup wypisze ścieżki zaczynające się od `data/`.
Jeśli `tar` zgłosi błąd, to backup jest nieudany. Powtórz krok 1
i **nie usuwaj danych**.

---

## Krok 3 - Czyszczenie serwera

Do usuwania starych danych służy `cleanup_tool.py`. Narzędzie ma wbudowane
zabezpieczenia i **odmawia usunięcia dnia, którego nie ma we wskazanym backupie**.

## Tryb próbny (dry-run) - zawsze przed właściwym usuwaniem

Pokazuje planowane działania, niczego nie usuwając. Można go uruchamiać
dowolnie wiele razy:

```bash
python cleanup_tool.py --server <user>@<host> --archive "<ścieżka-dysku>/backup/ztp-backup-<RRRR-MM-DD>.tar.gz"
```

Narzędzie wypisze, które dni zostałyby usunięte, a które zostają.
Domyślnie zachowuje ostatnie 7 dni (parametr `--keep`).
Jeśli dostępnych dni jest nie więcej niż próg, to nic nie zostanie
zaplanowane do usunięcia.

## Tryb usuwania - dopiero po sprawdzeniu planu

Faktyczne usuwanie włącza flaga `--execute`:

```bash
python cleanup_tool.py --server <user>@<host> --archive "<ścieżka-dysku>/backup/ztp-backup-<RRRR-MM-DD>.tar.gz" --execute
```

Narzędzie odmawia usuwania, gdy:
- wskazane archiwum jest nieczytelne lub uszkodzone,
- nie ma bezpiecznego nadmiaru dni (`--keep`)
- którykolwiek dzień przeznaczony do usunięcia nie występuje w backupie.

Bez flagi `--execute` narzędzie działa wyłącznie w trybie próbnym.
Danych nie da się usunąć przez pominięcie flagi.

### Parametry
 
| Parametr    | Znaczenie                              | Domyślnie |
|-------------|----------------------------------------|-----------|
| `--server`  | użytkownik i adres serwera             | (wymagany)|
| `--archive` | ścieżka do istniejącego backupu        | (wymagany)|
| `--keep`    | ile ostatnich dni zachować na serwerze | 7         |
| `--execute` | wykonaj usuwanie                       | wyłączone |
 
---

## Krok 4 - Potwierdzenie

Po czyszczeniu warto sprawdzić, że miejsce zostało zwolnione,
a na serwerze pozostały właściwe dni:

```bash
ssh <user>@<host> "df -h / && ls /opt/ztp-collector/data/raw/trip_updates/"
```

---

## Odtworzenie danych backupu

Backupy to standardowe archiwa `.tar.gz`. Aby rozpakować
(np. na potrzeby analizy danych):

```bash
tar -xzf <ścieżka-dysku>/backup/ztp-backup-<RRRR-MM-DD>.tar.gz -C <katalog-docelowy>/
```

W katalogu docelowym pojawi się folder `data/` z pełną strukturą partycji
(`data/raw/<typ>/date=.../hour=.../feed=.../*.parquet`
oraz `data/static/`, `data/logs/`).