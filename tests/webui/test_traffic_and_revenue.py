"""
Unit tests for webui/stats.py's YouTube Analytics API v2 data-assembly
functions: traffic_sources(), subscriber_growth(), revenue_stats(), and
revenue_available(). Never hits the real API -- these functions accept an
optional `client=` kwarg used verbatim instead of building a real client, so
tests pass a small fake that mimics youtubeAnalytics#v2's
reports().query(**kwargs).execute() chain.
"""
from __future__ import annotations

import pytest

from webui import config, stats


@pytest.fixture(autouse=True)
def _clear_analytics_caches():
    stats._traffic_cache.update(at=0.0, data=None)
    stats._subs_cache.update(at=0.0, data=None)
    stats._revenue_cache.update(at=0.0, data=None)
    yield
    stats._traffic_cache.update(at=0.0, data=None)
    stats._subs_cache.update(at=0.0, data=None)
    stats._revenue_cache.update(at=0.0, data=None)


class _Exec:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _Reports:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return _Exec(self._response)


class FakeAnalyticsClient:
    def __init__(self, response):
        self._reports = _Reports(response)

    def reports(self):
        return self._reports


class _RaisingClient:
    def reports(self):
        raise RuntimeError("simulated API error")


# ── traffic_sources ──────────────────────────────────────────────────────────
def test_traffic_sources_shapes_rows_sorted_as_returned():
    response = {"rows": [["SUBSCRIBER", 100, 5], ["YT_SEARCH", 50, 1]]}
    client = FakeAnalyticsClient(response)

    result = stats.traffic_sources(client=client)

    assert result == [
        {"source": "SUBSCRIBER", "views": 100, "subs_gained": 5},
        {"source": "YT_SEARCH", "views": 50, "subs_gained": 1},
    ]


def test_traffic_sources_queries_expected_dimension_and_metrics():
    client = FakeAnalyticsClient({"rows": []})
    stats.traffic_sources(client=client)
    kwargs = client._reports.calls[0]
    assert kwargs["dimensions"] == "insightTrafficSourceType"
    assert kwargs["metrics"] == "views,subscribersGained"


def test_traffic_sources_empty_rows_returns_empty_list():
    client = FakeAnalyticsClient({"rows": []})
    assert stats.traffic_sources(client=client) == []


def test_traffic_sources_returns_none_on_api_error():
    assert stats.traffic_sources(client=_RaisingClient()) is None


def test_traffic_sources_caches_within_ttl():
    client = FakeAnalyticsClient({"rows": [["SUBSCRIBER", 1, 1]]})
    stats.traffic_sources(client=client)
    stats.traffic_sources(client=client)
    assert len(client._reports.calls) == 1


def test_traffic_sources_force_bypasses_cache():
    client = FakeAnalyticsClient({"rows": [["SUBSCRIBER", 1, 1]]})
    stats.traffic_sources(client=client)
    stats.traffic_sources(force=True, client=client)
    assert len(client._reports.calls) == 2


# ── subscriber_growth ────────────────────────────────────────────────────────
def test_subscriber_growth_computes_net():
    response = {"rows": [["2026-08-01", 20, 5], ["2026-08-02", 3, 10]]}
    client = FakeAnalyticsClient(response)

    result = stats.subscriber_growth(client=client)

    assert result == [
        {"date": "2026-08-01", "gained": 20, "lost": 5, "net": 15},
        {"date": "2026-08-02", "gained": 3, "lost": 10, "net": -7},
    ]


def test_subscriber_growth_queries_expected_metrics_and_dimension():
    client = FakeAnalyticsClient({"rows": []})
    stats.subscriber_growth(client=client)
    kwargs = client._reports.calls[0]
    assert kwargs["dimensions"] == "day"
    assert kwargs["metrics"] == "subscribersGained,subscribersLost"


def test_subscriber_growth_returns_none_on_api_error():
    assert stats.subscriber_growth(client=_RaisingClient()) is None


# ── revenue_available / revenue_stats (opt-in monetary scope) ───────────────
def test_revenue_available_false_without_monetary_token(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(tmp_path / "no_such_file.json"))
    assert stats.revenue_available() is False


def test_revenue_available_true_with_monetary_token(tmp_path, monkeypatch):
    token = tmp_path / "token_monetary.json"
    token.write_text("{}")
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(token))
    assert stats.revenue_available() is True


def test_revenue_stats_shapes_rows():
    response = {"rows": [["2026-08-01", 12.5, 10.0, 4.2, 3.9]]}
    client = FakeAnalyticsClient(response)

    result = stats.revenue_stats(client=client)

    assert result == [{
        "date": "2026-08-01", "revenue": 12.5, "ad_revenue": 10.0,
        "cpm": 4.2, "playback_cpm": 3.9,
    }]


def test_revenue_stats_queries_monetary_metrics():
    client = FakeAnalyticsClient({"rows": []})
    stats.revenue_stats(client=client)
    kwargs = client._reports.calls[0]
    assert kwargs["metrics"] == "estimatedRevenue,estimatedAdRevenue,cpm,playbackBasedCpm"


def test_revenue_stats_none_without_monetary_token_and_no_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(tmp_path / "absent.json"))
    assert stats.revenue_stats() is None


def test_revenue_stats_returns_none_on_api_error():
    assert stats.revenue_stats(client=_RaisingClient()) is None
