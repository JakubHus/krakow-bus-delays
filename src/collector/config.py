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