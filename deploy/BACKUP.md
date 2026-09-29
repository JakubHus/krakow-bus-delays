# Backup danych kolektora

Dane kolektora żyją na serwerze i muszą być regularnie kopiowane na
własny dysk, aby chronić przed ich utratą.

Zasada: dane istnieją naprawdę dopiero, gdy są w dwóch miejscach.

## Jak zrobić backup

Z własnego komputera, w folderze `deploy/`:

```bash
./backup.sh uzytkownik@ADRES_IP  D:/kmk-backup
```

Podmień `uzytkownik@ADRES_IP` na dane swojego serwera, a `D:/kmk-backup`
na katalog na dysku, gdzie chcesz trzymać kopię.

Pierwszy backup ściągnie wszystko. Kolejne - tylko nowe pliki (rsync
kopiuje wyłącznie przyrost), więc trwają krótko.

## Jak często

Co najmniej raz w tygodniu. Im częściej, tym mniej danych ryzykujemy
stracić przy awarii serwera.

## Windows

`rsync` i `ssh` działają w PowerShell na nowszych Windowsach. Jeśli `rsync`
nie jest rozpoznawane, użyj Git Bash albo
WSL - oba mają `rsync` standardowo.

## Odtworzenie danych na nowym serwerze

Gdy stawiamy kolektor od nowa i chcemy
kontynuować z dotychczasowymi danymi, wgrywamy kopię z powrotem:

```bash
rsync -avz -e "ssh" D:/kmk-backup/data/  uzytkownik@NOWY_IP:/opt/ztp-collector/data/
```