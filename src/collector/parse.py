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
            "trip_shedule_relationship": trip.trip_shedule_relationship if trip.HasField("schedule_relationship") else None,
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