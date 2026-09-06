"""Headless API tests: run the whole FastAPI app with TestClient."""
import pytest
from fastapi.testclient import TestClient

from raycast_linux.backend.files import FileIndex
from raycast_linux.backend.server import ServiceHub, build_app


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return ServiceHub()


@pytest.fixture()
def client(hub):
    app = build_app(hub)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pid"] > 0
    assert "display_server" in body


def test_env(client):
    body = client.get("/api/env").json()
    assert "window_provider" in body
    assert "data_dir" in body
    assert body["window_provider"]  # never empty


def test_apps_endpoint_shape(client):
    body = client.get("/api/apps", params={"query": ""}).json()
    assert "items" in body
    for app in body["items"]:
        assert app["name"] and app["id"]


def test_snippets_crud(client):
    created = client.post("/api/snippets", json={"name": "s", "content": "x"}).json()
    assert created["id"]
    got = client.get("/api/snippets").json()["items"]
    assert any(s["id"] == created["id"] for s in got)

    updated = client.put(
        f"/api/snippets/{created['id']}", json={"content": "y"}
    ).json()
    assert updated["content"] == "y"

    assert client.delete(f"/api/snippets/{created['id']}").status_code == 200
    assert client.delete(f"/api/snippets/{created['id']}").status_code == 404


def test_snippet_create_requires_name(client):
    assert client.post("/api/snippets", json={"name": "  ", "content": "x"}).status_code == 400


def test_clipboard_degrades_without_tools(client, hub):
    body = client.get("/api/clipboard").json()
    assert body["items"] == []
    # no wl-copy/xclip in the sandbox → graceful failure, not a 500
    res = client.post("/api/clipboard/copy", json={"text": "hi"})
    assert res.status_code == 200
    assert res.json()["ok"] is False


def test_windows_none_provider(client, hub):
    info = client.get("/api/windows").json()
    assert info["provider"] in ("none", "sway", "hyprland", "x11", "wayland-generic", "x11-generic")
    for action in info["actions"]:
        res = client.post("/api/windows/action", json={"action": action}).json()
        assert "ok" in res and "message" in res


def test_shortcuts_fail_gracefully_without_portal(client, hub):
    # The frontend normally attaches an activation callback; simulate it so
    # the register call proceeds to the (absent) portal.
    hub.portal.set_on_activate(lambda: None)
    res = client.post("/api/shortcuts", json={"shortcut": "super+space"}).json()
    # headless sandbox has no portal: must be ok=False with a helpful message
    assert res["ok"] is False
    assert "raycast-linux toggle" in res["message"] or "python3-dbus" in res["message"]


def test_palette_toggle_without_frontend(client):
    res = client.post("/api/palette/toggle").json()
    assert res["ok"] is False


def test_file_index_in_isolated_root(tmp_path):
    root = tmp_path / "home"
    (root / "proj" / "src").mkdir(parents=True)
    (root / "proj" / "src" / "main.py").write_text("print('hi')")
    (root / "proj" / "README.md").write_text("# hi")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "junk.js").write_text("x")
    (root / ".cache").mkdir()
    (root / ".cache" / "junk.bin").write_bytes(b"x")

    idx = FileIndex(root=str(root))
    count = idx.build()
    assert count == 2  # node_modules and .cache skipped
    hits = idx.search("main")
    assert len(hits) == 1
    assert hits[0]["name"] == "main.py"
    assert hits[0]["rel"] == "proj/src/main.py"


def test_files_endpoint_refresh(client):
    body = client.get("/api/files", params={"query": "", "limit": 5}).json()
    assert body["status"] in ("ready", "error", "building")
    assert isinstance(body["items"], list)
