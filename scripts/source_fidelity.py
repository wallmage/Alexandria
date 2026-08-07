#!/usr/bin/env python3
"""Re-read cited sources and check that ledger extracts survive the reading.

Every other Alexandria gate checks the report against the ledger. This one
checks the ledger against the world: it fetches a weighted sample of the cited
pages and asserts that `extract_or_location` still appears in the fetched
text. It is deliberately honest about what it could not do — an unreachable
page is recorded as unverified, never as a pass, and an offline run is
recorded and printed as a visible skip rather than a silent success.
"""

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from artifact_safety import (  # noqa: E402
    artifact_collision_errors,
    publish_temp_file,
    validated_artifact_path,
)
from report_contract import canonical_visible_text  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_SAMPLE_SIZE = 8
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_FETCH_ATTEMPTS = 3
MAX_FETCH_BYTES = 4_000_000
MAX_DOCUMENT_PAGES = 500
MAX_DOCUMENT_TEXT_CHARACTERS = 5_000_000
MAX_DOCUMENT_PARSE_SECONDS = 20
PDF_WORKER_ARGUMENT = "--decode-pdf-worker"
USER_AGENT = "Alexandria-source-fidelity/1.0"
MAX_REDIRECTS = 5
PRODUCTION_TRANSPORT = "dns-pinned-http-v1"
SUPPORTED_TEXT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
}
ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCHEMA = ROOT / "references" / "evidence-ledger.schema.json"

#: Enough characters to identify a passage, short enough to survive markup.
MIN_PROBE_CHARACTERS = 16
#: A probe longer than this is trimmed: long quotes rarely survive rendering.
MAX_PROBE_CHARACTERS = 160
PROBE_CONTEXT_RADIUS = 500

_QUOTE_SPANS = re.compile(
    r"\"([^\"]{4,})\"|'([^']{4,})'|“([^”]{4,})”|「([^」]{4,})」|『([^』]{4,})』"
)


@dataclass(frozen=True)
class SafeTarget:
    url: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class FetchedDocument:
    text: str
    final_url: str
    redirects: tuple[str, ...]
    response_sha256: str
    content_type: str
    byte_count: int


def validate_public_http_url(url, *, resolver=None):
    """Resolve one public HTTP(S) target or reject it before any connection."""
    resolver = resolver or socket.getaddrinfo
    try:
        parsed = urlsplit(str(url or ""))
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Malformed source URL: {url!r}") from exc
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise ValueError("Source URLs must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Source URLs may not contain credentials.")
    host = (parsed.hostname or "").rstrip(".")
    if not host:
        raise ValueError("Source URL has no host.")
    expected_port = 443 if scheme == "https" else 80
    port = port or expected_port
    if port != expected_port:
        raise ValueError(
            f"Source URL uses unsafe port {port}; expected {expected_port}."
        )
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = (str(literal),)
    else:
        try:
            answers = resolver(host, port, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise ValueError(f"Source host could not be resolved: {host}") from exc
        addresses = tuple(
            dict.fromkeys(
                answer[4][0]
                for answer in answers
                if len(answer) >= 5 and answer[4]
            )
        )
    if not addresses:
        raise ValueError(f"Source host has no usable address: {host}")
    unsafe = []
    for address in addresses:
        value = ipaddress.ip_address(address)
        if not value.is_global:
            unsafe.append(address)
    if unsafe:
        raise ValueError(
            "Source host resolves to a non-public address: "
            + ", ".join(unsafe)
        )
    return SafeTarget(
        url=parsed.geturl(),
        scheme=scheme,
        host=host,
        port=port,
        addresses=addresses,
    )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP peer is the already-vetted address."""

    def __init__(self, host, pinned_address, port, *, timeout):
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_address = pinned_address

    def connect(self):
        raw = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
        )
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _same_source_host(first, second):
    def normalized(host):
        host = host.casefold().rstrip(".")
        return host[4:] if host.startswith("www.") else host

    return normalized(first) == normalized(second)


def _extract_pdf_text(payload):
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF sources cannot be verified.")
    if len(reader.pages) > MAX_DOCUMENT_PAGES:
        raise ValueError(f"PDF exceeds the page limit of {MAX_DOCUMENT_PAGES}.")
    parts = []
    text_characters = 0
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_characters += len(page_text)
        if text_characters > MAX_DOCUMENT_TEXT_CHARACTERS:
            raise ValueError(
                "PDF exceeds the text limit of "
                f"{MAX_DOCUMENT_TEXT_CHARACTERS} characters."
            )
        parts.append(page_text)
    text = "\n".join(parts)
    if not text.strip():
        raise ValueError("PDF source contains no extractable text.")
    return text


def _decode_pdf_document(payload):
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), PDF_WORKER_ARGUMENT],
            input=payload,
            capture_output=True,
            check=False,
            timeout=MAX_DOCUMENT_PARSE_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("PDF parsing exceeded the time limit.") from exc
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "PDF source could not be read: "
            + (detail or f"parser exited with status {completed.returncode}")
        )
    return completed.stdout.decode("utf-8")


def _decode_document(payload, content_type, charset):
    if content_type in SUPPORTED_TEXT_TYPES:
        try:
            return payload.decode(charset or "utf-8", errors="replace")
        except LookupError as exc:
            raise ValueError(
                f"Source declares an unsupported character encoding: {charset}"
            ) from exc
    if content_type == "application/pdf":
        return _decode_pdf_document(payload)
    raise ValueError(f"Unsupported source content type: {content_type or 'missing'}")


def _request_pinned(target, *, timeout):
    address = target.addresses[0]
    parsed = urlsplit(target.url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    if target.scheme == "https":
        connection = _PinnedHTTPSConnection(
            target.host,
            address,
            target.port,
            timeout=timeout,
        )
    else:
        connection = http.client.HTTPConnection(
            address,
            port=target.port,
            timeout=timeout,
        )
    host_header = target.host
    if ":" in host_header and not host_header.startswith("["):
        host_header = f"[{host_header}]"
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": host_header,
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,text/plain,"
                    "application/json,application/pdf"
                ),
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        payload = response.read(MAX_FETCH_BYTES + 1)
        headers = {key.casefold(): value for key, value in response.getheaders()}
        return response.status, headers, payload
    finally:
        connection.close()


def normalize_text(value):
    """Fold whitespace, quotation marks, and case for substring comparison."""
    text = canonical_visible_text(value)
    text = text.translate(
        str.maketrans(
            {
                "‘": "'",
                "’": "'",
                "‚": "'",
                "“": '"',
                "”": '"',
                "′": "'",
                "″": '"',
                "‐": "-",
                "‑": "-",
                "‒": "-",
                "–": "-",
                "—": "-",
                " ": " ",
            }
        )
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path, payload, *, overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite:
        raise ValueError(f"Artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            publish_temp_file(temporary, path, force=overwrite)
        except FileExistsError as exc:
            raise ValueError(f"Artifact already exists: {path}") from exc
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


class _VisibleTextParser(HTMLParser):
    """Collect only text a reader can see from self-contained HTML."""

    ALWAYS_HIDDEN: ClassVar[set[str]] = {
        "script",
        "style",
        "template",
        "noscript",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []

    @staticmethod
    def _element_is_hidden(tag, attrs):
        attributes = {
            str(name).casefold(): "" if value is None else str(value)
            for name, value in attrs
        }
        style = attributes.get("style", "")
        return bool(
            tag.casefold() in _VisibleTextParser.ALWAYS_HIDDEN
            or "hidden" in attributes
            or attributes.get("aria-hidden", "").strip().casefold() == "true"
            or re.search(
                r"(?i)(?:^|;)\s*(?:display\s*:\s*none|"
                r"visibility\s*:\s*hidden)\s*(?:;|$)",
                style,
            )
        )

    def handle_starttag(self, tag, attrs):
        parent_hidden = self.stack[-1][1] if self.stack else False
        hidden = parent_hidden or self._element_is_hidden(tag, attrs)
        self.stack.append((tag.casefold(), hidden))
        if not hidden:
            self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        if not self._element_is_hidden(tag, attrs):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        folded = tag.casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == folded:
                hidden = self.stack[index][1]
                del self.stack[index:]
                if not hidden:
                    self.parts.append(" ")
                break

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)


def strip_markup(document):
    """Return reader-visible text from HTML or plain text."""
    parser = _VisibleTextParser()
    parser.feed(str(document or ""))
    parser.close()
    return normalize_text(" ".join(parser.parts))


def _probe_windows(text):
    """Cover all normalized text with bounded, overlapping exact probes."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= MAX_PROBE_CHARACTERS:
        return [normalized]
    overlap = max(32, MAX_PROBE_CHARACTERS // 4)
    stride = MAX_PROBE_CHARACTERS - overlap
    starts = list(range(0, len(normalized), stride))
    final_start = len(normalized) - MAX_PROBE_CHARACTERS
    if final_start not in starts:
        starts.append(final_start)
    return [
        normalized[start : start + MAX_PROBE_CHARACTERS]
        for start in sorted(set(starts))
        if start < len(normalized)
    ]


def probe_strings(extract):
    """Return the substrings that must survive in the fetched source text.

    Quoted spans are verbatim evidence and every substantive unquoted segment
    is evidence too. Locator-only prefixes such as ``Pricing page:`` identify
    where to look, but do not claim that the label itself appears on the page.
    """
    text = str(extract or "").strip()
    if not text:
        return []
    probes = []
    outside = []
    cursor = 0
    for match in _QUOTE_SPANS.finditer(text):
        outside.append(text[cursor : match.start()])
        outside.append("\n")
        quoted = next(group for group in match.groups() if group is not None)
        probes.extend(_probe_windows(quoted))
        cursor = match.end()
    outside.append(text[cursor:])
    unquoted_text = "".join(outside)
    segments = [
        normalize_text(segment)
        for segment in re.split(r"[;\n]|\.\.\.|…", unquoted_text)
    ]
    substantive = [
        segment
        for segment in segments
        if (
            segment
            and any(character.isalnum() for character in segment)
            and not segment.rstrip().endswith(":")
        )
    ]
    for segment in substantive:
        probes.extend(_probe_windows(segment))
    if not probes and any(character.isalnum() for character in text):
        probes.extend(_probe_windows(text))
    seen = set()
    unique = []
    for probe in probes:
        if probe and probe not in seen:
            seen.add(probe)
            unique.append(probe)
    return unique


def default_fetcher(
    url,
    *,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    resolver=None,
):
    """Fetch one public source through a DNS-pinned, redirect-safe transport."""
    resolver = resolver or socket.getaddrinfo
    current = validate_public_http_url(url, resolver=resolver)
    original_host = current.host
    visited = set()
    redirects = []
    for _ in range(MAX_REDIRECTS + 1):
        if current.url in visited:
            raise ValueError("Source redirect loop detected.")
        visited.add(current.url)
        for attempt in range(DEFAULT_FETCH_ATTEMPTS):
            try:
                status, headers, payload = _request_pinned(
                    current,
                    timeout=timeout,
                )
                break
            except ssl.SSLCertVerificationError:
                raise
            except (
                ssl.SSLError,
                TimeoutError,
                ConnectionError,
                http.client.RemoteDisconnected,
                OSError,
            ):
                if attempt + 1 >= DEFAULT_FETCH_ATTEMPTS:
                    raise
        if len(payload) > MAX_FETCH_BYTES:
            raise ValueError(
                f"Source response exceeds {MAX_FETCH_BYTES} bytes."
            )
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location")
            if not location:
                raise ValueError("Source redirect has no Location header.")
            redirected = validate_public_http_url(
                urljoin(current.url, location),
                resolver=resolver,
            )
            if current.scheme == "https" and redirected.scheme != "https":
                raise ValueError("HTTPS source redirected to insecure HTTP.")
            if not _same_source_host(original_host, redirected.host):
                raise ValueError(
                    "Source redirected to a different host; update the ledger "
                    "to the final accountable source URL."
                )
            redirects.append(redirected.url)
            current = redirected
            continue
        if status < 200 or status >= 300:
            raise ValueError(f"Source returned HTTP {status}.")
        raw_content_type = headers.get("content-type", "")
        content_type, _, parameters = raw_content_type.partition(";")
        charset = "utf-8"
        match = re.search(r"(?i)\bcharset\s*=\s*[\"']?([^;\"']+)", parameters)
        if match:
            charset = match.group(1).strip()
        text = _decode_document(
            payload,
            content_type.strip().casefold(),
            charset,
        )
        return FetchedDocument(
            text=text,
            final_url=current.url,
            redirects=tuple(redirects),
            response_sha256=hashlib.sha256(payload).hexdigest(),
            content_type=content_type.strip().casefold(),
            byte_count=len(payload),
        )
    raise ValueError(f"Source exceeded {MAX_REDIRECTS} redirects.")


def _claim_weight(claim, central_ids):
    if claim.get("claim_id") in central_ids:
        return 3
    if claim.get("importance") == "key":
        return 2
    if claim.get("include_in_report") is True:
        return 1
    return 0


def _probe_context_sha256s(document, probes):
    """Bind each probe to every nearby normalized evidentiary context."""
    context_hashes = []
    for probe in probes:
        positions = []
        cursor = 0
        while True:
            position = document.find(probe, cursor)
            if position < 0:
                break
            positions.append(position)
            cursor = position + max(len(probe), 1)
        hashes = []
        for position in positions:
            start = max(0, position - PROBE_CONTEXT_RADIUS)
            end = min(
                len(document),
                position + len(probe) + PROBE_CONTEXT_RADIUS,
            )
            context = document[start:end]
            hashes.append(hashlib.sha256(context.encode("utf-8")).hexdigest())
        context_hashes.append(sorted(set(hashes)))
    return context_hashes


def select_samples(ledger, sample_size=DEFAULT_SAMPLE_SIZE):
    """Return the (claim, source) pairs to re-read, heaviest evidence first."""
    if not isinstance(ledger, dict):
        return []
    claims = ledger.get("claims", [])
    sources = ledger.get("sources", [])
    if not isinstance(claims, list) or not isinstance(sources, list):
        return []
    source_urls = {
        source.get("source_id"): source.get("url")
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }
    synthesis = ledger.get("synthesis")
    central_ids = set()
    if isinstance(synthesis, dict):
        central = synthesis.get("central_judgment_claim_ids", [])
        central_ids = set(central) if isinstance(central, list) else set()

    candidates = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        weight = _claim_weight(claim, central_ids)
        source_ids = claim.get("source_ids", [])
        if not isinstance(source_ids, list):
            continue
        source_evidence = claim.get("source_evidence")
        evidence_by_source = {
            entry.get("source_id"): entry.get("extract_or_location")
            for entry in source_evidence
            if isinstance(entry, dict) and entry.get("source_id")
        } if isinstance(source_evidence, list) else {}
        for source_id in source_ids:
            url = source_urls.get(source_id)
            if not url:
                continue
            extract = evidence_by_source.get(source_id)
            if extract is None and len(source_ids) == 1:
                extract = claim.get("extract_or_location")
            probes = probe_strings(extract)
            if not probes:
                continue
            candidates.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "source_id": source_id,
                    "url": url,
                    "probes": probes,
                    "weight": weight,
                }
            )
    candidates.sort(
        key=lambda item: (
            -item["weight"],
            str(item["claim_id"]),
            str(item["source_id"]),
        )
    )
    if sample_size and sample_size > 0:
        return candidates[:sample_size]
    return candidates


def check_source_fidelity(
    ledger,
    *,
    fetcher=None,
    sample_size=DEFAULT_SAMPLE_SIZE,
    online=False,
    timeout=DEFAULT_TIMEOUT_SECONDS,
):
    """Re-read a weighted sample of sources and return a machine-readable result.

    The online pass is opt-in because network access is not available
    everywhere. A skipped run is reported as `status: skipped` with a reason,
    which is not a pass: callers that treat skip as success are doing so
    explicitly.
    """
    samples = select_samples(ledger, sample_size)
    checks = []
    if not online:
        for sample in samples:
            checks.append(
                {
                    "claim_id": sample["claim_id"],
                    "source_id": sample["source_id"],
                    "url": sample["url"],
                    "status": "skipped",
                    "detail": "Source fidelity ran offline; nothing was re-read.",
                }
            )
        return _finish(
            checks,
            online=False,
            sample_size=len(samples),
            transport=None,
            skip_reason=(
                "The online source-fidelity pass was not requested; no "
                "extract was checked against its live source."
            ),
        )

    fetch = fetcher or (lambda url: default_fetcher(url, timeout=timeout))
    transport = PRODUCTION_TRANSPORT if fetcher is None else "test"
    documents = {}
    for sample in samples:
        url = sample["url"]
        if url not in documents:
            try:
                fetched = fetch(url)
                if isinstance(fetched, FetchedDocument):
                    observation = {
                        "requested_url": url,
                        "final_url": fetched.final_url,
                        "redirects": list(fetched.redirects),
                        "response_sha256": fetched.response_sha256,
                        "content_type": fetched.content_type,
                        "byte_count": fetched.byte_count,
                    }
                    raw_text = fetched.text
                else:
                    observation = None
                    raw_text = fetched
                documents[url] = (
                    strip_markup(raw_text),
                    None,
                    observation,
                )
            except (URLError, OSError, ValueError, UnicodeError) as exc:
                documents[url] = (
                    None,
                    f"{type(exc).__name__}: {exc}",
                    None,
                )
        document, failure, observation = documents[url]
        if document is None:
            checks.append(
                {
                    "claim_id": sample["claim_id"],
                    "source_id": sample["source_id"],
                    "url": url,
                    "status": "unverified",
                    "observation": observation,
                    "detail": f"Could not verify: the source could not be read ({failure}).",
                }
            )
            continue
        missing = [probe for probe in sample["probes"] if probe not in document]
        if missing:
            checks.append(
                {
                    "claim_id": sample["claim_id"],
                    "source_id": sample["source_id"],
                    "url": url,
                    "status": "mismatch",
                    "observation": observation,
                    "missing_probes": missing,
                    "detail": (
                        f"{sample['claim_id']}: extract_or_location does not "
                        f"appear in {url}. Missing: "
                        + " | ".join(probe[:80] for probe in missing)
                    ),
                }
            )
            continue
        check_observation = dict(observation) if observation is not None else None
        if check_observation is not None:
            check_observation["probe_context_sha256s"] = (
                _probe_context_sha256s(document, sample["probes"])
            )
            check_observation["normalized_document_sha256"] = hashlib.sha256(
                document.encode("utf-8")
            ).hexdigest()
        checks.append(
            {
                "claim_id": sample["claim_id"],
                "source_id": sample["source_id"],
                "url": url,
                "status": "verified",
                "observation": check_observation,
                "detail": "Every recorded probe was found in the fetched text.",
            }
        )
    return _finish(
        checks,
        online=True,
        sample_size=len(samples),
        transport=transport,
        skip_reason=None,
    )


def _finish(checks, *, online, sample_size, transport, skip_reason):
    counts = {"verified": 0, "mismatch": 0, "unverified": 0, "skipped": 0}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    if not online:
        status = "skipped"
    elif not checks:
        status = "incomplete"
    elif counts["mismatch"]:
        status = "failed"
    elif counts["unverified"]:
        status = "incomplete"
    else:
        status = "passed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "online": online,
        "transport": transport,
        "skip_reason": skip_reason,
        "sample_size": sample_size,
        "counts": counts,
        "checks": checks,
    }


def _receipt_check_set(ledger, selected_count):
    samples = select_samples(
        ledger,
        sample_size=selected_count if selected_count > 0 else 0,
    )
    return [
        {
            "claim_id": sample["claim_id"],
            "source_id": sample["source_id"],
            "url": sample["url"],
            "probe_sha256s": [
                hashlib.sha256(probe.encode("utf-8")).hexdigest()
                for probe in sample["probes"]
            ],
        }
        for sample in samples
    ]


def issue_source_fidelity_receipt(
    ledger_path,
    receipt_path,
    *,
    now=None,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    sample_size=DEFAULT_SAMPLE_SIZE,
    fetcher=None,
):
    """Run the live check, then write its passing ledger-bound receipt."""
    ledger_path = Path(ledger_path).resolve()
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Evidence ledger could not be read: {exc}") from exc
    result = check_source_fidelity(
        ledger,
        fetcher=fetcher,
        sample_size=max(sample_size, 0),
        online=True,
        timeout=timeout,
    )
    if (
        not isinstance(result, dict)
        or result.get("status") != "passed"
        or result.get("online") is not True
        or result.get("transport") != PRODUCTION_TRANSPORT
        or not result.get("checks")
        or any(
            not isinstance(check, dict)
            or check.get("status") != "verified"
            or not isinstance(check.get("observation"), dict)
            for check in result.get("checks", [])
        )
    ):
        raise ValueError(
            "A source-fidelity receipt requires a non-empty complete online "
            "pass through the production transport."
        )
    all_candidates = select_samples(ledger, sample_size=0)
    selected_count = len(result["checks"])
    minimum = min(DEFAULT_SAMPLE_SIZE, len(all_candidates))
    if selected_count < minimum:
        raise ValueError(
            f"Source-fidelity pass checked {selected_count} source pairs; "
            f"the production policy requires {minimum}."
        )
    expected = _receipt_check_set(ledger, selected_count)
    actual_pairs = [
        (check.get("claim_id"), check.get("source_id"), check.get("url"))
        for check in result["checks"]
    ]
    expected_pairs = [
        (check["claim_id"], check["source_id"], check["url"])
        for check in expected
    ]
    if actual_pairs != expected_pairs:
        raise ValueError(
            "Source-fidelity result does not match the ledger's selected "
            "claim/source pairs."
        )
    checked_at = now or datetime.now(timezone.utc)
    if isinstance(checked_at, date) and not isinstance(checked_at, datetime):
        checked_at = datetime.combine(
            checked_at,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
    receipt_checks = []
    for expected_check, result_check in zip(
        expected, result["checks"], strict=True
    ):
        receipt_checks.append(
            {
                **expected_check,
                "observation": result_check["observation"],
            }
        )
    receipt = {
        "schema_version": 2,
        "status": "passed",
        "online": True,
        "transport": PRODUCTION_TRANSPORT,
        "checked_at": checked_at.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "ledger_path": str(ledger_path),
        "ledger_sha256": file_sha256(ledger_path),
        "ledger_schema_path": str(LEDGER_SCHEMA.resolve()),
        "ledger_schema_sha256": file_sha256(LEDGER_SCHEMA),
        "verifier_path": str(Path(__file__).resolve()),
        "verifier_sha256": file_sha256(__file__),
        "policy": {
            "name": "weighted-source-evidence-v1",
            "candidate_count": len(all_candidates),
            "selected_count": selected_count,
            "minimum_selected": minimum,
        },
        "checks": receipt_checks,
    }
    _atomic_write_json(receipt_path, receipt)
    return result


def validate_source_fidelity_receipt(ledger_path, receipt):
    """Replay all deterministic parts of a source-fidelity receipt."""
    ledger_path = Path(ledger_path).resolve()
    if not isinstance(receipt, dict):
        return ["Source-fidelity receipt root must be an object."]
    errors = []
    if receipt.get("schema_version") != 2:
        errors.append("Source-fidelity receipt has an unsupported schema version.")
    if receipt.get("status") != "passed" or receipt.get("online") is not True:
        errors.append("Source-fidelity receipt does not record an online pass.")
    if receipt.get("transport") != PRODUCTION_TRANSPORT:
        errors.append(
            "Source-fidelity receipt was not issued by the production transport."
        )
    if Path(str(receipt.get("ledger_path", ""))).name != ledger_path.name:
        errors.append("Source-fidelity receipt belongs to a different ledger.")
    try:
        if receipt.get("ledger_sha256") != file_sha256(ledger_path):
            errors.append("Source-fidelity receipt does not match the ledger.")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"Evidence ledger could not be verified: {exc}"]
    if not isinstance(ledger, dict):
        return errors + ["Evidence ledger root must be an object."]
    try:
        recorded_schema_path = validated_artifact_path(
            receipt.get("ledger_schema_path"),
            "Source-fidelity receipt ledger-schema",
        )
    except ValueError as exc:
        errors.append(str(exc))
        recorded_schema_path = None
    if recorded_schema_path is not None and (
        recorded_schema_path != LEDGER_SCHEMA.resolve()
        or receipt.get("ledger_schema_sha256") != file_sha256(LEDGER_SCHEMA)
    ):
        errors.append(
            "Source-fidelity receipt does not use the current ledger schema."
        )
    try:
        recorded_verifier_path = validated_artifact_path(
            receipt.get("verifier_path"),
            "Source-fidelity receipt verifier",
        )
    except ValueError as exc:
        errors.append(str(exc))
        recorded_verifier_path = None
    if recorded_verifier_path is not None and (
        recorded_verifier_path != Path(__file__).resolve()
        or receipt.get("verifier_sha256") != file_sha256(__file__)
    ):
        errors.append(
            "Source-fidelity receipt does not use the current verifier."
        )
    policy = receipt.get("policy")
    policy = policy if isinstance(policy, dict) else {}
    all_candidates = select_samples(ledger, sample_size=0)
    minimum = min(DEFAULT_SAMPLE_SIZE, len(all_candidates))
    selected_count = policy.get("selected_count")
    if (
        policy.get("name") != "weighted-source-evidence-v1"
        or policy.get("candidate_count") != len(all_candidates)
        or policy.get("minimum_selected") != minimum
        or not isinstance(selected_count, int)
        or selected_count < minimum
    ):
        errors.append("Source-fidelity receipt uses a weakened sample policy.")
        selected_count = minimum
    expected = _receipt_check_set(ledger, selected_count)
    receipt_checks = receipt.get("checks")
    receipt_checks = receipt_checks if isinstance(receipt_checks, list) else []
    deterministic_checks = [
        {
            key: check.get(key)
            for key in ("claim_id", "source_id", "url", "probe_sha256s")
        }
        for check in receipt_checks
        if isinstance(check, dict)
    ]
    if deterministic_checks != expected or not expected:
        errors.append(
            "Source-fidelity receipt's claim/source probes do not match the ledger."
        )
    for expected_check, check in zip(expected, receipt_checks, strict=False):
        if not isinstance(check, dict):
            continue
        observation = check.get("observation")
        if not isinstance(observation, dict):
            errors.append("Source-fidelity receipt is missing fetch observations.")
            continue
        final_url = str(observation.get("final_url", ""))
        try:
            requested = urlsplit(expected_check["url"])
            final = urlsplit(final_url)
        except ValueError:
            final = urlsplit("")
            requested = urlsplit("")
        redirects = observation.get("redirects")
        response_hash = str(observation.get("response_sha256", ""))
        document_hash = str(
            observation.get("normalized_document_sha256", "")
        )
        context_hashes = observation.get("probe_context_sha256s")
        content_type = observation.get("content_type")
        byte_count = observation.get("byte_count")
        if (
            observation.get("requested_url") != expected_check["url"]
            or final.scheme not in {"http", "https"}
            or not final.hostname
            or not _same_source_host(
                requested.hostname or "", final.hostname or ""
            )
            or not isinstance(redirects, list)
            or any(not isinstance(item, str) for item in redirects)
            or re.fullmatch(r"[0-9a-f]{64}", response_hash) is None
            or re.fullmatch(r"[0-9a-f]{64}", document_hash) is None
            or not isinstance(context_hashes, list)
            or len(context_hashes) != len(expected_check["probe_sha256s"])
            or any(
                not isinstance(probe_hashes, list)
                or not probe_hashes
                or any(
                    not isinstance(value, str)
                    or re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in probe_hashes
                )
                for probe_hashes in context_hashes
            )
            or content_type not in SUPPORTED_TEXT_TYPES | {"application/pdf"}
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or byte_count > MAX_FETCH_BYTES
        ):
            errors.append(
                "Source-fidelity receipt contains invalid fetch observations."
            )
    try:
        checked_day = datetime.fromisoformat(
            str(receipt.get("checked_at", "")).replace("Z", "+00:00")
        ).date()
        report_day = date.fromisoformat(str(ledger.get("report_date")))
    except ValueError:
        errors.append("Source-fidelity receipt has an invalid checked_at date.")
    else:
        # A report date is editorial/local while checked_at is UTC. Their
        # calendar dates may legitimately differ by one day near midnight.
        if (
            (report_day - checked_day).days > 1
            or (checked_day - report_day).days > 30
        ):
            errors.append(
                "Source-fidelity receipt is outside the report freshness window."
            )
    return errors


def validate_source_fidelity_receipt_online(
    ledger_path,
    receipt,
    *,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    fetcher=None,
):
    """Re-read the receipt's source set before authorizing final delivery."""
    errors = validate_source_fidelity_receipt(ledger_path, receipt)
    if errors:
        return errors
    ledger_path = Path(ledger_path).resolve()
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Evidence ledger could not be re-read: {exc}"]
    selected_count = receipt["policy"]["selected_count"]
    result = check_source_fidelity(
        ledger,
        fetcher=fetcher,
        sample_size=selected_count,
        online=True,
        timeout=timeout,
    )
    live_errors = fidelity_errors(result)
    if result.get("transport") != PRODUCTION_TRANSPORT:
        live_errors.append(
            "Final delivery did not use the production source transport."
        )
    expected_pairs = [
        (check["claim_id"], check["source_id"], check["url"])
        for check in receipt["checks"]
    ]
    actual_pairs = [
        (check.get("claim_id"), check.get("source_id"), check.get("url"))
        for check in result.get("checks", [])
        if isinstance(check, dict)
    ]
    if actual_pairs != expected_pairs:
        live_errors.append(
            "Final delivery re-read a different source/probe selection."
        )
    for recorded, current in zip(
        receipt["checks"],
        result.get("checks", []),
        strict=False,
    ):
        recorded_observation = recorded.get("observation")
        current_observation = (
            current.get("observation") if isinstance(current, dict) else None
        )
        if not isinstance(recorded_observation, dict) or not isinstance(
            current_observation, dict
        ):
            continue
        if recorded_observation.get(
            "probe_context_sha256s"
        ) != current_observation.get("probe_context_sha256s"):
            live_errors.append(
                f"{recorded.get('claim_id')}: source evidence context changed "
                "since the source-fidelity receipt was issued."
            )
        if recorded_observation.get(
            "normalized_document_sha256"
        ) != current_observation.get("normalized_document_sha256"):
            live_errors.append(
                f"{recorded.get('claim_id')}: normalized source document "
                "changed since the source-fidelity receipt was issued."
            )
    return [
        f"Fresh live source verification failed: {error}"
        for error in live_errors
    ]


def fidelity_errors(result, *, allow_unverified=False, allow_skip=False):
    """Return the blocking errors in a source-fidelity result."""
    if not isinstance(result, dict):
        return ["Source-fidelity result must be an object."]
    errors = []
    if result.get("status") == "skipped" and not allow_skip:
        errors.append(
            "Source fidelity was skipped; no extract was checked against a "
            "live source. Rerun with --online."
        )
    if result.get("status") == "incomplete" and not result.get("checks"):
        errors.append(
            "Source fidelity is incomplete; the ledger produced no "
            "claim/source evidence pairs to verify."
        )
    for check in result.get("checks", []):
        if not isinstance(check, dict):
            continue
        if check.get("status") == "mismatch":
            errors.append(check.get("detail", "Extract does not match source."))
        elif check.get("status") == "unverified" and not allow_unverified:
            errors.append(
                f"{check.get('claim_id')}: {check.get('detail')} Re-read it by "
                "hand, or rerun with --allow-unverified to record the gap."
            )
    return errors


def build_parser():
    parser = argparse.ArgumentParser(
        description="Re-read cited sources and check the recorded extracts"
    )
    parser.add_argument("ledger", help="Evidence ledger JSON")
    parser.add_argument(
        "--online",
        action="store_true",
        help="fetch the sampled sources; without it the pass is skipped loudly",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="number of claim/source pairs to re-read (0 checks all)",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--out", help="write the machine-readable result here")
    parser.add_argument(
        "--force-output",
        action="store_true",
        help="replace an existing --out result; input/output collisions stay forbidden",
    )
    parser.add_argument(
        "--receipt",
        help="write a passing ledger-bound source-fidelity receipt here",
    )
    return parser


def _run_pdf_worker():
    try:
        payload = sys.stdin.buffer.read(MAX_FETCH_BYTES + 1)
        if len(payload) > MAX_FETCH_BYTES:
            raise ValueError(f"PDF exceeds {MAX_FETCH_BYTES} bytes.")
        text = _extract_pdf_text(payload)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv == [PDF_WORKER_ARGUMENT]:
        return _run_pdf_worker()
    args = build_parser().parse_args(argv)
    collisions = artifact_collision_errors(
        {"ledger": args.ledger},
        {"receipt": args.receipt, "out": args.out},
    )
    if collisions:
        for error in collisions:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    if args.force_output and not args.out:
        print("[FAIL] --force-output requires --out.", file=sys.stderr)
        return 1
    if args.out and Path(args.out).exists() and not args.force_output:
        print(
            f"[FAIL] Source-fidelity result already exists: {args.out}",
            file=sys.stderr,
        )
        return 1
    if args.receipt and Path(args.receipt).exists():
        print(
            f"[FAIL] Source-fidelity receipt already exists: {args.receipt}",
            file=sys.stderr,
        )
        return 1
    try:
        ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.receipt and not args.online:
        print(
            "[FAIL] A source-fidelity receipt requires --online.",
            file=sys.stderr,
        )
        return 2
    try:
        if args.receipt:
            result = issue_source_fidelity_receipt(
                args.ledger,
                args.receipt,
                timeout=args.timeout,
                sample_size=max(args.sample_size, 0),
            )
        else:
            result = check_source_fidelity(
                ledger,
                sample_size=max(args.sample_size, 0),
                online=args.online,
                timeout=args.timeout,
            )
    except (OSError, ValueError) as exc:
        print(f"[FAIL] Source-fidelity receipt: {exc}", file=sys.stderr)
        return 1
    if args.out:
        try:
            _atomic_write_json(
                args.out,
                result,
                overwrite=args.force_output,
            )
        except OSError as exc:
            print(f"[FAIL] Source-fidelity result could not be written: {exc}",
                  file=sys.stderr)
            return 1

    if result["status"] == "skipped":
        print(f"[SKIP] {result['skip_reason']}", file=sys.stderr)
        print(
            f"[SKIP] {result['sample_size']} claim/source pair(s) were not "
            "re-read. This is not a pass.",
            file=sys.stderr,
        )
    for check in result["checks"]:
        if check["status"] == "unverified":
            print(f"[WARN] {check['claim_id']}: {check['detail']}",
                  file=sys.stderr)

    errors = fidelity_errors(
        result,
        allow_unverified=False,
        allow_skip=False,
    )
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 2 if result.get("status") in {"skipped", "incomplete"} else 1

    print(
        f"[OK] Source fidelity {result['status']}: "
        f"{result['counts']['verified']} verified, "
        f"{result['counts']['unverified']} unverified, "
        f"{result['counts']['skipped']} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
