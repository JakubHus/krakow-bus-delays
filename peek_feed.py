import requests

URL = "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"
headers = {"User-Agent": "krakow-bus-delays research (husjakub24@gmail.com)"}

response = requests.get(URL, headers=headers, timeout=20)
response.raise_for_status()

print(f"status HTTP: {response.status_code}")
print(f"rozmiar: {len(response.content)}")
print(f"pierwsze bajty: {response.content[:16]!r}")