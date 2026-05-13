#!/usr/bin/env python
# encoding: utf-8
"""vivo AI gateway signing helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import string
import time
import urllib.parse
from typing import Mapping


SIGNED_HEADERS = "x-ai-gateway-app-id;x-ai-gateway-timestamp;x-ai-gateway-nonce"


def gen_nonce(length: int = 8) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def gen_canonical_query_string(params: Mapping[str, object] | None) -> str:
    if not params:
        return ""

    raw: list[tuple[str, str]] = []
    for key in sorted(params.keys()):
        value = "" if params[key] is None else str(params[key])
        raw.append(
            (
                urllib.parse.quote(str(key), safe=""),
                urllib.parse.quote(value, safe=""),
            )
        )
    return "&".join("=".join(kv) for kv in raw)


def gen_signature(app_secret: str, signing_string: bytes) -> str:
    secret = app_secret.encode("utf-8")
    digest = hmac.new(secret, signing_string, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def gen_sign_headers(
    app_id: str,
    app_key: str,
    method: str,
    uri: str,
    query: Mapping[str, object] | None = None,
) -> dict[str, str]:
    """Generate vivo HMAC gateway headers.

    The implementation mirrors the public vivo AI gateway examples and keeps
    requestId in the canonical query string when it is sent as a URL parameter.
    """

    method = method.upper()
    timestamp = str(int(time.time()))
    nonce = gen_nonce()
    canonical_query_string = gen_canonical_query_string(query)
    signed_headers_string = (
        f"x-ai-gateway-app-id:{app_id}\n"
        f"x-ai-gateway-timestamp:{timestamp}\n"
        f"x-ai-gateway-nonce:{nonce}"
    )
    signing_string = (
        f"{method}\n"
        f"{uri}\n"
        f"{canonical_query_string}\n"
        f"{app_id}\n"
        f"{timestamp}\n"
        f"{signed_headers_string}"
    ).encode("utf-8")
    signature = gen_signature(app_key, signing_string)

    return {
        "X-AI-GATEWAY-APP-ID": app_id,
        "X-AI-GATEWAY-TIMESTAMP": timestamp,
        "X-AI-GATEWAY-NONCE": nonce,
        "X-AI-GATEWAY-SIGNED-HEADERS": SIGNED_HEADERS,
        "X-AI-GATEWAY-SIGNATURE": signature,
    }

