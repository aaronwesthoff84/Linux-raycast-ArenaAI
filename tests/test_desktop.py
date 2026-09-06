import os
import textwrap

from raycast_linux.logic.desktop import (
    command_for,
    load_desktop_files,
    parse_desktop_file,
)


def _write(tmp_path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_parse_basic(tmp_path):
    p = _write(tmp_path, "test.app", """
        [Desktop Entry]
        Type=Application
        Name=Test App
        GenericName=Tester
        Comment=A test application
        Icon=utilities-terminal
        Exec=term
        Categories=Utility;
        Keywords=test;demo;
    """)
    app = parse_desktop_file(p)
    assert app["id"] == "test"
    assert app["name"] == "Test App"
    assert app["icon"] == "utilities-terminal"
    assert app["categories"] == ["Utility"]
    assert app["keywords"] == ["test", "demo"]
    assert app["terminal"] is False


def test_localized_key_does_not_override(tmp_path):
    p = _write(tmp_path, "loc.desktop", """
        [Desktop Entry]
        Name=English Name
        Name[de]=Deutscher Name
        Exec=thing
    """)
    app = parse_desktop_file(p)
    assert app["name"] == "English Name"


def test_nodisplay_and_non_application_skipped(tmp_path):
    p1 = _write(tmp_path, "hidden.desktop", """
        [Desktop Entry]
        Name=Hidden
        Exec=hidden
        NoDisplay=true
    """)
    p2 = _write(tmp_path, "link.desktop", """
        [Desktop Entry]
        Type=Link
        Name=Link
        URL=http://example.com
    """)
    assert parse_desktop_file(p1) is None
    assert parse_desktop_file(p2) is None


def test_mangled_name_stripped(tmp_path):
    p = _write(tmp_path, "m.desktop", """
        [Desktop Entry]
        Name=Test*App_foo
        Exec=t
    """)
    assert parse_desktop_file(p)["name"] == "TestAppfoo"


def test_load_dirs_user_wins(tmp_path):
    user = tmp_path / "user"
    system = tmp_path / "system"
    user.mkdir()
    system.mkdir()
    (system / "app.desktop").write_text("[Desktop Entry]\nName=System App\nExec=sys\n")
    (user / "app.desktop").write_text("[Desktop Entry]\nName=User App\nExec=usr\n")
    apps = load_desktop_files([str(user), str(system)])
    assert len(apps) == 1
    assert apps[0]["name"] == "User App"


def test_command_for_plain():
    env, cmd = command_for({"exec": "xdg-open %u"})
    assert env == []
    assert cmd == ["xdg-open"]


def test_command_for_env_prefix_and_tokens():
    env, cmd = command_for({"exec": "GTK_THEME=dark gtk-app --new %f %U"})
    assert env == ["GTK_THEME=dark"]
    assert cmd == ["gtk-app", "--new"]


def test_command_for_broken():
    assert command_for({"exec": ""}) == ([], [])
    # tokens-only Exec line: nothing to run
    assert command_for({"exec": "%u %f"}) == ([], [])
    # command with only field tokens keeps the command itself
    assert command_for({"exec": "only %u %f"}) == ([], ["only"])
