# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal stdlib HTTP client for the mod-ui REST calls.

Replaces `requests`, whose import pulls in chardet's language models and costs
~3.4s of startup on the Pi for no benefit: every call here is form/JSON against
localhost.
"""

import json as _json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class Response:
    def __init__(self, status_code: int, body: bytes, encoding: str = "utf-8"):
        self.status_code = status_code
        self.content = body
        self._encoding = encoding

    @property
    def text(self) -> str:
        return self.content.decode(self._encoding, errors="replace")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        return _json.loads(self.text)


def _send(req: urllib.request.Request, timeout: float | None) -> Response:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return Response(resp.status, resp.read(), charset)
    except urllib.error.HTTPError as e:
        # requests reports 4xx/5xx as a Response; callers branch on status_code.
        charset = e.headers.get_content_charset() or "utf-8" if e.headers else "utf-8"
        return Response(e.code, e.read(), charset)


def get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> Response:
    return _send(urllib.request.Request(url, headers=headers or {}, method="GET"), timeout)


def post(
    url: str,
    data: dict[str, Any] | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Response:
    hdrs = dict(headers or {})
    if json is not None:
        body = _json.dumps(json).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    else:
        body = b""
    return _send(urllib.request.Request(url, data=body, headers=hdrs, method="POST"), timeout)
