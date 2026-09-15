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
import time
import unicodedata
from contextlib import suppress
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from artifact_safety import (  # noqa: E402
    artifact_collision_errors,
    publish_temp_file,
    validated_artifact_path,
)
from report_contract import canonical_visible_text  # noqa: E402

try:
    from gate_severity import Finding
except (ImportError, AttributeError):  # T2 owns Finding; local stand-in until merge
    @dataclass
    class Finding:
        family: str
        severity: str
        klass: str
        ids: list
        message: str
        fix: str
        remove: str = ""

SCHEMA_VERSION = 1
DEFAULT_SAMPLE_SIZE = 8
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_FETCH_ATTEMPTS = 2
POLICY_V1 = "weighted-source-evidence-v1"
POLICY_V2 = "weighted-source-evidence-v2"
FAMILIES = (
    "fidelity/mismatch",
    "fidelity/context-changed",
    "fidelity/cache-missing",
)
CONTEXT_MARKERS = re.compile(
    r"更正|撤回|訂正|勘误|correction|retract|erratum|update",
    re.I,
)
MAX_FETCH_BYTES = 4_000_000
MAX_DOCUMENT_PAGES = 500
MAX_DOCUMENT_TEXT_CHARACTERS = 5_000_000
MAX_DOCUMENT_PARSE_SECONDS = 20
PDF_WORKER_MEMORY_LIMIT_BYTES = 1024**3
PDF_WORKER_CPU_LIMIT_SECONDS = 15
PDF_WORKER_ARGUMENT = "--decode-pdf-worker"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
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
    charset: str = "utf-8"


@dataclass
class FetchResult:
    status: str
    reason_class: str
    reason: str
    text: str
    charset: str
    url: str
    final_url: str
    aliases: list
    http_status: int | None
    title: str
    published: str | None
    text_sha256: str


def _registrable_domain(host):
    host = (host or "").casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) < 2:
        return host
    last_two = ".".join(parts[-2:])
    extra = {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "com.cn",
        "com.hk",
        "co.jp",
    }
    if last_two in extra and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def _same_registrable_domain(first, second):
    return _registrable_domain(first) == _registrable_domain(second)


def _fffd_ratio(text):
    if not text:
        return 0.0
    return text.count("\ufffd") / len(text)


def _undecodable_text(text):
    return _fffd_ratio(text) > 0.01


def _header_charset(headers):
    raw = (headers or {}).get("content-type", "")
    match = re.search(r"(?i)\bcharset\s*=\s*[\"']?([^;\"'\s]+)", raw)
    return match.group(1).strip() if match else None


def _bom_charset(payload):
    if payload.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if payload.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if payload.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return None


def _meta_charsets(payload):
    head = payload[:16384].decode("latin-1", errors="replace")
    named = re.search(
        r"<meta\b[^>]*?\bcharset\s*=\s*[\"']?([\w.-]+)",
        head,
        re.I,
    )
    equiv = re.search(
        r"<meta\b[^>]*http-equiv\s*=\s*[\"']?content-type[\"']?[^>]*"
        r"content\s*=\s*[\"'][^\"']*charset\s*=\s*([\w.-]+)",
        head,
        re.I,
    )
    if equiv is None:
        equiv = re.search(
            r"<meta\b[^>]*content\s*=\s*[\"'][^\"']*charset\s*=\s*([\w.-]+)"
            r"[^>]*http-equiv\s*=\s*[\"']?content-type",
            head,
            re.I,
        )
    return (
        named.group(1) if named else None,
        equiv.group(1) if equiv else None,
    )


def _normalize_charset_label(label):
    folded = (label or "").strip().casefold()
    if folded in {"gbk", "gb2312", "gb-2312"}:
        return "gb18030"
    if folded == "utf-8-sig":
        return "utf-8-sig"
    return label.strip() if label else ""


def _try_decode_bytes(payload, encoding, *, strict):
    encoding = _normalize_charset_label(encoding)
    if not encoding:
        return None
    try:
        text = payload.decode(encoding, errors="strict")
    except (LookupError, UnicodeDecodeError, ValueError):
        if strict:
            return None
        try:
            text = payload.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError, ValueError):
            return None
    if _undecodable_text(text):
        return None
    return text


def decode_text_payload(payload, headers):
    """Charset ladder: header → BOM → meta charset → http-equiv → utf-8 → gb18030."""
    header_cs = _header_charset(headers)
    bom_cs = _bom_charset(payload)
    meta_cs, equiv_cs = _meta_charsets(payload)
    steps = []
    for item, strict in (
        (header_cs, False),
        (bom_cs, False),
        (meta_cs, False),
        (equiv_cs, False),
        ("utf-8", True),
        ("gb18030", False),
    ):
        if not item:
            continue
        label = item if item != "utf-8-sig" else "utf-8-sig"
        steps.append((label, strict or item.casefold() == "utf-8"))
    declared = {
        _normalize_charset_label(item).casefold()
        for item in (header_cs, bom_cs, meta_cs, equiv_cs)
        if item
    }
    seen = set()
    for encoding, strict in steps:
        key = encoding.casefold()
        if key in seen:
            continue
        seen.add(key)
        text = _try_decode_bytes(payload, encoding, strict=strict)
        if text is not None:
            charset = "utf-8" if encoding == "utf-8-sig" else encoding
            if charset.casefold() in {"gbk", "gb2312"} or (
                _normalize_charset_label(encoding) == "gb18030"
                and (meta_cs or "").casefold() in {"gbk", "gb2312"}
            ):
                charset = "gbk"
            return text, charset
        label = _normalize_charset_label(encoding).casefold()
        aliases = {label, encoding.casefold(), "utf-8" if label == "utf-8-sig" else label}
        if declared & aliases:
            try:
                dirty = payload.decode(
                    _normalize_charset_label(encoding), errors="replace"
                )
            except (LookupError, UnicodeDecodeError, ValueError):
                dirty = ""
            if _undecodable_text(dirty):
                return None, None
    return None, None


def _extract_title(html):
    match = re.search(r"<title\b[^>]*>(.*?)</title>", str(html or ""), re.I | re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_published(html):
    text = str(html or "")
    patterns = (
        r"<meta\b[^>]*(?:property|name)\s*=\s*[\"']article:published_time[\"'][^>]*"
        r"content\s*=\s*[\"']([^\"']+)",
        r"<meta\b[^>]*content\s*=\s*[\"']([^\"']+)[\"'][^>]*"
        r"(?:property|name)\s*=\s*[\"']article:published_time",
        r"<meta\b[^>]*name\s*=\s*[\"']date[\"'][^>]*content\s*=\s*[\"']([^\"']+)",
        r"<meta\b[^>]*content\s*=\s*[\"']([^\"']+)[\"'][^>]*name\s*=\s*[\"']date[\"']",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return None


def cache_paths(cache_dir, source_id):
    root = Path(cache_dir)
    return root / f"{source_id}.txt", root / f"{source_id}.meta.json"


def write_cache(cache_dir, source_id, result: FetchResult) -> None:
    txt, meta_path = cache_paths(cache_dir, source_id)
    visible = strip_markup(result.text) if result.text else ""
    digest = hashlib.sha256(visible.encode("utf-8")).hexdigest()
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    txt.write_text(visible + ("\n" if visible and not visible.endswith("\n") else ""), encoding="utf-8")
    probe_contexts = {}
    if meta_path.is_file():
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if isinstance(previous, dict) and isinstance(previous.get("probe_contexts"), dict):
            probe_contexts = previous["probe_contexts"]
    meta = {
        "url": result.url,
        "final_url": result.final_url,
        "aliases": list(result.aliases or []),
        "http_status": result.http_status,
        "charset": result.charset,
        "title": result.title,
        "published": result.published,
        "fetched_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "text_sha256": digest,
        "transport": PRODUCTION_TRANSPORT,
        "probe_contexts": probe_contexts,
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def record_probe_contexts(cache_dir, source_id, claim_id, probes) -> None:
    cached = read_cache(cache_dir, source_id)
    if cached is None:
        raise ValueError(f"No cache for {source_id}")
    text, meta = cached
    contexts = dict(meta.get("probe_contexts") or {})
    contexts[str(claim_id)] = _probe_context_sha256s(
        normalize_text(text),
        list(probes or []),
    )
    meta["probe_contexts"] = contexts
    cache_paths(cache_dir, source_id)[1].write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_cache(cache_dir, source_id):
    txt, meta_path = cache_paths(cache_dir, source_id)
    if not txt.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    return txt.read_text(encoding="utf-8"), meta


def _empty_fetch(url, *, status, reason_class, reason, http_status=None):
    return FetchResult(
        status=status,
        reason_class=reason_class,
        reason=reason,
        text="",
        charset="",
        url=str(url or ""),
        final_url=str(url or ""),
        aliases=[str(url or "")] if url else [],
        http_status=http_status,
        title="",
        published=None,
        text_sha256=hashlib.sha256(b"").hexdigest(),
    )


def _map_fetch_exception(url, exc):
    message = str(exc)
    folded = message.casefold()
    if isinstance(exc, TimeoutError) or "timed out" in folded or "timeout" in folded:
        klass = "timeout"
    elif isinstance(exc, ssl.SSLError) or folded.startswith("tls"):
        klass = "tls"
    elif isinstance(exc, socket.gaierror) or "could not be resolved" in folded:
        klass = "dns"
    elif "undecodable" in folded:
        return _empty_fetch(
            url,
            status="undecodable",
            reason_class="unknown",
            reason=message,
        )
    elif "exceeds" in folded and "bytes" in folded:
        klass = "oversize"
    elif "redirect loop" in folded:
        klass = "redirect-loop"
    elif "cross-domain-redirect" in folded:
        klass = "cross-domain-redirect"
    elif "plaintext" in folded or "must use https" in folded:
        klass = "plaintext-http"
    else:
        match = re.search(r"HTTP (\d{3})", message)
        klass = f"http-{match.group(1)}" if match else "http-000"
    return _empty_fetch(url, status="unreachable", reason_class=klass, reason=message)


def fetch_document(url, *, cache_dir=None, refresh=False, timeout=10, deadline=None):
    """Fetch one URL through the production transport and decode it."""
    now = time.time()
    if deadline is not None and float(deadline) <= now:
        return _empty_fetch(
            url,
            status="unreachable",
            reason_class="timeout",
            reason="deadline expired",
        )
    if deadline is not None:
        timeout = min(float(timeout), max(0.0, float(deadline) - now))
    raw_url = str(url or "")
    if raw_url.casefold().startswith("http://"):
        return _empty_fetch(
            raw_url,
            status="unreachable",
            reason_class="plaintext-http",
            reason="use https://; plaintext HTTP is not fetched here",
        )
    if cache_dir and not refresh:
        cache_root = Path(cache_dir)
        if cache_root.is_dir():
            for meta_path in cache_root.glob("*.meta.json"):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                aliases = [meta.get("url"), meta.get("final_url"), *(meta.get("aliases") or [])]
                if raw_url in aliases:
                    source_id = meta_path.name[: -len(".meta.json")]
                    cached = read_cache(cache_dir, source_id)
                    if cached:
                        text, stored = cached
                        return FetchResult(
                            status="ok",
                            reason_class="",
                            reason="",
                            text=text,
                            charset=str(stored.get("charset") or ""),
                            url=str(stored.get("url") or raw_url),
                            final_url=str(stored.get("final_url") or raw_url),
                            aliases=list(stored.get("aliases") or []),
                            http_status=stored.get("http_status"),
                            title=str(stored.get("title") or ""),
                            published=stored.get("published"),
                            text_sha256=str(stored.get("text_sha256") or ""),
                        )
    try:
        fetched = default_fetcher(raw_url, timeout=timeout)
    except (URLError, OSError, ValueError, UnicodeError, ssl.SSLError) as exc:
        mapped = _map_fetch_exception(raw_url, exc)
        if mapped.reason_class == "cross-domain-redirect":
            match = re.search(r"cross-domain-redirect → (\S+)", mapped.reason)
            if match:
                mapped.reason = f"cross-domain-redirect → {match.group(1)}"
                mapped.final_url = match.group(1)
        http_match = re.search(r"HTTP (\d{3})", mapped.reason)
        if http_match:
            mapped.http_status = int(http_match.group(1))
            mapped.reason_class = f"http-{http_match.group(1)}"
        return mapped
    if fetched.content_type == "application/pdf":
        text, charset = fetched.text, "utf-8"
    else:
        text, charset = fetched.text, getattr(fetched, "charset", "") or "utf-8"
    if _undecodable_text(text):
        return _empty_fetch(
            raw_url,
            status="undecodable",
            reason_class=charset or "unknown",
            reason=f"U+FFFD ratio {_fffd_ratio(text):.3f} exceeds 0.01",
        )
    visible = strip_markup(text)
    aliases = list(dict.fromkeys([raw_url, fetched.final_url, *fetched.redirects]))
    return FetchResult(
        status="ok",
        reason_class="",
        reason="",
        text=text,
        charset=charset,
        url=raw_url,
        final_url=fetched.final_url,
        aliases=aliases,
        http_status=200,
        title=_extract_title(text),
        published=_extract_published(text),
        text_sha256=hashlib.sha256(visible.encode("utf-8")).hexdigest(),
    )


def validate_public_http_url(url, *, resolver=None):
    """Resolve one HTTPS target or reject it before any connection."""
    resolver = resolver or socket.getaddrinfo
    try:
        parsed = urlsplit(str(url or ""))
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Malformed source URL: {url!r}") from exc
    scheme = parsed.scheme.casefold()
    if scheme == "http":
        raise ValueError(
            "Plaintext HTTP sources are not accepted; "
            "source URLs must use HTTPS."
        )
    elif scheme != "https":
        raise ValueError("Source URLs must use HTTPS.")
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


def _folded_text(value):
    """Fold width, whitespace, quotation marks, and case; keep word spacing."""
    text = unicodedata.normalize("NFKC", canonical_visible_text(value))
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
                "「": '"',
                "」": '"',
                "『": '"',
                "』": '"',
                "，": ",",
                "。": ".",
                "、": ",",
            }
        )
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_text(value):
    """`_folded_text` with every space removed: spacing is never fidelity.

    A page printing "认真 .从1915年" and an extract quoting "认真.从1915年" are
    the same words, so both sides of every comparison drop whitespace.
    """
    return re.sub(r"\s+", "", _folded_text(value))


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
    return _folded_text(" ".join(parser.parts))


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


_ELLIPSIS_SPLIT = re.compile(r"\.\.\.|…")


def _extract_segments(extract, document=None):
    """Split an extract into the pieces that must appear in the source.

    Literal-whole-first (spec §7.2.3): an extract that occurs verbatim in the
    normalized document is one segment. The segment rule exists only to catch a
    fabricated tail around an author-inserted ellipsis, so quote glyphs, list
    markers and in-source ellipses must not strand orphan fragments when the
    whole window is already verbatim. Piece length is never a fabrication
    signal (ruling R13): every non-empty piece must occur, whatever its length.
    """
    text = str(extract or "").strip()
    if not text:
        return []
    if document is not None:
        whole = normalize_text(text)
        if whole and whole in document:
            return [text]
    parts = []
    outside = []
    cursor = 0
    for match in _QUOTE_SPANS.finditer(text):
        outside.append(text[cursor : match.start()])
        outside.append("\n")
        quoted = next(group for group in match.groups() if group is not None)
        parts.extend(_ELLIPSIS_SPLIT.split(quoted))
        cursor = match.end()
    outside.append(text[cursor:])
    parts.extend(re.split(r"[;\n]|\.\.\.|…", "".join(outside)))
    segments = []
    for part in parts:
        normalized = normalize_text(part)
        if (
            normalized
            and any(character.isalnum() for character in normalized)
            and not normalized.rstrip().endswith(":")
        ):
            segments.append(part)
    if not segments and any(character.isalnum() for character in text):
        segments.append(text)
    return segments


def probe_strings(extract):
    """Return the substrings that must survive in the fetched source text.

    Quoted spans are verbatim evidence and every substantive unquoted segment
    is evidence too. Locator-only prefixes such as ``Pricing page:`` identify
    where to look, but do not claim that the label itself appears on the page.
    Ellipsis splits both inside and outside quoted spans.
    """
    probes = []
    for segment in _extract_segments(extract):
        probes.extend(_probe_windows(segment))
    seen = set()
    unique = []
    for probe in probes:
        if probe and probe not in seen:
            seen.add(probe)
            unique.append(probe)
    return unique


def probe_findings(claim, source, text, *, cache_meta=None, extract=None):
    """Offline probe of one claim/source extract against cached text.

    R22: one source may carry several evidence entries, so the caller names the
    entry to probe; without one, the first entry for the source is probed.
    """
    claim = claim if isinstance(claim, dict) else {}
    source = source if isinstance(source, dict) else {}
    claim_id = str(claim.get("claim_id") or "")
    source_id = str(source.get("source_id") or "")
    evidence = claim.get("source_evidence")
    if extract is None and isinstance(evidence, list):
        for entry in evidence:
            if isinstance(entry, dict) and entry.get("source_id") == source_id:
                extract = entry.get("extract_or_location")
                break
    if extract is None:
        extract = claim.get("extract_or_location")
    document = normalize_text(strip_markup(text) if "<" in str(text or "") else text)
    findings = []
    segments = _extract_segments(extract, document)
    usable = []
    for segment in segments:
        normalized = normalize_text(segment)
        usable.append(normalized)
        windows = _probe_windows(segment)
        missing = [window for window in windows if window not in document]
        if missing:
            findings.append(
                Finding(
                    family="fidelity/mismatch",
                    severity="hard",
                    klass="F",
                    ids=[claim_id, source_id],
                    message=(
                        f"{claim_id}: extract_or_location does not appear in "
                        f"{source.get('url') or source_id}. Missing: "
                        + " | ".join(item[:80] for item in missing)
                    ),
                    fix=f"alx find {source_id} <keyword>",
                    remove=f"alx claim drop {claim_id} --apply",
                )
            )
    if cache_meta and isinstance(cache_meta, dict) and usable:
        stored = cache_meta.get("probe_contexts")
        recorded = None
        if isinstance(stored, dict):
            recorded = stored.get(claim_id)
        if recorded:
            current = _probe_context_sha256s(document, probe_strings(extract))
            if current != recorded:
                window = usable[0][:120]
                markers = CONTEXT_MARKERS.findall(str(text or ""))
                marker_note = (
                    f" markers: {', '.join(dict.fromkeys(markers))}"
                    if markers
                    else ""
                )
                findings.append(
                    Finding(
                        # R28: a changed context is a re-read prompt, not
                        # fabrication; it is reported and never blocks.
                        family="fidelity/context-changed",
                        severity="warn",
                        klass="A",
                        ids=[claim_id, source_id],
                        message=(
                            f"{source_id} context changed since research; re-read. "
                            f"Window: {window}{marker_note}"
                        ),
                        fix=f"alx fetch --id {source_id} --refresh",
                        remove=f"alx claim drop {claim_id} --apply",
                    )
                )
    return findings


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
            if not _same_registrable_domain(original_host, redirected.host):
                raise ValueError(
                    f"cross-domain-redirect → {redirected.url}"
                )
            redirects.append(redirected.url)
            current = redirected
            continue
        if status < 200 or status >= 300:
            raise ValueError(f"Source returned HTTP {status}.")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if content_type == "application/pdf":
            text = _decode_document(payload, content_type, None)
            charset = "utf-8"
        elif content_type in SUPPORTED_TEXT_TYPES:
            decoded, charset = decode_text_payload(payload, headers)
            if decoded is None:
                raise ValueError("undecodable source text")
            text = decoded
        else:
            raise ValueError(f"Unsupported source content type: {content_type or 'missing'}")
        return FetchedDocument(
            text=text,
            final_url=current.url,
            redirects=tuple(redirects),
            response_sha256=hashlib.sha256(payload).hexdigest(),
            content_type=content_type,
            byte_count=len(payload),
            charset=charset,
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
                    "extract": extract,
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


def _evaluate_sample(sample, document, observation, failure, *, fail_status="unreachable"):
    if document is None:
        return {
            "claim_id": sample["claim_id"],
            "source_id": sample["source_id"],
            "url": sample["url"],
            "status": fail_status,
            "observation": observation,
            "detail": (
                f"Could not verify: the source could not be read ({failure})."
            ),
        }
    missing = [probe for probe in sample["probes"] if probe not in document]
    if missing:
        return {
            "claim_id": sample["claim_id"],
            "source_id": sample["source_id"],
            "url": sample["url"],
            "status": "mismatch",
            "observation": observation,
            "missing_probes": missing,
            "detail": (
                f"{sample['claim_id']}: extract_or_location does not "
                f"appear in {sample['url']}. Missing: "
                + " | ".join(probe[:80] for probe in missing)
            ),
        }
    check_observation = dict(observation) if observation is not None else None
    if check_observation is not None:
        check_observation["probe_context_sha256s"] = _probe_context_sha256s(
            document, sample["probes"]
        )
        check_observation["normalized_document_sha256"] = hashlib.sha256(
            document.encode("utf-8")
        ).hexdigest()
    return {
        "claim_id": sample["claim_id"],
        "source_id": sample["source_id"],
        "url": sample["url"],
        "status": "verified",
        "observation": check_observation,
        "detail": "Every recorded probe was found in the fetched text.",
    }


def _load_fetched(url, fetched):
    if isinstance(fetched, FetchResult):
        if fetched.status == "undecodable":
            return None, fetched.reason or fetched.status, None, "undecodable"
        if fetched.status != "ok":
            return None, fetched.reason or fetched.status, None, "unreachable"
        observation = {
            "requested_url": url,
            "final_url": fetched.final_url,
            "redirects": [item for item in fetched.aliases if item != url],
            "response_sha256": fetched.text_sha256,
            "content_type": "text/html",
            "byte_count": len(fetched.text.encode("utf-8", errors="replace")),
        }
        return normalize_text(strip_markup(fetched.text)), None, observation, None
    if isinstance(fetched, FetchedDocument):
        observation = {
            "requested_url": url,
            "final_url": fetched.final_url,
            "redirects": list(fetched.redirects),
            "response_sha256": fetched.response_sha256,
            "content_type": fetched.content_type,
            "byte_count": fetched.byte_count,
        }
        return normalize_text(strip_markup(fetched.text)), None, observation, None
    return normalize_text(strip_markup(fetched)), None, None, None


def check_source_fidelity(
    ledger,
    *,
    fetcher=None,
    sample_size=DEFAULT_SAMPLE_SIZE,
    online=False,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    cache_dir=None,
    deadline=None,
):
    """Re-read a weighted sample of sources and return a machine-readable result."""
    samples = select_samples(ledger, sample_size)
    pool = select_samples(ledger, 0)
    checks = []
    refreshed = []
    findings = []
    if not online and not cache_dir:
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

    fetch = fetcher
    if fetch is None and online:
        def fetch(url):
            return fetch_document(
                url,
                cache_dir=cache_dir,
                refresh=True,
                timeout=timeout,
                deadline=deadline,
            )
    if not online:
        transport = None
    elif fetcher is None:
        transport = PRODUCTION_TRANSPORT
    else:
        transport = "test"
    documents = {}

    def resolve(sample):
        url = sample["url"]
        source_id = sample["source_id"]
        if not online and cache_dir:
            cached = read_cache(cache_dir, source_id)
            if cached is None:
                findings.append(
                    Finding(
                        family="fidelity/cache-missing",
                        severity="hard",
                        klass="F",
                        ids=[sample["claim_id"], source_id],
                        message=(
                            f"{source_id}: cache missing (need "
                            f"sources/{source_id}.txt)"
                        ),
                        fix=f"alx fetch --id {source_id} --refresh",
                        remove=f"alx claim drop {sample['claim_id']} --apply",
                    )
                )
                return _evaluate_sample(
                    sample,
                    None,
                    None,
                    "cache-missing",
                    fail_status="unreachable",
                )
            text, meta = cached
            document = normalize_text(text)
            claim = {}
            for item in ledger.get("claims") or []:
                if isinstance(item, dict) and item.get("claim_id") == sample["claim_id"]:
                    claim = item
                    break
            if not claim:
                claim = {
                    "claim_id": sample["claim_id"],
                    "source_evidence": [
                        {
                            "source_id": source_id,
                            "extract_or_location": sample.get("extract"),
                        }
                    ],
                }
            extra = probe_findings(
                claim,
                {"source_id": source_id, "url": url},
                text,
                cache_meta=meta,
            )
            findings.extend(extra)
            observation = {
                "requested_url": url,
                "final_url": meta.get("final_url") or url,
                "redirects": list(meta.get("aliases") or []),
                "response_sha256": meta.get("text_sha256") or "",
                "content_type": "text/html",
                "byte_count": len(text.encode("utf-8")),
            }
            return _evaluate_sample(sample, document, observation, None)
        if url not in documents:
            try:
                fetched = fetch(url)
                document, failure, observation, fail_status = _load_fetched(
                    url, fetched
                )
                documents[url] = (document, failure, observation, fail_status)
                if (
                    cache_dir
                    and online
                    and isinstance(fetched, FetchResult)
                    and fetched.status == "ok"
                ):
                    write_cache(cache_dir, source_id, fetched)
                    refreshed.append(source_id)
                elif cache_dir and online and document is not None:
                    write_cache(
                        cache_dir,
                        source_id,
                        FetchResult(
                            status="ok",
                            reason_class="",
                            reason="",
                            text=fetched if isinstance(fetched, str) else getattr(
                                fetched, "text", ""
                            ),
                            charset=getattr(fetched, "charset", "utf-8"),
                            url=url,
                            final_url=getattr(fetched, "final_url", url),
                            aliases=[url],
                            http_status=200,
                            title=_extract_title(
                                fetched if isinstance(fetched, str) else getattr(
                                    fetched, "text", ""
                                )
                            ),
                            published=_extract_published(
                                fetched if isinstance(fetched, str) else getattr(
                                    fetched, "text", ""
                                )
                            ),
                            text_sha256="",
                        ),
                    )
                    refreshed.append(source_id)
            except (URLError, OSError, ValueError, UnicodeError) as exc:
                documents[url] = (
                    None,
                    f"{type(exc).__name__}: {exc}",
                    None,
                    "unreachable",
                )
        document, failure, observation, fail_status = documents[url]
        return _evaluate_sample(
            sample,
            document,
            observation,
            failure,
            fail_status=fail_status or "unreachable",
        )

    used = set()
    for sample in samples:
        check = resolve(sample)
        used.add((sample["claim_id"], sample["source_id"]))
        if check["status"] in {"unreachable", "undecodable"}:
            replacement = next(
                (
                    previous
                    for previous in checks
                    if previous.get("claim_id") == sample["claim_id"]
                    and previous.get("status") == "verified"
                ),
                None,
            )
            if replacement is not None:
                check = replacement
            else:
                for alt in pool:
                    key = (alt["claim_id"], alt["source_id"])
                    if alt["claim_id"] != sample["claim_id"] or key == (
                        sample["claim_id"],
                        sample["source_id"],
                    ):
                        continue
                    alt_check = resolve(alt)
                    used.add(key)
                    if alt_check["status"] not in {"unreachable", "undecodable"}:
                        check = alt_check
                        break
        checks.append(check)

    central = set()
    synthesis = ledger.get("synthesis") if isinstance(ledger, dict) else None
    if isinstance(synthesis, dict):
        raw = synthesis.get("central_judgment_claim_ids", [])
        central = set(raw) if isinstance(raw, list) else set()
    disclosure = [
        check["claim_id"]
        for check in checks
        if check.get("claim_id") in central
        and check.get("status") in {"unreachable", "undecodable"}
    ]
    finished = _finish(
        checks,
        online=online,
        sample_size=len(checks),
        transport=transport,
        skip_reason=None,
    )
    finished["refreshed_source_ids"] = list(dict.fromkeys(refreshed))
    finished["disclosure_required"] = list(dict.fromkeys(disclosure))
    finished["findings"] = [_finding_payload(item) for item in findings]
    return finished


def _finding_payload(item):
    if isinstance(item, dict):
        return item
    if is_dataclass(item):
        return asdict(item)
    return {
        "family": getattr(item, "family", ""),
        "severity": getattr(item, "severity", "hard"),
        "klass": getattr(item, "klass", "F"),
        "ids": list(getattr(item, "ids", []) or []),
        "message": getattr(item, "message", ""),
        "fix": getattr(item, "fix", ""),
        "remove": getattr(item, "remove", ""),
    }


def _finish(checks, *, online, sample_size, transport, skip_reason):
    counts = {
        "verified": 0,
        "mismatch": 0,
        "unreachable": 0,
        "undecodable": 0,
        "skipped": 0,
    }
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    unverified = counts["unreachable"] + counts["undecodable"]
    if skip_reason and all(check.get("status") == "skipped" for check in checks):
        status = "skipped"
    elif not online and checks and any(
        check.get("status") != "skipped" for check in checks
    ):
        if counts["mismatch"]:
            status = "failed"
        elif unverified:
            status = "incomplete"
        else:
            status = "passed"
    elif not online:
        status = "skipped"
    elif not checks:
        status = "incomplete"
    elif counts["mismatch"]:
        status = "failed"
    elif unverified:
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
        "unverified": unverified,
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


def _receipt_rows_from_checks(ledger, checks):
    catalog = {
        (sample["claim_id"], sample["source_id"], sample["url"]): sample
        for sample in select_samples(ledger, 0)
    }
    rows = []
    for check in checks:
        sample = catalog.get(
            (check.get("claim_id"), check.get("source_id"), check.get("url"))
        )
        if sample is None:
            raise ValueError(
                "Source-fidelity result does not match the ledger's "
                "claim/source pairs."
            )
        rows.append(
            {
                "claim_id": sample["claim_id"],
                "source_id": sample["source_id"],
                "url": sample["url"],
                "probe_sha256s": [
                    hashlib.sha256(probe.encode("utf-8")).hexdigest()
                    for probe in sample["probes"]
                ],
            }
        )
    return rows


def issue_source_fidelity_receipt(
    ledger_path,
    receipt_path,
    *,
    now=None,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    sample_size=DEFAULT_SAMPLE_SIZE,
    fetcher=None,
    policy=POLICY_V2,
    cache_dir=None,
    deadline=None,
    force=False,
    result=None,
):
    """Run the live check, then write its passing ledger-bound receipt."""
    ledger_path = Path(ledger_path).resolve()
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Evidence ledger could not be read: {exc}") from exc
    if result is None:
        result = check_source_fidelity(
            ledger,
            fetcher=fetcher,
            sample_size=max(sample_size, 0),
            online=True,
            timeout=timeout,
            cache_dir=cache_dir,
            deadline=deadline,
        )
    checks = result.get("checks") if isinstance(result, dict) else []
    mismatch = any(
        isinstance(check, dict) and check.get("status") == "mismatch"
        for check in checks
    )
    unverified = sum(
        1
        for check in checks
        if isinstance(check, dict)
        and check.get("status") in {"unreachable", "undecodable"}
    )
    rate = (unverified / len(checks)) if checks else 1.0
    v2_ok = (
        policy == POLICY_V2
        and not mismatch
        and rate <= 0.25
        and result.get("online") is True
        and result.get("transport") == PRODUCTION_TRANSPORT
        and checks
    )
    v1_ok = (
        policy == POLICY_V1
        and result.get("status") == "passed"
        and result.get("online") is True
        and result.get("transport") == PRODUCTION_TRANSPORT
        and checks
        and all(
            isinstance(check, dict)
            and check.get("status") == "verified"
            and isinstance(check.get("observation"), dict)
            for check in checks
        )
    )
    if not v2_ok and not v1_ok:
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
    if policy == POLICY_V1:
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
    else:
        expected = _receipt_rows_from_checks(ledger, result["checks"])
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
            "name": policy if policy in {POLICY_V1, POLICY_V2} else POLICY_V2,
            "candidate_count": len(all_candidates),
            "selected_count": selected_count,
            "minimum_selected": minimum,
            "unverified_rate": rate,
            "disclosure_required": list(result.get("disclosure_required") or []),
        },
        "checks": receipt_checks,
        "disclosure_required": list(result.get("disclosure_required") or []),
        "refreshed_source_ids": list(result.get("refreshed_source_ids") or []),
    }
    _atomic_write_json(receipt_path, receipt, overwrite=force)
    result = dict(result)
    result["disclosure_required"] = receipt["disclosure_required"]
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
        policy.get("name") not in {POLICY_V1, POLICY_V2}
        or policy.get("candidate_count") != len(all_candidates)
        or policy.get("minimum_selected") != minimum
        or not isinstance(selected_count, int)
        or selected_count < minimum
    ):
        errors.append("Source-fidelity receipt uses a weakened sample policy.")
        selected_count = minimum
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
    policy_name = policy.get("name")
    if policy_name == POLICY_V1:
        expected = _receipt_check_set(ledger, selected_count)
        if deterministic_checks != expected or not expected:
            errors.append(
                "Source-fidelity receipt's claim/source probes do not match the ledger."
            )
    else:
        try:
            expected = _receipt_rows_from_checks(ledger, receipt_checks)
        except ValueError:
            errors.append(
                "Source-fidelity receipt's claim/source probes do not match the ledger."
            )
            expected = []
        if deterministic_checks != expected or not expected:
            errors.append(
                "Source-fidelity receipt's claim/source probes do not match the ledger."
            )
    for expected_check, check in zip(expected, receipt_checks, strict=False):
        if not isinstance(check, dict):
            continue
        observation = check.get("observation")
        if not isinstance(observation, dict):
            if policy_name == POLICY_V1:
                errors.append(
                    "Source-fidelity receipt is missing fetch observations."
                )
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
            or not _same_registrable_domain(
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
    return [
        f"Fresh live source verification failed: {error}"
        for error in live_errors
    ]


def fidelity_errors(result, *, policy=None, allow_skip=False):
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
    checks = [
        check for check in result.get("checks", []) if isinstance(check, dict)
    ]
    mismatch = any(check.get("status") == "mismatch" for check in checks)
    unverified = sum(
        1
        for check in checks
        if check.get("status") in {"unreachable", "undecodable"}
    )
    rate = (unverified / len(checks)) if checks else 1.0
    tolerate_unverified = (
        policy == POLICY_V2 and not mismatch and rate <= 0.25
    )
    for check in checks:
        if check.get("status") == "mismatch":
            errors.append(check.get("detail", "Extract does not match source."))
        elif (
            check.get("status") in {"unreachable", "undecodable"}
            and not tolerate_unverified
        ):
            errors.append(
                f"{check.get('claim_id')}: {check.get('detail')} Re-read it by "
                "hand."
            )
    for item in result.get("findings") or []:
        payload = _finding_payload(item)
        if payload.get("severity") == "hard" or payload.get("klass") == "F":
            errors.append(
                payload.get("message") or payload.get("family") or "finding"
            )
    return errors


def _receipt_is_stale(receipt_path, ledger_path):
    path = Path(receipt_path)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    return payload.get("ledger_sha256") != file_sha256(ledger_path)


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
        "--force",
        action="store_true",
        help="overwrite an existing --out or --receipt file",
    )
    parser.add_argument(
        "--cache-dir",
        help="read/write sources/S<n>.txt cache for offline and online passes",
    )
    parser.add_argument(
        "--explain",
        metavar="C<n>",
        help="print probes for one claim without fetching",
    )
    parser.add_argument(
        "--receipt",
        help="write a passing ledger-bound source-fidelity receipt here",
    )
    return parser


def _run_pdf_worker():
    if resource is not None:
        for kind, limit in (
            (resource.RLIMIT_AS, PDF_WORKER_MEMORY_LIMIT_BYTES),
            (resource.RLIMIT_CPU, PDF_WORKER_CPU_LIMIT_SECONDS),
        ):
            # Some kernels reject limits below the interpreter's current
            # reservation; the parent process timeout remains in force.
            with suppress(OSError, ValueError):
                resource.setrlimit(kind, (limit, limit))
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
    force = bool(getattr(args, "force", False) or args.force_output)
    if args.force_output and not args.out:
        print("[FAIL] --force-output requires --out.", file=sys.stderr)
        return 1
    if args.out and Path(args.out).exists() and not force:
        print(
            f"[FAIL] Source-fidelity result already exists: {args.out}",
            file=sys.stderr,
        )
        return 1
    if (
        args.receipt
        and Path(args.receipt).exists()
        and not force
        and not _receipt_is_stale(args.receipt, args.ledger)
    ):
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

    if getattr(args, "explain", None):
        claim_id = args.explain
        for claim in ledger.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("claim_id") != claim_id:
                continue
            evidence = claim.get("source_evidence") or []
            printed = False
            if isinstance(evidence, list):
                for entry in evidence:
                    if not isinstance(entry, dict):
                        continue
                    for probe in probe_strings(entry.get("extract_or_location")):
                        print(probe)
                        printed = True
            if not printed:
                for probe in probe_strings(claim.get("extract_or_location")):
                    print(probe)
            return 0
        print(f"[FAIL] Unknown claim {claim_id}", file=sys.stderr)
        return 1

    if args.receipt and not args.online:
        print(
            "[FAIL] A source-fidelity receipt requires --online.",
            file=sys.stderr,
        )
        return 2
    try:
        result = check_source_fidelity(
            ledger,
            sample_size=max(args.sample_size, 0),
            online=args.online,
            timeout=args.timeout,
            cache_dir=getattr(args, "cache_dir", None),
        )
    except (OSError, ValueError) as exc:
        print(f"[FAIL] Source-fidelity receipt: {exc}", file=sys.stderr)
        return 1

    def print_sections(payload):
        groups = {
            "mismatch": [],
            "unreachable": [],
            "undecodable": [],
            "verified": [],
        }
        for check in payload.get("checks") or []:
            groups.setdefault(check.get("status"), [])
            if check.get("status") in groups:
                groups[check["status"]].append(check)
        for name in ("mismatch", "unreachable", "undecodable", "verified"):
            items = groups.get(name) or []
            if not items:
                continue
            print(f"=== {name.upper()} {len(items)} ===", file=sys.stderr)
            for check in items:
                print(
                    f"{check.get('claim_id')}: {check.get('detail')}",
                    file=sys.stderr,
                )

    errors = fidelity_errors(
        result,
        policy=POLICY_V2 if args.receipt else None,
        allow_skip=False,
    )
    if args.receipt and errors:
        print_sections(result)
        print(
            "[FAIL] Source-fidelity receipt refused after failing checks.",
            file=sys.stderr,
        )
        return 1 if result.get("status") == "failed" else 2
    if args.receipt and not errors:
        try:
            result = issue_source_fidelity_receipt(
                args.ledger,
                args.receipt,
                timeout=args.timeout,
                sample_size=max(args.sample_size, 0),
                cache_dir=getattr(args, "cache_dir", None),
                force=force or _receipt_is_stale(args.receipt, args.ledger),
                result=result,
            )
        except (OSError, ValueError) as exc:
            print_sections(result)
            print(f"[FAIL] Source-fidelity receipt: {exc}", file=sys.stderr)
            return 1
    if args.out:
        try:
            _atomic_write_json(
                args.out,
                result,
                overwrite=force,
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
    print_sections(result)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 2 if result.get("status") in {"skipped", "incomplete"} else 1

    print(
        f"[OK] Source fidelity {result['status']}: "
        f"{result['counts']['verified']} verified, "
        f"{result['counts'].get('unreachable', 0)} unreachable, "
        f"{result['counts'].get('undecodable', 0)} undecodable, "
        f"{result['counts']['skipped']} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
