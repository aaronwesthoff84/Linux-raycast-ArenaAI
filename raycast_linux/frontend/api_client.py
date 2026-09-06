"""Tiny async-ish HTTP client: requests run on a worker pool, results are
dispatched back onto the GTK main thread via GLib.idle_add."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
from gi.repository import GLib


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="raycast-api")
        self._client: httpx.Client | None = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            # 15s: the first file search may trigger a full $HOME index build.
            self._client = httpx.Client(base_url=self.base_url, timeout=15.0)
        return self._client

    def call(self, method: str, path: str, params: dict | None = None,
             json: dict | None = None, on_result=None) -> None:
        """Fire a request; ``on_result(result_dict_or_None, error_or_None)``
        runs on the GTK main thread."""

        def worker():
            try:
                r = self._http().request(method, path, params=params, json=json)
                try:
                    payload = r.json()
                except ValueError:
                    payload = {"ok": r.status_code == 200, "message": r.text[:200]}
                if r.status_code >= 400:
                    GLib.idle_add(_callback, on_result, None, payload.get("detail", str(payload)), False)
                    return
                GLib.idle_add(_callback, on_result, payload, None, False)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(_callback, on_result, None, str(e), False)

        def _callback(cb, result, error, _flag):
            if cb:
                cb(result, error)
            return False

        self.pool.submit(worker)

    def get(self, path: str, params: dict | None = None, on_result=None) -> None:
        self.call("GET", path, params=params, on_result=on_result)

    def post(self, path: str, json: dict | None = None, on_result=None) -> None:
        self.call("POST", path, json=json, on_result=on_result)

    def put(self, path: str, json: dict | None = None, on_result=None) -> None:
        self.call("PUT", path, json=json, on_result=on_result)

    def delete(self, path: str, on_result=None) -> None:
        self.call("DELETE", path, on_result=on_result)

    def shutdown(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self.pool.shutdown(wait=False)
