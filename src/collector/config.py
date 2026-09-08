"""Stałe konfiguracyjne kolektora GTFS-RT ZTP Kraków"""

BASE_URL = "https://gtfs.ztp.krakow.pl"

# Kody feedów według ZTP. Przypisanie do rodzaju taboru (autobusy miejskie / aglomeracyjne / tramwaje)
# TODO: potwierdzić to w dalszej części
FEED_CODES = ["A", "M", "T"]

# Trzy strumienie danych
# Wartość = przedrostek pliku .pb na serwerze.
RT_DATASETS = {
    "trip_updates": "TripUpdates",
    "vehicle_positions": "VehiclePositions",
    "service_alerts": "ServiceAlerts"
}

# Nagłówek dla ZTP
USER_AGENT = "krakow-bus-delays research (husjakub24@gmail.com)"

# --- Monitoring: progi wykrywania awarii pobierania ---
# Alarm, gdy spełniony JEDEN z warunków:
HEALTH_MAX_CONSECUTIVE_ERRORS = 5      # tyle błędów POD RZĄD = nagła awaria
HEALTH_WINDOW_SIZE = 15                # rozmiar okna "ostatnich N prób"
HEALTH_MAX_ERRORS_IN_WINDOW = 8        # tyle błędów w oknie = awaria przerywana

# --- Pętla kolektora ---
POLL_INTERVAL_SECONDS = 15    # odstęp między cyklami pobierania
HEALTH_HISTORY_SIZE = 60      # ile ostatnich wyników trzymać do oceny zdrowia