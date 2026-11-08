import asyncio
import time
from weakref import WeakKeyDictionary

import httpx

BASE_URL = "https://api.notion.com/v1"


class NotionError(Exception):
    def __init__(self, status: int | None = None, code: str | None = None):
        self.status = status
        self.code = code
        super().__init__(f"Notion request failed ({status}, {code})")


class NotionUnavailable(NotionError):
    pass


class _Limiter:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.last_start: float | None = None

    async def wait(self, interval, sleep):
        async with self.lock:
            if self.last_start is not None:
                delay = interval - (time.monotonic() - self.last_start)
                if delay > 0:
                    await sleep(delay)
            self.last_start = time.monotonic()


# Share the limiter across clients on the application's event loop.
_limiters = WeakKeyDictionary()


class NotionClient:
    def __init__(
        self,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        rate_per_sec: float = 3.0,
        max_attempts: int = 3,
        sleep=asyncio.sleep,
    ):
        if rate_per_sec <= 0 or max_attempts < 1:
            raise ValueError("rate_per_sec and max_attempts must be positive")
        self.http = http if http is not None else httpx.AsyncClient(timeout=30)
        self._owns_http = http is None
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2025-09-03",
        }
        self.interval = 1 / min(rate_per_sec, 3.0)
        self.max_attempts = max_attempts
        self.sleep = sleep

    async def _request(self, method, path, **kwargs):
        loop = asyncio.get_running_loop()
        limiter = _limiters.setdefault(loop, _Limiter())
        for attempt in range(self.max_attempts):
            await limiter.wait(self.interval, self.sleep)
            try:
                response = await self.http.request(
                    method, f"{BASE_URL}{path}", headers=self.headers, **kwargs
                )
            except httpx.RequestError:
                if attempt + 1 == self.max_attempts:
                    raise NotionUnavailable() from None
                await self.sleep(2**attempt)
                continue
            if response.is_success:
                return response.json()
            try:
                code = response.json().get("code")
            except (ValueError, AttributeError):
                code = None
            retryable = response.status_code == 429 or response.status_code >= 500
            error = NotionUnavailable if retryable else NotionError
            if not retryable or attempt + 1 == self.max_attempts:
                raise error(response.status_code, code)
            try:
                delay = max(0.0, float(response.headers["Retry-After"]))
            except (KeyError, ValueError):
                delay = 2**attempt
            await self.sleep(delay)

    async def get_data_source(self, ds_id) -> dict:
        return await self._request("GET", f"/data_sources/{ds_id}")

    async def query(self, ds_id, *, filter=None, sorts=None, limit=None) -> list[dict]:
        results = []
        cursor = None
        while limit is None or len(results) < limit:
            payload = {"page_size": 100}
            if filter is not None:
                payload["filter"] = filter
            if sorts is not None:
                payload["sorts"] = sorts
            if cursor:
                payload["start_cursor"] = cursor
            page = await self._request(
                "POST", f"/data_sources/{ds_id}/query", json=payload
            )
            results.extend(page["results"])
            if not page.get("has_more"):
                break
            cursor = page["next_cursor"]
        return results if limit is None else results[:limit]

    async def create_page(self, ds_id, properties: dict, children=None) -> dict:
        payload = {
            "parent": {"type": "data_source_id", "data_source_id": ds_id},
            "properties": properties,
        }
        if children is not None:
            payload["children"] = children[:100]
        page = await self._request("POST", "/pages", json=payload)
        if children and len(children) > 100:
            await self.append_children(page["id"], children[100:])
        return page

    async def update_page(self, page_id, properties: dict) -> dict:
        return await self._request(
            "PATCH", f"/pages/{page_id}", json={"properties": properties}
        )

    async def list_children(self, block_id) -> list[dict]:
        results = []
        params = {"page_size": 100}
        while True:
            page = await self._request(
                "GET", f"/blocks/{block_id}/children", params=params
            )
            results.extend(page["results"])
            if not page.get("has_more"):
                return results
            params["start_cursor"] = page["next_cursor"]

    async def append_children(self, block_id, children: list[dict]) -> None:
        for start in range(0, len(children), 100):
            await self._request(
                "PATCH",
                f"/blocks/{block_id}/children",
                json={"children": children[start : start + 100]},
            )

    async def aclose(self):
        if self._owns_http:
            await self.http.aclose()
