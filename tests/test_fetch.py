"""Testy pobierania z sieci (z mockowaniem - bez prawdziwych żądań)"""

from unittest.mock import patch, Mock

import requests
import pytest

from src.collector.fetch import fetch_url, fetch_feed, build_feed_url, FetchResult


def test_successful_fetch():
    """Udane pobranie zwraca ok=True i zawartość"""
    fake_response = Mock()
    fake_response.content = b"udawane bajty protobuf"
    fake_response.status_code = 200
    fake_response.raise_for_status = Mock() # nic nie robi -> brak błędu

    with patch("src.collector.fetch.requests.get", return_value=fake_response):
        result = fetch_url("https://przyklad.pl/feed.pb")

    assert result.ok is True
    assert result.content == b"udawane bajty protobuf"
    assert result.status_code == 200
    assert result.size_bytes == len(b"udawane bajty protobuf")
    assert result.error is None


def test_timeout_returns_error_not_exception():
    """Timeout nie wywala programu, zwraca ok==False z opisem"""
    with patch("src.collector.fetch.requests.get", side_effect=requests.exceptions.ConnectTimeout("przekroczono czas")):
        result = fetch_url("https://przyklad.pl/feed.pb")

    assert result.ok is False
    assert result.content is None
    assert "ConnectTimeout" in result.error


def test_http_error_is_caught():
    """Błąd HTTP też trafia do kontrolowanego wyniku"""
    fake_response = Mock()
    fake_response.status_code = 500
    http_error = requests.exceptions.HTTPError("500 Server Error")
    http_error.response = fake_response
    fake_response.raise_for_status = Mock(side_effect=http_error)

    with patch("src.collector.fetch.requests.get", return_value=fake_response):
        result = fetch_url("https://przyklad.pl/feed.pb")

    assert result.ok is False
    assert result.status_code == 500
    assert "HTTPError" in result.error


def test_result_always_has_url_and_time():
    """Każdy wynik (udany czy nie) ma URL i znacznik czasu"""
    with patch("src.collector.fetch.requests.get", side_effect=requests.exceptions.ConnectionError("brak sieci")):
        result = fetch_url("https://przyklad.pl/feed.pb")

    assert result.url == "https://przyklad.pl/feed.pb"
    assert result.observed_at > 0
    assert result.duration_ms is not None


def test_build_feed_url_trip_updates():
    """URL dla trip_updates z feedu A"""
    url = build_feed_url("trip_updates", "A")
    assert url == "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"


def test_build_feed_url_all_datasets():
    """Każdy typ danych daje poprawny przedrostek w URL"""
    assert "VehiclePositions_M.pb" in build_feed_url("vehicle_positions", "M")
    assert "ServiceAlerts_T.pb" in build_feed_url("service_alerts", "T")


def test_build_feed_url_unknown_dataset_raises():
    """Nieznany typ danych -> KeyError"""
    with pytest.raises(KeyError):
        build_feed_url("literowka_bez_s", "A")


def test_fetch_feed_builds_url_and_delegates():
    """fetch_feed składa URL i przekazuje go do fetch_url"""
    fake_response = Mock()
    fake_response.content = b"dane"
    fake_response.status_code = 200
    fake_response.raise_for_status = Mock()

    with patch("src.collector.fetch.requests.get", return_value=fake_response) as mock_get:
        result = fetch_feed("trip_updates", "A")

    assert result.ok is True
    # Sprawdzamy czy pobrano z właściwego URL
    called_url = mock_get.call_args[0][0]
    assert called_url == "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"