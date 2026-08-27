from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import SpaStaticFiles


def test_spa_static_files_serve_assets_and_fall_back_to_index(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "index.html").write_text("<title>Carhibou</title>", encoding="utf-8")
    (tmp_path / "asset.txt").write_text("compiled asset", encoding="utf-8")
    app = FastAPI()
    app.mount("/", SpaStaticFiles(directory=tmp_path, html=True))

    with TestClient(app) as client:
        assert client.get("/asset.txt").text == "compiled asset"
        deep_link = client.get("/vehicles/example/history")
        assert deep_link.status_code == 200
        assert "<title>Carhibou</title>" in deep_link.text
