import requests
from google.transit import gtfs_realtime_pb2

URL = "https://gtfs.ztp.krakow.pl/VehiclePositions_A.pb"
headers = {"User-Agent": "krakow-bus-delays research (husjakub24@gmail.com)"}

response = requests.get(URL, headers=headers, timeout=20)
response.raise_for_status()

# Tworzymy miejsce na przechowanie komunikatu GTFS-RT i wrzucamy tam surowe bajty
# Biblioteka sama je rozszyfrowuje
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

# Nagłówek: wersja specyfikacji i moment wygenerowania migawki
print("Wersja GTFS-RT: ", feed.header.gtfs_realtime_version)
print("Znacznik czasu: ", feed.header.timestamp)
print("Liczba encji: ", len(feed.entity))
print("-"*50)

# Pierwsza encja i jej struktura - surowy podgląd
first = feed.entity[0]
print(first)