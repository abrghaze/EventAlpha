from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx
import pytest

from app.providers.news.http_sources import (
    FredObservationProvider,
    OfficialRssProvider,
    SecSubmissionsProvider,
)

NOW = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_official_rss_maps_to_raw_envelope() -> None:
    xml = b"<rss><channel><item><title>Policy update</title><link>https://agency.example/update</link><guid>a1</guid><description>Official text</description><pubDate>Wed, 26 Aug 2026 14:59:00 GMT</pubDate></item></channel></rss>"
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=xml))
    )
    provider = OfficialRssProvider(
        client, "https://agency.example/feed", "agency", "regulation", lambda: NOW
    )
    items = [item async for item in provider.stream_items()]
    await client.aclose()
    assert items[0].source_id == "agency"
    assert items[0].source_type == "official_feed"
    assert items[0].published_at == datetime(2026, 8, 26, 14, 59, tzinfo=UTC)


@pytest.mark.asyncio
async def test_sec_adapter_sets_policy_header_and_filters_forms() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "EventAlpha ops@example.com"
        return httpx.Response(
            200,
            json={
                "name": "ACME Corp",
                "filings": {
                    "recent": {
                        "form": ["8-K", "3"],
                        "accessionNumber": ["0001-26-000001", "0001-26-000002"],
                        "filingDate": ["2026-08-26", "2026-08-25"],
                        "acceptanceDateTime": ["2026-08-26T14:30:15Z", "2026-08-25T10:00:00Z"],
                        "primaryDocument": ["acme8k.htm", "form3.htm"],
                    }
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SecSubmissionsProvider(client, "123", "EventAlpha ops@example.com", lambda: NOW)
    items = [item async for item in provider.stream_items()]
    await client.aclose()
    assert len(items) == 1
    assert items[0].native_id == "0001-26-000001"
    assert items[0].category == "company_filing"
    assert items[0].published_at == datetime(2026, 8, 26, 14, 30, 15, tzinfo=UTC)
    assert items[0].derived_attributes["accepted_at"] == "2026-08-26T14:30:15+00:00"


@pytest.mark.asyncio
async def test_sec_adapter_rejects_truncated_parallel_arrays() -> None:
    payload = {
        "name": "ACME Corp",
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q"],
                "accessionNumber": ["0001-26-000001"],
                "filingDate": ["2026-08-26", "2026-08-25"],
                "primaryDocument": ["one.htm", "two.htm"],
            }
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        provider = SecSubmissionsProvider(client, "123", "EventAlpha ops@example.com", lambda: NOW)
        with pytest.raises(ValueError, match="inconsistent lengths"):
            _ = [item async for item in provider.stream_items()]


@pytest.mark.asyncio
async def test_fred_adapter_preserves_observation_date_without_claiming_publish_time() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["series_id"] == "DFF"
        assert request.url.params["api_key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "observations": [
                    {
                        "date": "2026-08-01",
                        "value": "4.25",
                        "realtime_start": "2026-08-26",
                        "realtime_end": "9999-12-31",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = FredObservationProvider(client, "DFF", "test-key", lambda: NOW)
    items = [item async for item in provider.stream_items()]
    await client.aclose()
    assert items[0].event_time == datetime(2026, 8, 1, tzinfo=UTC)
    assert items[0].published_at is None
    assert items[0].received_at == NOW
    assert items[0].derived_attributes["value"] == "4.25"
    assert ":2026-08-26:" in (items[0].native_id or "")


@pytest.mark.asyncio
async def test_fred_adapter_skips_missing_observation_values() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"observations": [{"date": "2026-08-01", "value": "."}]},
            )
        )
    ) as client:
        provider = FredObservationProvider(client, "DFF", "test-key", lambda: NOW)
        assert [item async for item in provider.stream_items()] == []


@pytest.mark.asyncio
async def test_fred_revision_value_changes_native_identity() -> None:
    async def native_id_for(value: str) -> str | None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "observations": [
                        {
                            "date": "2026-08-01",
                            "value": value,
                            "realtime_start": "2026-08-26",
                            "realtime_end": "9999-12-31",
                        }
                    ]
                },
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            provider = FredObservationProvider(client, "DFF", "test-key", lambda: NOW)
            return (await anext(provider.stream_items())).native_id

    assert await native_id_for("4.25") != await native_id_for("4.50")


@pytest.mark.asyncio
async def test_official_rss_retries_a_transient_timeout() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(
            200,
            content=b"<rss><channel><item><title>Update</title><link>https://agency.example/u</link><description>Text</description></item></channel></rss>",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OfficialRssProvider(
            client, "https://agency.example/feed", "agency", "regulation", lambda: NOW
        )
        items = [item async for item in provider.stream_items()]
    assert len(items) == 1
    assert attempts == 2


@pytest.mark.asyncio
async def test_official_rss_rejects_malformed_xml() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<rss>"))
    ) as client:
        provider = OfficialRssProvider(
            client, "https://agency.example/feed", "agency", "regulation", lambda: NOW
        )
        with pytest.raises(ElementTree.ParseError):
            _ = [item async for item in provider.stream_items()]


@pytest.mark.asyncio
async def test_official_rss_stops_after_bounded_retry_exhaustion() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OfficialRssProvider(
            client, "https://agency.example/feed", "agency", "regulation", lambda: NOW
        )
        with pytest.raises(httpx.HTTPStatusError):
            _ = [item async for item in provider.stream_items()]
    assert attempts == 3


@pytest.mark.asyncio
async def test_official_rss_does_not_retry_nonretryable_status() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OfficialRssProvider(
            client, "https://agency.example/feed", "agency", "regulation", lambda: NOW
        )
        with pytest.raises(httpx.HTTPStatusError):
            _ = [item async for item in provider.stream_items()]
    assert attempts == 1
