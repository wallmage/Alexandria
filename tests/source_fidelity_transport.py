"""Deterministic production-transport boundary for receipt-building tests."""

import socket
from contextlib import contextmanager
from unittest import mock

from scripts import source_fidelity as production_source_fidelity

PUBLIC_TEST_ADDRESS = "93.184.216.34"

GBK_META_PAGE = (
    "<html><head><meta charset=\"gbk\"><title>GBK标题页</title>"
    '<meta name="date" content="2026-03-01">'
    "</head><body>简体中文正文足够长用于探测</body></html>"
).encode("gbk")
BOM_PAGE = (
    b"\xef\xbb\xbf"
    + (
        "<html><head><title>BOM Title</title>"
        '<meta property="article:published_time" content="2026-04-02">'
        "</head><body>BOM encoded visible text</body></html>"
    ).encode("utf-8")
)
CHANGED_CONTEXT_PAGE = (
    "<html><head><title>Pricing</title></head><body>"
    "<p>Free: “Claude Code: Included”, with 50% of weekly limits.</p>"
    "<p>更正: the prior pricing result is invalid and retracted.</p>"
    "</body></html>"
).encode("utf-8")


def fixture_responses():
    """Deterministic pages for charset, HTTP errors, and context change."""
    return {
        "gbk.example.org": (
            200,
            {"content-type": "text/html"},
            GBK_META_PAGE,
        ),
        "bom.example.org": (
            200,
            {"content-type": "text/html"},
            BOM_PAGE,
        ),
        "blocked.example.org": (
            403,
            {"content-type": "text/html"},
            b"<p>forbidden</p>",
        ),
    }


@contextmanager
def mock_production_transport(
    responses,
    *,
    module=production_source_fidelity,
):
    """Replace DNS and pinned HTTP while preserving the production code path."""
    normalized = {
        str(host).casefold().rstrip("."): response
        for host, response in responses.items()
    }

    def resolve(host, port, **_kwargs):
        normalized_host = str(host).casefold().rstrip(".")
        if normalized_host not in normalized:
            raise socket.gaierror(
                socket.EAI_NONAME,
                f"No deterministic response for {host}",
            )
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC_TEST_ADDRESS, port),
            )
        ]

    def request(target, *, timeout):
        del timeout
        try:
            return normalized[target.host.casefold().rstrip(".")]
        except KeyError as exc:
            raise OSError(
                f"No deterministic response for {target.host}"
            ) from exc

    with (
        mock.patch.object(module.socket, "getaddrinfo", side_effect=resolve),
        mock.patch.object(module, "_request_pinned", side_effect=request),
    ):
        yield
