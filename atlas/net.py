"""
atlas.net — the one way this project talks to the internet.

Every outbound request goes through `Fetcher`. That is worth enforcing because
the alternative — `requests.get` scattered across four source modules — is how a
scraper ends up hammering a government site during a debugging session, and how
politeness settings drift apart between modules.

Four behaviours, each with a reason:

  Rate limit. canada.ca's robots.txt sets no Crawl-delay and disallows nothing
  we touch, so ~1 request/second is self-imposed rather than required. It costs
  about a minute for a full MPO crawl and removes any question of whether we
  were a burden.

  On-disk cache. Development means running stage 01 dozens of times. Without a
  cache that is dozens of full crawls of a public service for no new data. The
  cache is keyed on URL and is scratch — `data/raw/cache/` is gitignored.

  Backoff. 502/504/524 from these hosts are infrastructure, not a bad URL.
  Three retries with exponential backoff; 404 and 403 fail immediately, because
  retrying them just repeats a wrong answer more slowly.

  Generous timeouts. canada.ca was observed taking more than 45 seconds to first
  byte from some networks while smaller endpoints answered instantly. A short
  timeout would turn that into a spurious "site down".

Explicitly NOT carried over from African-Stability-Index: that project's
`01_pull.py` monkey-patches `requests.Session.merge_environment_settings` to
force `verify=False` process-wide as a Windows SSL workaround, and tracks it in
its own backlog as a defect. TLS verification stays on here. If a corporate
proxy ever breaks it, the fix is REQUESTS_CA_BUNDLE, not disabling the check.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


# ── Settings ───────────────────────────────────────────────────────────────────

#: Identifies us and points at the project. A real UA is the minimum courtesy
#: when scraping; it lets an administrator tell a research crawler from a bot.
USER_AGENT = (
    "canada-economic-atlas/0.1 (research; +https://github.com/Oscarsb2004/canada-economic-atlas)"
)

#: Seconds between requests to the same host.
MIN_INTERVAL = 1.0

#: (connect, read). Read is long on purpose — see the module docstring.
TIMEOUT = (15.0, 120.0)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5           # seconds; doubles each attempt (5 → 10 → 20)

#: Status codes worth retrying. Everything else is an answer, even if unwelcome.
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504, 520, 522, 524})


class FetchError(RuntimeError):
    """A request failed in a way retrying will not fix."""


# ── The fetcher ────────────────────────────────────────────────────────────────

@dataclass
class Fetcher:
    """
    A polite, caching HTTP client.

    Not a singleton: stages construct their own so a test can point one at a
    temporary directory without touching global state.
    """

    cache_dir: Path
    min_interval: float = MIN_INTERVAL
    use_cache: bool = True

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8",
        })
        self._last_request_at = 0.0

    # ── Public surface ────────────────────────────────────────────────────────

    def text(self, url: str, *, encoding: str | None = None) -> str:
        """Fetch `url` and decode as text."""
        raw = self.bytes(url)
        if encoding:
            return raw.decode(encoding, errors="replace")
        # Federal pages declare UTF-8 and mean it; the fallback is for the odd
        # legacy CSV served as latin-1.
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            log.warning("%s is not valid UTF-8; decoding as latin-1", url)
            return raw.decode("latin-1", errors="replace")

    def json(self, url: str) -> Any:
        """Fetch `url` and parse as JSON."""
        body = self.text(url)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            # An ArcGIS or WDS error arrives as an HTML page with status 200, so
            # the parse failure is the first sign anything is wrong. Show enough
            # of the body to identify it without dumping a whole page into logs.
            raise FetchError(f"{url} did not return JSON: {body[:200]!r}") from exc

    def bytes(self, url: str, *, force: bool = False) -> bytes:
        """
        Fetch `url` and return the raw body, via the cache unless `force`.

        This is the only method that actually performs a request; `text` and
        `json` are decoders over it.
        """
        cached = None if (force or not self.use_cache) else self._cache_read(url)
        if cached is not None:
            log.debug("cache hit  %s", url)
            return cached

        body = self._get_with_retries(url)
        if self.use_cache:
            self._cache_write(url, body)
        return body

    def post_json(self, url: str, payload: Any) -> Any:
        """
        POST `payload` as JSON and parse the response.

        Deliberately NOT cached. The cache is keyed on URL alone, so caching a
        POST would serve one request body's answer to a different body — which
        is the kind of bug that produces plausible wrong numbers rather than an
        error. StatCan's WDS needs POST for cube metadata and for vector reads.
        """
        self._throttle()
        try:
            resp = self._session.post(url, json=payload, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise FetchError(f"POST {url} failed: {exc}") from exc
        if resp.status_code != 200:
            raise FetchError(f"POST {url} returned HTTP {resp.status_code}")
        return resp.json()

    def download(self, url: str, dest: Path, *, force: bool = False) -> Path:
        """
        Fetch `url` straight to `dest`, skipping it if already present.

        Used for the full-resolution federal renderings and the StatCan cube
        zips, which are far too large to route through the text cache.
        """
        dest = Path(dest)
        if dest.exists() and not force:
            log.debug("already downloaded  %s", dest.name)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = self._get_with_retries(url)
        dest.write_bytes(body)
        log.info("downloaded %s (%s bytes)", dest.name, f"{len(body):,}")
        return dest

    # ── Internals ─────────────────────────────────────────────────────────────

    def _get_with_retries(self, url: str) -> bytes:
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self._session.get(url, timeout=TIMEOUT, allow_redirects=True)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if attempt == MAX_RETRIES:
                    break
                self._sleep_for_retry(attempt, url, str(exc))
                continue

            if resp.status_code == 200:
                return resp.content

            if resp.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                self._sleep_for_retry(attempt, url, f"HTTP {resp.status_code}")
                continue

            raise FetchError(f"{url} returned HTTP {resp.status_code}")

        raise FetchError(f"{url} failed after {MAX_RETRIES} retries: {last_exc}")

    def _sleep_for_retry(self, attempt: int, url: str, reason: str) -> None:
        delay = RETRY_BACKOFF_BASE * (2 ** attempt)
        log.warning("%s (%s) — retrying in %ss", url, reason, delay)
        time.sleep(delay)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        # Hashed, not slugified: federal URLs are long and contain characters
        # Windows rejects in filenames.
        return self.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.bin"

    def _cache_read(self, url: str) -> bytes | None:
        path = self._cache_path(url)
        return path.read_bytes() if path.exists() else None

    def _cache_write(self, url: str, body: bytes) -> None:
        self._cache_path(url).write_bytes(body)
        # A sidecar so a human can tell what a hashed cache file holds.
        self._cache_path(url).with_suffix(".url").write_text(url, encoding="utf-8")
