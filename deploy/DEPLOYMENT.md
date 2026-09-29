# Wdrożenie kolektora GTFS-RT ZTP  na serwer

Instrukcja uruchomienia kolektora jako usługi `systemd`
na maszynie wirtualnej z systemem Ubuntu (Azure albo dowolny inny Linux-VPS)

Zakłada, że masz już postawioną maszynę z Ubuntu i możesz się z nią połączyć
przez SSH jako użytkownik z uprawnieniami `sudo`.

---

## 0. Połączenie z serwerem

Z własnego komputera (PowerShell / terminal):

```bash
ssh nazwa_uzytkownika@ADRES_IP_SERWERA
```

Adres IP znajdziesz w panelu Azure na stronie maszyny wirtualnej.
Przy pierwszym połączeniu SSH zapyta o potwierdzenie odcisku klucza.
Należy wtedy wpisać `yes`.

---

## 1. Aktualizacja systemu i instalacja Pythona

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip git
```

Sprawdź wersję Pythona (potrzebna jest 3.12+ - Ubuntu 24.04 ma ją standardowo):

```bash
python3 --version
```

---

## 2. Utworzenie użytkownika usługi

Kolektor działa jako osobny, nieuprzywilejowany użytkownik `ztp`.
Tworzymy go bez możliwości logowania:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin ztp
```

---

## 3. Pobieranie kodu z repozytorium

Kod wgrywamy przez Git do `/opt/ztp-collector`.

```bash
sudo git clone https://github.com/JakubHus/krakow-bus-delays.git /opt/ztp-collector
sudo chown -R ztp:ztp /opt/ztp-collector
```

Drugie polecenie nadaje użytkownikowi `ztp` własność katalogu, żeby kolektor
mógł w nim tworzyć folder `data/`.

---

## 4. Środowisko wirtualne i zależności

Tworzymy `.venv` i instalujemy zależności - wszystko jako użytkownik `ztp`:

```bash
sudo -u ztp python3 -m venv /opt/ztp-collector/.venv
sudo -u ztp /opt/ztp-collector/.venv/bin/pip install -r /opt/ztp-collector/requirements.txt
```
 
---

# 5. Sekrety poza repozytorium

Tworzymy katalog i plik na zmienne środowiskowe.
Ten plik nigdy nie trafia do Gita, istnieje tylko na serwerze.

```bash
sudo mkdir -p /etc/ztp-collector
sudo nano /etc/ztp-collector/collector.env
```

W edytorze `nano` wpisz:

```
SMTP_USER=husjakub24@gmail.com
SMTP_PASSWORD=twoje16znakowehaslo
ALERT_TO=husjakub24@gmail.com
```
 
Zapisz (`Ctrl+O`, `Enter`) i wyjdź (`Ctrl+X`). Zabezpiecz plik, żeby tylko
administrator mógł go czytać:
 
```bash
sudo chmod 600 /etc/ztp-collector/collector.env
```
 
---

## 6. Instalacja usługi systemd
 
Kopiujemy wzorzec usługi z repo we właściwe miejsce systemowe:
 
```bash
sudo cp /opt/ztp-collector/deploy/ztp-collector.service /etc/systemd/system/
```
 
Mówimy systemd, żeby wczytał nową usługę, włączamy ją (uruchamianie po
restarcie) i startujemy:
 
```bash
sudo systemctl daemon-reload
sudo systemctl enable ztp-collector
sudo systemctl start ztp-collector
```
 
---
 
## 7. Sprawdzenie, czy działa
 
Status usługi (powinno być `active (running)`):
 
```bash
sudo systemctl status ztp-collector
```
 
Podgląd logów na żywo (co kolektor robi w tej chwili):
 
```bash
sudo journalctl -u ztp-collector -f
```
 
(`Ctrl+C` wychodzi z podglądu — usługa działa dalej.)
 
Po kilku minutach sprawdź, czy powstają dane:
 
```bash
sudo ls -R /opt/ztp-collector/data/raw | head -30
```
 
---
 
## 8. Aktualizacja kodu na serwerze
 
Gdy poprawisz kod i wypchniesz na GitHub, na serwerze:
 
```bash
cd /opt/ztp-collector
sudo -u ztp git pull
sudo -u ztp /opt/ztp-collector/.venv/bin/pip install -r requirements.txt
sudo systemctl restart ztp-collector
```
 
Zawsze aktualizuj z `main` (kod przetestowany). Zbieranie przerywa się tylko
na chwilę restartu.
 
---
 
## 10. Backup danych — patrz BACKUP.md
 
Dane z serwera należy regularnie ściągać na własny dysk. Procedura w osobnym
pliku `deploy/BACKUP.md`.

