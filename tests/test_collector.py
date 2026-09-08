"""Testy kolektora"""

from unittest.mock import patch, Mock

from google.transit import gtfs_realtime_pb2

from src.collector.collector import (
    collect_one_feed,
    run_one_cycle,
    run_forever,
    PARSERS
)


def _build_trip_updates_bytes():
    """Buduje prawdziwe bajty protobuf TripUpdates (jeden kurs, jeden przystanek)."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1788561398
    entity = feed.entity.add()
    entity.id = "t1"
    tu = entity.trip_update
    tu.trip.trip_id = "20260904_test"
    tu.trip.route_id = "179"
    stu = tu.stop_time_update.add()
    stu.stop_sequence = 1
    stu.stop_id = "13065"
    stu.departure.delay = 30
    return feed.SerializeToString()


def _fake_ok_response(content):
    """Sztuczna udana odpowiedź HTTP z podanymi bajtami"""
    resp = Mock()
    resp.content = content
    resp.status_code = 200
    resp.raise_for_status = Mock()
    return resp


def test_parsers_cover_all_datasets():
    """Tabelka PARSERS ma wpis dla każdego typu danych z konfiguracji"""
    from src.collector.config import RT_DATASETS
    assert set(PARSERS.keys()) == set(RT_DATASETS.keys())


def test_collect_one_feed_success_writes_file(tmp_path):
    """Udany cykl: pobiera, parsuje, zapisuje plik i zwraca ok=True"""
    content = _build_trip_updates_bytes()

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)):
        result = collect_one_feed("trip_updates", "A", tmp_path)

    assert result.fetch_ok is True
    assert result.parse_ok is True
    # plik danych powstał w oczekiwanej partycji
    written = list(tmp_path.rglob("*.parquet"))
    assert len(written) == 1
    assert "trip_updates" in written[0].parts
    assert "feed=A" in written[0].parts


def test_collect_one_feed_failure_writes_nothing(tmp_path):
    """Nieudane pobranie: żaden plik nie powstaje -> wynik ma ok=False"""
    import requests
    with patch("src.collector.fetch.requests.get",
               side_effect=requests.exceptions.ConnectTimeout("timeout")):
        result = collect_one_feed("trip_updates", "A", tmp_path)

    assert result.fetch_ok is False
    assert result.parse_ok is None
    # Żadnych plików Parquet
    assert list(tmp_path.rglob("*.parquet")) == []


def test_collect_one_feed_empty_feed_no_file(tmp_path):
    """Pusty feed (0 encji): pobranie ok, ale nie ma czego zapisać"""
    empty = gtfs_realtime_pb2.FeedMessage()
    empty.header.gtfs_realtime_version = "2.0"
    empty.header.timestamp = 1788561398
    content = empty.SerializeToString()

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)):
        result = collect_one_feed("service_alerts", "A", tmp_path)

    assert result.fetch_ok is True # pobranie się udało
    assert result.parse_ok is True
    assert list(tmp_path.rglob("*.parquet")) == [] # ale plik nie powstał


def test_collect_one_feed_data_is_correct(tmp_path):
    """Zapisane dane odpowiadają temu, co było w feedzie"""
    import pandas as pd
    content = _build_trip_updates_bytes()

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)):
        collect_one_feed("trip_updates", "A", tmp_path)

    written = list(tmp_path.rglob("*.parquet"))[0]
    df = pd.read_parquet(written)
    assert df.iloc[0]["route_id"] == "179"
    assert df.iloc[0]["departure_delay"] == 30


def test_run_one_cycle_all_success(tmp_path):
    """Cykl przy działającej sieci: 9 prób, wszystkie udane."""
    content = _build_trip_updates_bytes()
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)):
        fetch_outcomes, parse_outcomes = run_one_cycle(raw_dir, logs_dir)

    assert len(fetch_outcomes) == 9       # 9 prób pobrania
    assert all(fetch_outcomes) is True    # wszystkie pobrania udane
    assert all(parse_outcomes) is True    # wszystkie parsowania udane

    # log kompletności powstał
    log_files = list(logs_dir.rglob("poll_log.csv"))
    assert len(log_files) == 1


def test_run_one_cycle_all_fail(tmp_path):
    """Cykl przy padniętej sieci: 9 prób, wszystkie nieudane."""
    import requests
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"

    with patch("src.collector.fetch.requests.get",
               side_effect=requests.exceptions.ConnectTimeout("timeout")):
        fetch_outcomes, parse_outcomes = run_one_cycle(raw_dir, logs_dir)

    assert len(fetch_outcomes) == 9
    assert not any(fetch_outcomes)              # żadna próba pobrania się nie udała
    # parsowań nie było wcale, więc historia parsowania jest pusta
    assert parse_outcomes == []
    # żadnych plików danych
    assert list(raw_dir.rglob("*.parquet")) == []
    # ale log i tak powstał — z zapisem błędów
    assert len(list(logs_dir.rglob("poll_log.csv"))) == 1


def test_run_one_cycle_logs_all_attempts(tmp_path):
    """Log zawiera wpis o każdej z 9 prób."""
    import pandas as pd
    content = _build_trip_updates_bytes()
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)):
        run_one_cycle(raw_dir, logs_dir)

    log_file = list(logs_dir.rglob("poll_log.csv"))[0]
    log = pd.read_csv(log_file)
    assert len(log) == 9                  # 9 wpisów w logu


def test_run_forever_stops_after_max_cycles(tmp_path):
    """max_cycles ogranicza liczbę cykli -> pętla nie wisi w nieskończoność"""
    content = _build_trip_updates_bytes()
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"
    static_dir = tmp_path / "static"

    # Mockujemy sieć (sukces) oraz sleep (żeby test nie czekał naprawdę)
    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)), \
         patch("src.collector.collector.check_static_schedules"), \
         patch("src.collector.collector.time.sleep") as mock_sleep:
        run_forever(raw_dir, logs_dir, static_dir, max_cycles=3)

    # 3 cykle -> sleep wywołany 2 razy (po ostatnim cyklu nie śpimy)
    assert mock_sleep.call_count == 2


def test_run_forever_writes_data_each_cycle(tmp_path):
    """Każdy cykl pętli zapisuje dane"""
    content = _build_trip_updates_bytes()
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"
    static_dir = tmp_path / "static"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)), \
         patch("src.collector.collector.time.sleep"):
        run_forever(raw_dir, logs_dir, static_dir, max_cycles=2)

    # log powstał i ma wpisy z dwóch cykli: 2 * 9 prób = 18
    import pandas as pd
    log_file = list(logs_dir.rglob("poll_log.csv"))[0]
    assert len(pd.read_csv(log_file)) == 18


def test_run_forever_unhealthy_warns(tmp_path, caplog):
    """Przy padniętej sieci pętla loguje ostrzeżenie o problemie"""
    import requests
    import logging
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"
    static_dir = tmp_path / "static"

    with patch("src.collector.fetch.requests.get",
               side_effect=requests.exceptions.ConnectTimeout("timeout")), \
         patch("src.collector.collector.time.sleep"), \
         caplog.at_level(logging.WARNING):
        run_forever(raw_dir, logs_dir, static_dir, max_cycles=5)

    # gdzieś padło ostrzeżenie o problemie z pobieraniem
    assert any("problem z pobieraniem" in msg.lower() for msg in caplog.messages)


def test_collect_one_feed_corrupt_data_survives(tmp_path):
    """Obcięte/wadliwe bajty → parse_ok=False, ale funkcja nie rzuca błędu"""
    # Bajty, które nie są poprawnym protobuf GTFS-RT
    garbage = b"\xff\xfe to nie jest protobuf \x00\x01\x02"

    fake = Mock()
    fake.content = garbage
    fake.status_code = 200
    fake.raise_for_status = Mock()

    with patch("src.collector.fetch.requests.get", return_value=fake):
        result = collect_one_feed("trip_updates", "A", tmp_path)

    # pobranie się udało, ale parsowanie nie i to nie wywaliło funkcji
    assert result.fetch_ok is True
    assert result.parse_ok is False
    # żaden plik nie powstał, bo nie było czego zapisać
    assert list(tmp_path.rglob("*.parquet")) == []


def test_run_forever_checks_static_on_start(tmp_path):
    """Rozkład statyczny sprawdzany jest raz na starcie pętli"""
    content = _build_trip_updates_bytes()
    raw_dir = tmp_path / "raw"
    logs_dir = tmp_path / "logs"
    static_dir = tmp_path / "static"

    with patch("src.collector.fetch.requests.get",
               return_value=_fake_ok_response(content)), \
         patch("src.collector.collector.check_static_schedules") as mock_check, \
         patch("src.collector.collector.time.sleep"):
        run_forever(raw_dir, logs_dir, static_dir, max_cycles=1)

    # sprawdzenie rozkładu wywołane co najmniej raz (na starcie)
    assert mock_check.call_count >= 1