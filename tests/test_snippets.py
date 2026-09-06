import pytest

from raycast_linux.backend.snippets import SnippetService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return SnippetService()


def test_seeds_defaults(svc):
    names = [s["name"] for s in svc.list()]
    assert "email" in names
    # second call must not duplicate the seeds
    assert len(svc.list()) == len(names)


def test_crud(svc):
    s = svc.create("sig", "Regards")
    assert s["name"] == "sig"
    assert svc.get(s["id"])["content"] == "Regards"

    svc.update(s["id"], content="Regards,")
    assert svc.get(s["id"])["content"] == "Regards,"

    assert svc.delete(s["id"]) is True
    assert svc.get(s["id"]) is None
    assert svc.delete(s["id"]) is False


def test_create_requires_name(svc):
    with pytest.raises(ValueError):
        svc.create("   ", "x")


def test_search(svc):
    svc.create("email", "you@example.com")
    svc.create("address", "123 Main St")
    hits = svc.search("em")
    assert any(h["name"] == "email" for h in hits)
    assert all(h["name"] != "address" for h in hits)
    # empty query returns everything
    assert len(svc.search("")) >= 2


def test_expand_no_typing_tool(tmp_path, monkeypatch):
    # headless sandbox: no wtype/xdotool → expand must degrade to clipboard
    # or a clear failure, never raise.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    svc = SnippetService()
    s = svc.create("t", "hello")
    result = svc.expand(s["id"])
    assert isinstance(result, dict)
    assert "message" in result
    assert result["ok"] is False or result["method"] in ("wtype", "xdotool", "clipboard")
