from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from xml.etree import ElementTree

import httpx

from app.contracts import RawEnvelope, StoragePolicy
from app.providers.news.base import NewsProvider

Clock = Callable[[], datetime]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_HTTP_ATTEMPTS = 3


def _digest(title: str, content: str) -> str:
    normalized = f"{title.strip().casefold()}\n{content.strip().casefold()}"
    return sha256(normalized.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sec_acceptance_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return _utc(datetime.fromisoformat(normalized))
    except ValueError:
        return datetime.strptime(normalized, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
) -> httpx.Response:
    for attempt in range(MAX_HTTP_ATTEMPTS):
        try:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            if (
                error.response.status_code not in RETRYABLE_STATUS_CODES
                or attempt == MAX_HTTP_ATTEMPTS - 1
            ):
                raise
            retry_after = error.response.headers.get("Retry-After", "")
            delay = min(float(retry_after), 2.0) if retry_after.isdigit() else 0.05 * 2**attempt
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == MAX_HTTP_ATTEMPTS - 1:
                raise
            delay = 0.05 * 2**attempt
        await asyncio.sleep(delay)
    raise RuntimeError("HTTP retry loop exhausted without returning or raising")


class OfficialRssProvider(NewsProvider):
    name = "official-rss"

    def __init__(
        self,
        client: httpx.AsyncClient,
        feed_url: str,
        source_id: str,
        category: str,
        clock: Clock | None = None,
    ) -> None:
        self._client = client
        self._feed_url = feed_url
        self._source_id = source_id
        self._category = category
        self._clock = clock or (lambda: datetime.now(UTC))

    async def stream_items(self) -> AsyncIterator[RawEnvelope]:
        response = await _get_with_retry(self._client, self._feed_url)
        root = ElementTree.fromstring(response.content)
        observed_at = _utc(self._clock())
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            content = (item.findtext("description") or title).strip()
            native_id = (item.findtext("guid") or link).strip() or None
            published_text = (item.findtext("pubDate") or "").strip()
            try:
                published = _utc(parsedate_to_datetime(published_text)) if published_text else None
            except (TypeError, ValueError):
                published = None
            if title and link:
                yield RawEnvelope(
                    provider=self.name,
                    source_id=self._source_id,
                    source_type="official_feed",
                    native_id=native_id,
                    published_at=published,
                    received_at=observed_at,
                    processed_at=observed_at,
                    title=title,
                    content=content,
                    url=link,
                    language="en",
                    category=self._category,
                    content_hash=_digest(title, content),
                    storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
                    derived_attributes={
                        "feed_url": self._feed_url,
                        "provider_publication_time": published_text,
                    },
                )


class SecSubmissionsProvider(NewsProvider):
    name = "sec-edgar"

    def __init__(
        self, client: httpx.AsyncClient, cik: str, user_agent: str, clock: Clock | None = None
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC_USER_AGENT is required by SEC access policy")
        self._client = client
        self._cik = cik.zfill(10)
        self._user_agent = user_agent
        self._clock = clock or (lambda: datetime.now(UTC))

    async def stream_items(self) -> AsyncIterator[RawEnvelope]:
        response = await _get_with_retry(
            self._client,
            f"https://data.sec.gov/submissions/CIK{self._cik}.json",
            headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"},
        )
        payload = response.json()
        observed_at = _utc(self._clock())
        recent = payload.get("filings", {}).get("recent", {})
        company = str(payload.get("name") or f"CIK {self._cik}")
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_documents = recent.get("primaryDocument", [])
        required_lengths = {
            "form": len(forms),
            "accessionNumber": len(accessions),
            "filingDate": len(filing_dates),
            "primaryDocument": len(primary_documents),
        }
        if len(set(required_lengths.values())) != 1:
            raise ValueError(
                f"SEC recent filing arrays have inconsistent lengths: {required_lengths}"
            )
        acceptance_times = recent.get("acceptanceDateTime", [])
        if not acceptance_times:
            acceptance_times = [None] * len(forms)
        elif len(acceptance_times) != len(forms):
            raise ValueError("SEC acceptanceDateTime length does not match filing records")
        for form, accession, filing_date, primary_document, acceptance_value in zip(
            forms, accessions, filing_dates, primary_documents, acceptance_times
        ):
            if form not in {"8-K", "10-K", "10-Q", "6-K", "20-F"}:
                continue
            title = f"{company} files {form}"
            accepted_at = _sec_acceptance_time(acceptance_value)
            content = (
                f"SEC filing {accession}; form {form}; filing date {filing_date}; "
                f"accepted at {accepted_at.isoformat() if accepted_at else 'unavailable'}."
            )
            accession_compact = accession.replace("-", "")
            cik_compact = str(int(self._cik))
            url = f"https://www.sec.gov/Archives/edgar/data/{cik_compact}/{accession_compact}/{primary_document}"
            filing_day = datetime.fromisoformat(f"{filing_date}T00:00:00+00:00")
            yield RawEnvelope(
                provider=self.name,
                source_id="sec-edgar",
                source_type="regulatory_filing",
                native_id=accession,
                event_time=accepted_at or filing_day,
                published_at=accepted_at,
                received_at=observed_at,
                processed_at=observed_at,
                title=title,
                content=content,
                url=url,
                language="en",
                category="company_filing",
                content_hash=_digest(title, content),
                storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
                derived_attributes={
                    "form": form,
                    "accession": accession,
                    "filing_date": filing_date,
                    "accepted_at": accepted_at.isoformat() if accepted_at else "",
                },
            )


class FredObservationProvider(NewsProvider):
    name = "fred"

    def __init__(
        self, client: httpx.AsyncClient, series_id: str, api_key: str, clock: Clock | None = None
    ) -> None:
        if not api_key.strip():
            raise ValueError("FRED_API_KEY is required")
        self._client = client
        self._series_id = series_id
        self._api_key = api_key
        self._clock = clock or (lambda: datetime.now(UTC))

    async def stream_items(self) -> AsyncIterator[RawEnvelope]:
        response = await _get_with_retry(
            self._client,
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": self._series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
        )
        observed_at = _utc(self._clock())
        for observation in response.json().get("observations", []):
            date = str(observation.get("date") or "").strip()
            value = str(observation.get("value") or "").strip()
            if not date or not value or value == ".":
                continue
            realtime_start = str(observation.get("realtime_start") or "unknown-vintage")
            realtime_end = str(observation.get("realtime_end") or realtime_start)
            title = f"FRED {self._series_id} observation for {date}"
            content = (
                f"Series {self._series_id}; observation date {date}; value {value}; "
                f"vintage {realtime_start} through {realtime_end}."
            )
            event_time = datetime.fromisoformat(f"{date}T00:00:00+00:00")
            revision_fingerprint = sha256(value.encode("utf-8")).hexdigest()[:16]
            yield RawEnvelope(
                provider=self.name,
                source_id=f"fred:{self._series_id}",
                source_type="macro_data",
                native_id=f"{self._series_id}:{date}:{realtime_start}:{revision_fingerprint}",
                event_time=event_time,
                published_at=None,
                received_at=observed_at,
                processed_at=observed_at,
                title=title,
                content=content,
                url=f"https://fred.stlouisfed.org/series/{self._series_id}",
                language="en",
                category="macro_observation",
                content_hash=_digest(title, content),
                storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
                derived_attributes={
                    "series_id": self._series_id,
                    "observation_date": date,
                    "value": value,
                    "realtime_start": realtime_start,
                    "realtime_end": realtime_end,
                },
            )
