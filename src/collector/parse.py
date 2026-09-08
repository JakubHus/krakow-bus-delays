"""Parsowanie komunikatów GTFS-RT na wiersze gotowe do zapisu"""

from google.transit import gtfs_realtime_pb2

def _clean_time(value: int) -> int | None:
    """
    Znaczniki czasu w GTFS-RT to czas unixowy.
    0 = północ 1970 roku, co dla rozkładu jazdy jest niemożliwe,
    feed używa jej jako brak danych (np. przyjazd na pierwszym przystanku, odjazd z ostatniego).
    Zamieniamy ją na None. Dotyczy to TYLKO czasu.
    """
    return value if value != 0 else None

def _first_translation(translated_string) -> str | None:
    """
    Wyłuskuje tekst z pola TranslatedString (header_text, description_text, url).
    ZTP nie oznacza języka etykietą, więc bierzemy pierwsze dostępne tłumaczenie.
    Gdy tekstu nie ma - None.
    """
    if not translated_string.translation:
        return None
    return translated_string.translation[0].text or None


def parse_trip_updates(feed: gtfs_realtime_pb2.FeedMessage,
                       observed_at: int,
                       feed_code: str) -> list[dict]:
    """
    Zamienia komunikat TripUpdates na listę wierszy.
    Jeden wiersz = jedna para (kurs, przystanek)

    :param feed: rozpakowany komunikat GTFS-RT
    :param observed_at: epoch UTC momentu pobrania (czas zebrania)
    :param feed_code: kod feedu (A/M/T), zapisany w każdym wierszu
    :return: lista słowników, każdy to jeden stop_time_update
    """
    header_ts = feed.header.timestamp or None
    rows = []

    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
        tu = entity.trip_update
        trip = tu.trip
        vehicle = tu.vehicle if tu.HasField("vehicle") else None

        # Pola wspólne dla wszystkich przystanków tego kursu
        trip_fields = {
            "observed_at": observed_at,
            "header_ts": header_ts,
            "feed": feed_code,
            "trip_id": trip.trip_id or None,
            "route_id": trip.route_id or None,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
            "start_date": trip.start_date or None,
            "trip_schedule_relationship": trip.schedule_relationship if trip.HasField("schedule_relationship") else None,
            "vehicle_id": (vehicle.id or None) if vehicle else None,
            "vehicle_label": (vehicle.label or None) if vehicle else None
        }

        for stu in tu.stop_time_update:
            has_arrival = stu.HasField("arrival")
            has_departure = stu.HasField("departure")

            rows.append({
                **trip_fields,
                "stop_sequence": stu.stop_sequence if stu.HasField("stop_sequence") else None,
                "stop_id": stu.stop_id or None,
                "arrival_delay": stu.arrival.delay if has_arrival else None,
                "arrival_time": _clean_time(stu.arrival.time) if has_arrival else None,
                "departure_delay": stu.departure.delay if has_departure else None,
                "departure_time": _clean_time(stu.departure.time) if has_departure else None,
                "stop_schedule_relationship": stu.schedule_relationship if stu.HasField("schedule_relationship") else None,
            })
    return rows

def parse_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage,
                            observed_at: int,
                            feed_code: str) -> list[dict]:
    """
    Zamienia komunikat VehiclePositions na listę wierszy.
    Jeden wiersz = jeden pojazd (pojedyncza pozycja GPS)

    :param feed: rozpakowany komunikat GTFS-RT
    :param observed_at: epoch UTC momentu pobrania (czas zebrania)
    :param feed_code: kod feedu (A/M/T), zapisywany w każdym wierszu
    :return: lista słowników, każdy to jeden pojazd
    """
    header_ts = feed.header.timestamp or None
    rows = []

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vp = entity.vehicle
        trip = vp.trip if vp.HasField("trip") else None
        pos = vp.position if vp.HasField("position") else None
        vehicle = vp.vehicle if vp.HasField("vehicle") else None

        rows.append({
            "observed_at": observed_at,
            "header_ts": header_ts,
            "feed": feed_code,
            "trip_id": (trip.trip_id or None) if trip else None,
            "route_id": (trip.route_id or None) if trip else None,
            "direction_id": trip.direction_id if trip and trip.HasField("direction_id") else None,

            "latitude": pos.latitude if pos else None,
            "longitude": pos.longitude if pos else None,
            "bearing": pos.bearing if pos and pos.HasField("bearing") else None,
            "speed": pos.speed if pos and pos.HasField("speed") else None,

            # status na trasie
            "current_stop_sequence": vp.current_stop_sequence if vp.HasField("current_stop_sequence") else None,
            "current_status": vp.current_status if vp.HasField("current_status") else None,
            "stop_id": vp.stop_id or None,

            # własny znacznik czasu pojazdu
            "vehicle_timestamp": vp.timestamp if vp.HasField("timestamp") else None,
            "vehicle_id": (vehicle.id or None) if vehicle else None,
            "vehicle_label": (vehicle.label or None) if vehicle else None,

            # zapełnienie autobusu
            "occupancy_status": vp.occupancy_status if vp.HasField("occupancy_status") else None,
        })
    return rows


def parse_service_alerts(feed: gtfs_realtime_pb2.FeedMessage,
                         observed_at: int,
                         feed_code: str) -> list[dict]:
    """
    Zamienia komunikat ServiceAlerts na listę wierszy.
    Jeden wiersz = jedna para (alert, encja).
    Alert bez encji -> jeden wiersz z pustymi polami informed_*,
    żeby sam alert nie zniknął.

    :param feed: rozpakowany komunikat GTFS-RT
    :param observed_at: epoch UTC momentu pobrania (czas zebrania)
    :param feed_code: kod feedu (A/M/T)
    :return: lista słowników, pusta gdy brak alertów
    """
    header_ts = feed.header.timestamp or None
    rows = []

    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert

        # pola wspólne dla całego alertu
        alert_fields = {
            "observed_at": observed_at,
            "header_ts": header_ts,
            "feed": feed_code,
            "alert_id": entity.id or None,
            "cause": alert.cause if alert.HasField("cause") else None,
            "effect": alert.effect if alert.HasField("effect") else None,
            "header_text": _first_translation(alert.header_text),
            "description_text": _first_translation(alert.description_text)
        }

        if len(alert.informed_entity) == 0:
            # Alert bez wskazanej encji -> zapisujemy sam alert, pola puste
            rows.append({
                **alert_fields,
                "informed_agency_id": None,
                "informed_route_id": None,
                "informed_stop_id": None,
                "informed_trip_id": None
            })
        else:
            # Jeden wiersz za każdą encję
            for ie in alert.informed_entity:
                rows.append({
                    **alert_fields,
                    "informed_agency_id": ie.agency_id or None,
                    "informed_route_id": ie.route_id or None,
                    "informed_stop_id": ie.stop_id or None,
                    "informed_trip_id": (ie.trip.trip_id or None) if ie.HasField("trip") else None,
                })
    return rows