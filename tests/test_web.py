"""HTTP delivery of packaged web resources, without a database or a running server."""

import pytest
from httpx import ASGITransport, AsyncClient

from olympic_boinc.api.app import create_app
from olympic_boinc.config import Settings


@pytest.fixture
async def web_client():
    app = create_app(
        Settings(
            _env_file=None, database_url="postgresql+asyncpg://u:p@db/x", scheduler_enabled=False
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_home_and_linked_resources(web_client, monkeypatch, tmp_path):
    # Resource paths must work from outside the repository's working directory.
    monkeypatch.chdir(tmp_path)
    response = await web_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="en">' in response.text
    assert "Medal standings · Olympic BOINC" in response.text
    assert '<select id="language">' in response.text
    assert '<option value="en" lang="en">English</option>' in response.text
    assert '<option value="ru" lang="ru">Русский</option>' in response.text
    assert 'href="/static/styles.css"' in response.text
    assert 'src="/static/app.js"' in response.text

    for path, content_type in (
        ("/static/styles.css", "text/css"),
        ("/static/app.js", "javascript"),
    ):
        asset = await web_client.get(path)

        assert asset.status_code == 200
        assert content_type in asset.headers["content-type"]
        assert asset.content


@pytest.mark.parametrize(
    "path", ["/static/missing.css", "/unknown-page", "/static/../pyproject.toml"]
)
async def test_missing_web_paths_are_404(web_client, path):
    assert (await web_client.get(path)).status_code == 404


async def test_web_does_not_shadow_api_docs(web_client):
    assert (await web_client.get("/docs")).status_code == 200

    response = await web_client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/challenges/years" in response.json()["paths"]
    assert "/" not in response.json()["paths"]
