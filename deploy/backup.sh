#!/usr/bin/env bash
# Backup danych kolektora ZTP z serwera na lokalny dysk.

# Ściąga tylko nowe lub zmienione pliki (rsync), więc kolejne uruchomienia są szybkie.
# Użycie:
# ./backup.sh uzytkownik@ADRES_IP  /sciezka/do/kopii

# Przykład:
# ./backup.sh azureuser@20.101.x.x  D:/kmk-backup

set -euo pipefail

SERVER="${1:?Podaj serwer: uzytkownik@IP}"
DEST="${2:?Podaj katalog docelowy kopii}"

echo "Backup z ${SERVER}:${REMOTE_DATA}"
echo "     do ${DEST}"
echo

mkdir -p "${DEST}"

# -a -> zachowaj strukturę, czasy, uprawnienia
# -v -> pokaż co się kopiuje
# -z -> kompresuj w trakcie przesyłania
# --progress -> pasek postępu

rsync -avz --progress \
    -e "ssh" \
    "${SERVER}:${REMOTE_DATA}" \
    "${DEST}/data/"

echo
echo "Gotowe. Kopia w: ${DEST}/data/"