"""Test parsera GTFS-RT"""

from google.transit import gtfs_realtime_pb2
from src.collector.parse import (
    parse_trip_updates,
    parse_vehicle_positions,
    parse_service_alerts,
    _clean_time
)

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
    tu.trip.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.SCHEDULED
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


def _build_vehicle_feed():
    """Sztuczny komunikat VehiclePositions"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1788556784

    entity = feed.entity.add()
    entity.id = "vehicle_DA155"
    vp = entity.vehicle
    vp.trip.trip_id = "20260901_4_127904828_33"
    vp.trip.route_id = "175"
    vp.trip.direction_id = 0
    vp.position.latitude = 49.9828
    vp.position.longitude = 19.9206791
    vp.position.bearing = 20
    vp.position.speed = 8
    vp.current_stop_sequence = 11
    vp.current_status = gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO
    vp.stop_id = "10226"
    vp.timestamp = 1788556776
    vp.vehicle.id = "DA155"
    vp.vehicle.label = "155"
    vp.occupancy_status = gtfs_realtime_pb2.VehiclePosition.NO_DATA_AVAILABLE

    return feed


def test_vehicle_one_row_per_vehicle():
    """Jeden pojazd -> jeden wiersz"""
    rows = parse_vehicle_positions(_build_vehicle_feed(), 1788556790, "A")
    assert len(rows) == 1

def test_vehicle_coordinates_use_approx():
    """Sprawdzenie przybliżonych wartości koordynatów"""
    import pytest
    rows = parse_vehicle_positions(_build_vehicle_feed(), 1788556790, "A")
    assert rows[0]["latitude"] == pytest.approx(49.9828, abs=1e-4)
    assert rows[0]["longitude"] == pytest.approx(19.920679, abs=1e-4)

def test_vehicle_status_and_occupancy_kept_raw():
    """Surowy zapis statusu i zapełnienia autobusu"""
    rows = parse_vehicle_positions(_build_vehicle_feed(), 1788556790, "A")
    assert rows[0]["occupancy_status"] == gtfs_realtime_pb2.VehiclePosition.NO_DATA_AVAILABLE
    assert rows[0]["current_status"] == gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO

def test_vehicle_metadata():
    rows = parse_vehicle_positions(_build_vehicle_feed(), 1788556790, "A")
    assert rows[0]["observed_at"] == 1788556790
    assert rows[0]["feed"] == "A"
    assert rows[0]["header_ts"] == 1788556784
    assert rows[0]["vehicle_timestamp"] == 1788556776


def _build_alert_feed(with_entities=True):
    """Sztuczny ServiceAlerts"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1788561398

    entity = feed.entity.add()
    entity.id = "alert_test_1"
    alert = entity.alert

    alert.header_text.translation.add().text = "Objazd"
    alert.description_text.translation.add().text = "Wyłączenie ruchu tramwajowego"

    if with_entities:
        alert.informed_entity.add().route_id = "5"
        alert.informed_entity.add().route_id = "8"
        alert.informed_entity.add().stop_id = "10200"

    return feed


def test_alert_multiplies_into_rows():
    """Alert o 3 encjach -> 3 wiersze"""
    rows = parse_service_alerts(_build_alert_feed(), 1788561400, "T")
    assert len(rows) == 3

def test_alert_shared_text_repeated():
    """Opis alertu powtarza się w każdym wygenerowanym wierszu"""
    rows = parse_service_alerts(_build_alert_feed(), 1788561400, "T")
    assert all(r["description_text"] == "Wyłączenie ruchu tramwajowego" for r in rows)
    assert all(r["header_text"] == "Objazd" for r in rows)

def test_alert_informed_entities_split():
    """Każda encja trafia do osobnego wiersza"""
    rows = parse_service_alerts(_build_alert_feed(), 1788561400, "T")
    assert rows[0]["informed_route_id"] == "5"
    assert rows[1]["informed_route_id"] == "8"
    assert rows[2]["informed_stop_id"] == "10200"
    # przystanek nie ma route_id i odwrotnie
    assert rows[2]['informed_route_id'] is None

def test_alert_without_entities_still_one_row():
    """Alert bez żadnej encji -> i tak mamy jeden wiersz żeby alert nie zniknął"""
    rows = parse_service_alerts(_build_alert_feed(with_entities=False), 1788561400, "T")
    assert len(rows) == 1
    assert rows[0]["informed_route_id"] is None
    assert rows[0]["description_text"] == "Wyłączenie ruchu tramwajowego"

def test_empty_feed_returns_empty_list():
    """Brak alertów -> pusta lista, bez błędu"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    rows = parse_service_alerts(feed, 1788561400, "T")
    assert rows == []