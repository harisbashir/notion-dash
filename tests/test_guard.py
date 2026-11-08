import pytest
from fastapi import Request
from starlette.responses import PlainTextResponse


@pytest.fixture
def guarded(client):
    @client.app.api_route(
        "/guard-test", methods=["GET", "POST", "PATCH", "PUT", "DELETE"]
    )
    async def endpoint(request: Request):
        return PlainTextResponse("accepted")

    return client


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
def test_guard_rejects_cross_origin(guarded, method):
    response = getattr(guarded, method)(
        "/guard-test",
        headers={"HX-Request": "true", "Origin": "https://elsewhere.example"},
    )
    assert response.status_code == 403


def test_guard_rejects_missing_hx(guarded):
    assert (
        guarded.post("/guard-test", headers={"Origin": "http://testserver"}).status_code
        == 403
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"HX-Request": "true", "Origin": "http://testserver"},
        {"HX-Request": "true", "Referer": "http://testserver/todos"},
    ],
)
def test_guard_allows_same_origin_htmx(guarded, headers):
    assert guarded.post("/guard-test", headers=headers).text == "accepted"


@pytest.mark.parametrize(
    "origin", ["", "null", "http://testserver.evil", "http://testserver:99"]
)
def test_guard_rejects_invalid_origin(guarded, origin):
    assert (
        guarded.post(
            "/guard-test", headers={"HX-Request": "true", "Origin": origin}
        ).status_code
        == 403
    )


def test_get_not_guarded(guarded):
    assert guarded.get("/guard-test").status_code == 200
