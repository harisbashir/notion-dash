import json

import httpx
import pytest

from app.notion.client import NotionClient, NotionError, NotionUnavailable

BASE = "https://api.notion.com/v1"


@pytest.fixture
def virtual_clock(monkeypatch):
    class Clock:
        now = 0.0
        sleeps = []

        async def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr("app.notion.client.time.monotonic", lambda: clock.now)
    return clock


@pytest.fixture
def notion(virtual_clock):
    return NotionClient("fake-token", sleep=virtual_clock.sleep)


async def test_headers(respx_mock, notion):
    route = respx_mock.get(f"{BASE}/data_sources/fake-ds").respond(
        200, json={"id": "fake-ds"}
    )
    assert await notion.get_data_source("fake-ds") == {"id": "fake-ds"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer fake-token"
    assert route.calls[0].request.headers["Notion-Version"] == "2025-09-03"
    await notion.aclose()


@pytest.mark.parametrize("limit,count", [(None, 150), (120, 120), (0, 0)])
async def test_query_paginates(respx_mock, notion, limit, count):
    route = respx_mock.post(f"{BASE}/data_sources/fake-ds/query").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": str(i)} for i in range(100)],
                    "has_more": True,
                    "next_cursor": "fake-cursor",
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [{"id": str(i)} for i in range(100, 150)],
                    "has_more": False,
                    "next_cursor": None,
                },
            ),
        ]
    )
    result = await notion.query("fake-ds", limit=limit)
    assert len(result) == count
    assert route.call_count == (0 if limit == 0 else 2)
    if limit != 0:
        assert json.loads(route.calls[0].request.content)["page_size"] == 100
        assert (
            json.loads(route.calls[1].request.content)["start_cursor"] == "fake-cursor"
        )
    await notion.aclose()


async def test_retry_after_429(respx_mock, notion, virtual_clock):
    route = respx_mock.get(f"{BASE}/data_sources/fake-ds").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"id": "fake-ds"}),
        ]
    )
    assert await notion.get_data_source("fake-ds") == {"id": "fake-ds"}
    assert 2 in virtual_clock.sleeps
    assert route.call_count == 2
    await notion.aclose()


async def test_retry_5xx_then_unavailable(respx_mock, notion, virtual_clock):
    route = respx_mock.get(f"{BASE}/data_sources/fake-ds").respond(502)
    with pytest.raises(NotionUnavailable) as exc:
        await notion.get_data_source("fake-ds")
    assert exc.value.status == 502
    assert route.call_count == 3
    assert virtual_clock.sleeps == [1, 2]
    await notion.aclose()


async def test_4xx_raises_notion_error(respx_mock, notion):
    route = respx_mock.get(f"{BASE}/data_sources/fake-ds").respond(
        404, json={"code": "object_not_found"}
    )
    with pytest.raises(NotionError) as exc:
        await notion.get_data_source("fake-ds")
    assert exc.value.status == 404
    assert exc.value.code == "object_not_found"
    assert not isinstance(exc.value, NotionUnavailable)
    assert route.call_count == 1
    await notion.aclose()


async def test_append_chunks_100(respx_mock, notion):
    route = respx_mock.patch(f"{BASE}/blocks/fake-page/children").respond(200, json={})
    await notion.append_children("fake-page", [{"object": "block"}] * 250)
    assert [
        len(json.loads(call.request.content)["children"]) for call in route.calls
    ] == [100, 100, 50]
    await notion.aclose()


async def test_rate_limit(respx_mock, virtual_clock):
    respx_mock.get(f"{BASE}/data_sources/fake-ds").respond(200, json={})
    a = NotionClient("fake-a", sleep=virtual_clock.sleep)
    b = NotionClient("fake-b", sleep=virtual_clock.sleep)
    for client in [a, b, a, b, a, b]:
        await client.get_data_source("fake-ds")
    assert virtual_clock.now >= 5 / 3 - 0.001
    await a.aclose()
    await b.aclose()


async def test_network_error(respx_mock, notion):
    route = respx_mock.get(f"{BASE}/data_sources/fake-ds").mock(
        side_effect=httpx.ConnectError("offline")
    )
    with pytest.raises(NotionUnavailable) as exc:
        await notion.get_data_source("fake-ds")
    assert exc.value.status is None
    assert route.call_count == 3
    await notion.aclose()


async def test_write_payloads_and_children_pagination(respx_mock, notion):
    create = respx_mock.post(f"{BASE}/pages").respond(200, json={"id": "fake-new"})
    patch = respx_mock.patch(f"{BASE}/pages/fake-new").respond(
        200, json={"id": "fake-new"}
    )
    children = respx_mock.get(f"{BASE}/blocks/fake-new/children").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": "a"}],
                    "has_more": True,
                    "next_cursor": "next",
                },
            ),
            httpx.Response(200, json={"results": [{"id": "b"}], "has_more": False}),
        ]
    )
    props = {"Name": {"title": []}}
    assert await notion.create_page("fake-ds", props, []) == {"id": "fake-new"}
    assert json.loads(create.calls[0].request.content) == {
        "parent": {"type": "data_source_id", "data_source_id": "fake-ds"},
        "properties": props,
        "children": [],
    }
    await notion.update_page("fake-new", props)
    assert json.loads(patch.calls[0].request.content) == {"properties": props}
    assert await notion.list_children("fake-new") == [{"id": "a"}, {"id": "b"}]
    assert children.calls[1].request.url.params["start_cursor"] == "next"
    await notion.aclose()


async def test_create_page_not_retried_on_5xx(respx_mock, notion):
    route = respx_mock.post(f"{BASE}/pages").respond(502)
    with pytest.raises(NotionUnavailable):
        await notion.create_page("ds", {})
    assert route.call_count == 1


async def test_create_page_retried_on_429(respx_mock, notion):
    route = respx_mock.post(f"{BASE}/pages").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"id": "p1"}),
        ]
    )
    assert (await notion.create_page("ds", {}))["id"] == "p1"
    assert route.call_count == 2
