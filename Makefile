PY ?= python3

.PHONY: venv test run server doctor install deb appimage clean

venv:
	$(PY) -m venv .venv
	./.venv/bin/pip install -q -U pip
	./.venv/bin/pip install -q -e ".[dev]"

test:
	./.venv/bin/python -m pytest -q

run:
	./.venv/bin/python -m raycast_linux

server:
	./.venv/bin/python -m raycast_linux server

doctor:
	./.venv/bin/python -m raycast_linux doctor

install:
	./install.sh

source:
	./packaging/build-source.sh

pkgbuild: source
	cd packaging && makepkg -si

deb:
	./packaging/build-deb.sh

appimage:
	./packaging/build-appimage.sh

clean:
	rm -rf dist build *.egg-info .appimage-venv onefile
