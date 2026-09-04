"""Test parsera GTFS-RT"""

from google.transit import gtfs_realtime_pb2
from src.collector.parse import parse_trip_updates, _clean_time

def _build_feed_with_one_trip():
    """Buduje sztuczny komunikat z jednym kursem o dwóch przystankach"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1788544958

    entity = feed.entity.add()
    entity.id = "test_trip"
    tu = entity.trip_update
    tu.trip.trip_id = "20260901_test_1"
    tu.trip.route_id = "476"
    tu.trip.direction_id = 1
    tu.vehicle.id = "PA147"
    tu.vehicle.label = "147"

    # przystanek 1
    s1 = tu.stop_time_update.add()
    s1.stop_sequence = 1
    s1.stop_id = "13065"
    s1.arrival.delay = 0
    s1.arrival.time = 0
    s1.departure.delay = 0
    s1.departure.time = 1788545640

    # przystanek 2
    s2 = tu.stop_time_update.add()
    s2.stop_sequence = 2
    s2.stop_id = "11951"
    s2.arrival.delay = 65
    s2.arrival.time = 1788545700
    s2.departure.delay = 65
    s2.departure.time = 178854700

    return feed

def test_parses_all_stop_updates():
    "Parser powinien zwrócić po jednym wierszu na każdy przystanek"
    rows = parse_trip_updates(_build_feed_with_one_trip(), observed_at=1788544966, feed_code="A")
    assert len(rows) == 2

def test_extracts_delay_correctly():
    """Sprawdzamy czy opóźnienie 65s trafia do właściwego wiersza"""
    rows = parse_trip_updates(_build_feed_with_one_trip(), observed_at=1788544966, feed_code="A")
    assert rows[1]["arrival_delay"] == 65
    assert rows[1]["stop_id"] == "11951"

def test_preserves_metadata():
    rows = parse_trip_updates(_build_feed_with_one_trip(), observed_at=1788544966, feed_code="A")
    assert all(r["observed_at"] == 1788544966 for r in rows)
    assert all(r["feed"] == "A" for r in rows)
    assert all(r["header_ts"] == 1788544958 for r in rows)

def test_extracts_trip_fields():
    """Pola kierunku kursu i pojazdu"""
    rows = parse_trip_updates(_build_feed_with_one_trip(), observed_at=1788544966, feed_code="A")
    assert rows[0]["direction_id"] == 1
    assert rows[0]["vehicle_id"] == "PA147"
    assert rows[0]["vehicle_label"] == "147"

def test_zero_time_becomes_none_but_zero_delay_stays():
    """Czy zerowy czas znika, ale zerowe opóźnienie zostaje"""
    rows = parse_trip_updates(_build_feed_with_one_trip(), observed_at=1788544966, feed_code="A")
    # przystanek 1 -> arrival.time = 0 -> None
    assert rows[0]["arrival_time"] is None
    # przystanek 1 -> arrival.delay = 0 -> 0 a nie None
    assert rows[0]["arrival_delay"] == 0
    # realny czas odjazdu z przystanku 1 ma zostać zachowany
    assert rows[0]["departure_time"] == 1788545640

def test_clean_time_helper():
    """Bezpośredni test funkcji pomocniczej"""
    assert _clean_time(0) is None
    assert _clean_time(1788545640) == 1788545640
