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
