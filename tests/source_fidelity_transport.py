"""Deterministic production-transport boundary for receipt-building tests."""

import socket
from contextlib import contextmanager
from unittest import mock

from scripts import source_fidelity as production_source_fidelity

PUBLIC_TEST_ADDRESS = "93.184.216.34"


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
