"""Test parsera GTFS-RT"""

from google.transit import gtfs_realtime_pb2
from src.collector.parse import parse_trip_updates

def _build_feed_with_one_trip():
    """Buduje sztuczny komunikat z jednym kursem o dwóch przystankach"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"

    entity = feed.entity.add()
    entity.id = "test_trip"
    tu = entity.trip_update
    tu.trip.trip_id = "20260901_test_1"
    tu.trip.route_id = "476"

    # przystanek 1
    s1 = tu.stop_time_update.add()
    s1.stop_sequence = 1
    s1.stop_id = "13065"
    s1.departure.delay = 0

    # przystanek 2
    s2 = tu.stop_time_update.add()
    s2.stop_sequence = 2
    s2.stop_id = "11951"
    s2.arrival.delay = 65
    s2.departure.delay = 65

    return feed

def test_parses_all_stop_updates():
    "Parser powinien zwrócić po jednym wierszu na każdy przystanek"
    feed = _build_feed_with_one_trip()
    rows = parse_trip_updates(feed, observed_at=1788544966, feed_code="A")
    assert len(rows) == 2

def test_extracts_delay_correctly():
    """Sprawdzamy czy opóźnienie 65s trafia do właściwego wiersza"""
    feed = _build_feed_with_one_trip()
    rows = parse_trip_updates(feed, observed_at=1788544966, feed_code="A")
    assert rows[1]["arrival_delay"] == 65
    assert rows[1]["stop_id"] == "11951"

def test_preserves_metadata():
    feed = _build_feed_with_one_trip()
    rows = parse_trip_updates(feed, observed_at=1788544966, feed_code="A")
    assert all(r["observed_at"] == 1788544966 for r in rows)
    assert all(r["feed"] == "A" for r in rows)