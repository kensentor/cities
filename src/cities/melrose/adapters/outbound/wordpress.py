"""LogSource over the department site's WordPress media API."""

from __future__ import annotations

import html
import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

import httpx

from cities.melrose.domain.logs import PublishedLog
from cities.melrose.ports.outbound import LogSource, LogSourceUnavailable

MEDIA_URL = "https://melrosepolice.net/wp-json/wp/v2/media"
# The police-logs page; every weekly PDF is attached to it.
POLICE_LOGS_PAGE_ID = 160
FIELDS = "id,date_gmt,modified_gmt,source_url,title"


class WordPressLogSource(LogSource):
    """Lists and downloads the dispatch-log PDFs, waiting between requests to the site."""

    __slots__ = ("_client", "_interval", "_last_request", "_monotonic", "_sleep")

    def __init__(
        self,
        client: httpx.Client,
        *,
        interval_s: float,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._interval = interval_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request: float | None = None

    def list_logs(self, uploaded_since: date) -> Sequence[PublishedLog]:
        logs: list[PublishedLog] = []
        page, pages = 1, 1
        while page <= pages:
            response = self._get(
                MEDIA_URL,
                params={
                    "parent": POLICE_LOGS_PAGE_ID,
                    "after": f"{uploaded_since.isoformat()}T00:00:00",
                    "per_page": 100,
                    "page": page,
                    "orderby": "id",
                    "order": "asc",
                    "_fields": FIELDS,
                },
            )
            try:
                pages = int(response.headers.get("X-WP-TotalPages", "1"))
                logs.extend(_published_log(item) for item in response.json())
            except (ValueError, KeyError, TypeError) as exc:
                raise LogSourceUnavailable(f"unexpected media listing: {exc}") from exc
            page += 1
        return logs

    def fetch(self, log: PublishedLog) -> bytes:
        content = self._get(log.source_url).content
        if not content.startswith(b"%PDF"):
            raise LogSourceUnavailable(f"{log.source_url} did not return a PDF")
        return content

    def _get(self, url: str, params: dict[str, str | int] | None = None) -> httpx.Response:
        if self._last_request is not None:
            wait = self._interval - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LogSourceUnavailable(f"{url}: {exc}") from exc
        finally:
            self._last_request = self._monotonic()
        return response


def _published_log(item: dict[str, object]) -> PublishedLog:
    title = item["title"]
    rendered = title["rendered"] if isinstance(title, dict) else title
    return PublishedLog(
        media_id=int(str(item["id"])),
        source_url=str(item["source_url"]),
        title=html.unescape(str(rendered)),
        uploaded_at=_gmt(item["date_gmt"]),
        modified_at=_gmt(item["modified_gmt"]),
    )


def _gmt(value: object) -> datetime:
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
