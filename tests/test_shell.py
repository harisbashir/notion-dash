from app.notion.client import NotionUnavailable


def test_manifest_served(client):
    response = client.get("/static/manifest.webmanifest")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["start_url"] == "/"
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_unavailable_page_503(client):
    @client.app.get("/unavailable")
    async def unavailable():
        raise NotionUnavailable("offline")

    response = client.get("/unavailable")
    assert response.status_code == 503
    assert "Try again" in response.text
    assert "<nav" in response.text
    assert "htmx.min.js" in response.text
    fragment = client.get("/unavailable", headers={"HX-Request": "true"})
    assert fragment.status_code == 503
    assert "<html" not in fragment.text


def test_screen_polls_for_external_edits(client):
    from fastapi import Request

    from app.web import render

    @client.app.get("/shell")
    async def shell(request: Request):
        return render(request, "error.html")

    text = client.get("/shell").text
    assert "every 60s" in text
    assert "form[data-dirty]" in text
