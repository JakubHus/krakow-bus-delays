"""Parsowanie komunikatów GTFS-RT na wiersze gotowe do zapisu"""

from google.transit import gtfs_realtime_pb2

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
    rows = []
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
        tu = entity.trip_update
        trip = tu.trip

        for stu in tu.stop_time_update:
            has_arrival = stu.HasField("arrival")
            has_departure = stu.HasField("departure")

            rows.append({
                "observed_at": observed_at,
                "feed": feed_code,
                "trip_id": trip.trip_id or None,
                "route_id": trip.route_id or None,
                "stop_sequence": stu.stop_sequence or None,
                "stop_id": stu.stop_id or None,
                "arrival_delay": stu.arrival.delay if has_arrival is not None else None,
                "departure_delay": stu.departure.delay if has_departure is not None else None
            })
    return rows