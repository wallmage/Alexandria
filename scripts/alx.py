#!/usr/bin/env python3
"""Alexandria's single entry point: one CLI over the research gates.

`alx` is thin orchestration over the existing modules used as libraries
(spec 09-14-01 §5). Free text enters only through files; every command
appends one worklog line and prints the elapsed/remaining footer last.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (  # noqa: E402
    content_gate,
    gate_severity,
    report_contract,
    rewild_gate,
    source_fidelity,
    validate_ledger,
    validate_report,
)

LANGUAGES = ("en", "zh-CN", "zh-HK")
ARCHETYPES = (
    "person",
    "organization",
    "artifact",
    "event",
    "concept",
    "system",
    "hybrid",
)
LIVING_STATUSES = ("living", "recently_deceased", "deceased", "unknown")
PROTECTED_STATUSES = frozenset({"living", "recently_deceased", "unknown"})
PROVENANCES = (
    "primary_independent",
    "primary_interested",
    "secondary_independent",
    "secondary_dependent",
    "unverified",
)
EVIDENCE_TYPES = (
    "accountable_record",
    "peer_reviewed",
    "preprint",
    "official_documentation",
    "dataset_or_test",
    "reported_interview",
    "news_report",
    "opinion_or_forecast",
    "marketing",
    "anecdote",
)
SOURCE_ROLES = (
    "subject_official",
    "counterparty_official",
    "independent_analysis",
    "empirical_data",
    "affected_stakeholder",
    "expert_interpretation",
    "historical_record",
)
ACCOUNTABILITY_BASES = (
    "none",
    "court_or_regulator_record",
    "named_source_investigation",
    "subject_admission",
)
REVIEW_KINDS = ("rewild", "content")

CONTENT_SCORE_KEYS = (
    "question_answered",
    "evidence_strength",
    "evidence_coverage",
    "reasoning_integrity",
    "counterevidence",
    "explanatory_depth",
    "decision_value",
    "writing_clarity",
)
CONTENT_CHECK_KEYS = (
    "central_judgment_answers_question",
    "priority_coverage_resolved",
    "key_claims_traceable",
    "source_independence_calibrated",
    "counterevidence_tested",
    "uncertainty_visible",
    "recommendations_or_implications_supported",
    "forecasts_conditional",
    "section_value_density_reviewed",
    "length_is_substantive_not_padded",
)

VERIFICATION_NOTE_PREFIX = {
    "en": "Verification note:",
    "zh-CN": "核查说明：",
    "zh-HK": "核實說明：",
}

#: Every printed remedy (spec D14). Commands parse; the rest are the closed
#: imperative list of spec §6.
REMEDY_TEMPLATES = {
    "fetch-refresh": "alx fetch --id {source_id} --refresh",
    "claim-add": "alx claim add {file}",
    "claim-drop": "alx claim drop {claim_id} --apply",
    "claim-bind": "alx claim bind {claim_id} --paragraph {paragraph}",
    "ledger-merge": "alx ledger merge {file}",
    "source-set": "alx source set {source_id} --provenance primary_independent",
    "find": "alx find {source_id} {keyword}",
    "snapshot-restore": "alx snapshot --restore",
    "review-start": "alx review start {kind}",
    "review-iter": "alx review start {kind} --iter",
    "review-restore": "alx review restore {kind}",
    "check": "alx check",
    "check-fix": "alx check --fix",
    "issue": "alx issue",
    "issue-deliver": "alx issue --deliver",
    "render": "alx render",
    "set-field": "set field {field} in {file}",
    "extend-quote": "extend the quote in {file}",
    "delete-paragraph": "delete paragraph {paragraph} of report.md",
}

#: Class A families (spec §6.10); every other hard family defaults to Class F.
CLASS_A_FAMILIES = frozenset(
    {
        "fidelity/unreachable",
        "tooling/receipt",
        "tooling/render",
        "review/rewild-missing",
        "review/rewild-stale",
        "rewild/humanization",
        "rewild/style",
        "rewild/ai-vocabulary",
        "integrity/length",
        "integrity/structure",
        "binding/sources-section",
    }
)

RESERVE_MINUTES = 8
FETCH_STOP_MINUTES = 20
DEGRADE_MINUTES = 15
ONLINE_CAP_MINUTES = 4
EXCERPT_CHARS = 60
MIN_EXTRACT_CHARS = 20
MIN_SEGMENT_CHARS = 8
MAX_WINDOW_CHARS = 300

DEGRADE_INSTRUCTION = (
    "remaining <= 15 min: stop fixing, run `alx issue --deliver`, then `alx render`."
)


def remedy(key, **values):
    """Return one pinned remedy string from the registry."""
    return REMEDY_TEMPLATES[key].format(**values)


if hasattr(gate_severity, "Finding"):  # T2 owns the shared dataclass.
    Finding = gate_severity.Finding
else:

    @dataclass
    class Finding:
        """Library form of one grouped finding (plan: pinned interfaces)."""

        family: str
        severity: str = "hard"
        klass: str = "F"
        ids: list = field(default_factory=list)
        message: str = ""
        fix: str = ""
        remove: str = ""


def finding_class(family, severity):
    """Class F unless the family is listed as availability/tooling."""
    if severity == "warn":
        return "A"
    return "A" if family in CLASS_A_FAMILIES else "F"


def finding(family, message, *, severity="hard", ids=(), fix="", remove=""):
    return Finding(
        family=family,
        severity=severity,
        klass=finding_class(family, severity),
        ids=list(ids),
        message=message,
        fix=fix,
        remove=remove,
    )


def _group(findings):
    grouped = {}
    for item in findings:
        grouped.setdefault(item.family, []).append(item)
    return grouped


def _family_lines(findings, per_family):
    lines = []
    for family, members in _group(findings).items():
        lines.append(f"[{family}] {len(members)}")
        for member in members[:per_family]:
            head = ",".join(member.ids)
            text = f"  {head}: {member.message}" if head else f"  {member.message}"
            if member.fix:
                text += f" Fix: {member.fix}"
            if member.remove:
                text += f" Remove: {member.remove}"
            lines.append(text)
        if len(members) > per_family:
            lines.append(f"  +{len(members) - per_family} more")
    return lines


def _render_grouped(findings, *, per_family=5):
    """Spec §6.7 output block; replaced by gate_severity.render_grouped (T2)."""
    hard = [item for item in findings if item.severity != "warn"]
    warn = [item for item in findings if item.severity == "warn"]
    lines = [f"=== HARD {len(hard)} (blocks issue) ==="]
    lines.extend(_family_lines(hard, per_family))
    lines.append(f"=== WARN {len(warn)} ===")
    lines.extend(_family_lines(warn, per_family))
    return "\n".join(lines)


def render_grouped(findings, *, per_family=5):
    renderer = getattr(gate_severity, "render_grouped", _render_grouped)
    return renderer(findings, per_family=per_family)


def hard_findings(findings):
    return [item for item in findings if item.severity != "warn"]


def class_f_findings(findings):
    return [item for item in hard_findings(findings) if item.klass == "F"]


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _now():
    return datetime.now(timezone.utc)


class Workspace:
    """The report directory layout of spec §5."""

    def __init__(self, directory):
        self.dir = Path(directory).resolve()
        self.report = self.dir / "report.md"
        self.ledger_path = self.dir / "ledger.json"
        self.sources = self.dir / "sources"
        self.claims = self.dir / "claims"
        self.reviews = self.dir / "reviews"
        self.receipts = self.dir / "receipts"
        self.alx = self.dir / ".alx"
        self.state_path = self.alx / "state.json"
        self.worklog = self.dir / "worklog.md"

    def load_state(self):
        return _read_json(self.state_path)

    def save_state(self, state):
        _write_json(self.state_path, state)

    def load_ledger(self):
        return _read_json(self.ledger_path)

    def save_ledger(self, ledger):
        _write_json(self.ledger_path, ledger)

    def report_text(self):
        return self.report.read_bytes().decode("utf-8")

    def cache_paths(self, source_id):
        return (
            self.sources / f"{source_id}.txt",
            self.sources / f"{source_id}.meta.json",
        )

    def snapshots(self):
        base = self.dir / "report.pre-rewild.md"
        found = [base] if base.exists() else []
        iterations = sorted(
            self.dir.glob("report.pre-rewild.iter*.md"),
            key=lambda path: int(re.search(r"iter(\d+)", path.name).group(1)),
        )
        return found + iterations

    def latest_snapshot(self):
        snapshots = self.snapshots()
        return snapshots[-1] if snapshots else None

    def review_dir(self, kind, iteration):
        return self.alx / "reviews" / kind / str(iteration)


def _minutes(state):
    start = datetime.fromisoformat(state["start_time"])
    deadline = datetime.fromisoformat(state["deadline"])
    now = _now()
    elapsed = max(0, int((now - start).total_seconds() // 60))
    remaining = int((deadline - now).total_seconds() // 60)
    return elapsed, remaining


def _emit(ws, state, command, summary, lines):
    """Print the command output, append the worklog line, print the footer."""
    for line in lines:
        print(line)
    elapsed, remaining = _minutes(state)
    stamp = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    with ws.worklog.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {command} {summary}\n")
    if remaining <= DEGRADE_MINUTES:
        print(DEGRADE_INSTRUCTION)
    print(f"elapsed {max(elapsed, 0)} min, remaining {max(remaining, 0)} min")


def _open(args):
    """Return (workspace, state, ledger) for an initialized directory."""
    ws = Workspace(args.dir)
    if not ws.state_path.exists():
        raise SystemExit(
            f"No Alexandria workspace in {ws.dir}. Run `alx init {ws.dir} "
            "--lang en --subject subject.txt` first."
        )
    return ws, ws.load_state(), ws.load_ledger()


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

_QUOTED_SPAN_RE = re.compile(
    r"「([^」]{4,}?)」|『([^』]{4,}?)』|“([^”]{4,}?)”|‘([^’]{4,}?)’|\"([^\"\n]{4,}?)\""
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_url(value):
    """lowercase scheme/host, strip fragment, utm_*, trailing slash (spec §6.7c)."""
    parts = urlsplit(str(value or "").strip())
    query = "&".join(
        item
        for item in parts.query.split("&")
        if item and not item.casefold().startswith("utm_")
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


def quoted_spans(text):
    spans = []
    for match in _QUOTED_SPAN_RE.finditer(str(text or "")):
        span = next(group for group in match.groups() if group is not None)
        spans.append(span.strip())
    return [span for span in spans if len(span) >= 4]


def _blocks(text):
    """Return (start, end, text) for every blank-line separated block."""
    blocks = []
    start = 0
    for match in re.finditer(r"\n[ \t]*\n", text + "\n\n"):
        end = min(match.start(), len(text))
        if text[start:end].strip():
            blocks.append((start, end, text[start:end]))
        start = match.end()
        if start >= len(text):
            break
    return blocks


def sources_heading_offset(text):
    offset = None
    for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE):
        if match.group(1).strip().casefold() in validate_report.SOURCE_HEADINGS:
            offset = match.start()
    return offset


def body_paragraphs(text):
    """Numbered body paragraphs: (number, start, end, text)."""
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    masked = _FENCE_RE.sub(lambda match: " " * len(match.group(0)), body)
    numbered = []
    number = 0
    for start, end, block in _blocks(masked):
        first = block.lstrip().splitlines()[0]
        if first.startswith(("#", ">", "```", "|")):
            continue
        number += 1
        numbered.append((number, start, end, body[start:end]))
    return numbered


def markdown_links(text):
    return [(match.group(1), match.group(2)) for match in _LINK_RE.finditer(text)]


def masked_prose(text):
    """Link-stripped, whitespace-folded prose used by the freshness diff."""
    stripped = _LINK_RE.sub(lambda match: match.group(1), text)
    return re.sub(r"\s+", " ", stripped).strip()


def sentence_window(text, start, length, context):
    """Sentence-bounded verbatim window, no ellipsis, <= 300 chars."""
    left = max(0, start - context)
    right = min(len(text), start + length + context)
    boundaries = "。！？!?；;\n"
    head = start
    while head > left and text[head - 1] not in boundaries:
        head -= 1
    tail = start + length
    while tail < right and text[tail - 1] not in boundaries:
        tail += 1
    window = text[head:tail].strip()
    if len(window) > MAX_WINDOW_CHARS:
        window = window[:MAX_WINDOW_CHARS].strip()
    return window


# --------------------------------------------------------------------------
# fetch and cache
# --------------------------------------------------------------------------


@dataclass
class FetchOutcome:
    status: str
    reason_class: str = ""
    reason: str = ""
    text: str = ""
    charset: str = "utf-8"
    url: str = ""
    final_url: str = ""
    aliases: list = field(default_factory=list)
    http_status: int = None
    title: str = ""
    published: str = None
    text_sha256: str = ""


_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_CHARSET_RE = re.compile(r"(?i)<meta[^>]+charset=[\"']?([\w-]+)")
_PUBLISHED_RE = re.compile(
    r"(?is)<meta[^>]+(?:property|name)=[\"'](?:article:published_time|date|"
    r"pubdate)[\"'][^>]*content=[\"']([^\"']+)[\"']"
)


def _visible_text(document):
    parser = source_fidelity._VisibleTextParser()
    parser.feed(document)
    parser.close()
    visible = report_contract.canonical_visible_text(" ".join(parser.parts))
    return re.sub(r"[ \t ]+", " ", visible).strip()


def _reason_class(error):
    message = str(error)
    if "different host" in message:
        return "cross-domain-redirect"
    if "redirect loop" in message:
        return "redirect-loop"
    if "exceeds" in message and "bytes" in message:
        return "oversize"
    match = re.search(r"HTTP (\d{3})", message)
    if match:
        return f"http-{match.group(1)}"
    if "timed out" in message or isinstance(error, TimeoutError):
        return "timeout"
    if "certificate" in message.casefold() or "ssl" in message.casefold():
        return "tls"
    return "dns"


def fetch_document(url, *, timeout=10, deadline=None):
    """Fetch one URL through T1's `fetch_document` when it exists."""
    pinned = getattr(source_fidelity, "fetch_document", None)
    if pinned is not None:
        return pinned(url, timeout=timeout, deadline=deadline)
    try:
        document = source_fidelity.default_fetcher(url, timeout=timeout)
    except Exception as exc:  # every transport failure is an outcome, not a crash
        return FetchOutcome(
            status="unreachable",
            reason_class=_reason_class(exc),
            reason=str(exc),
            url=url,
        )
    text = _visible_text(document.text)
    if not text:
        return FetchOutcome(
            status="undecodable",
            reason_class="undecodable",
            reason="The page carried no readable text.",
            url=url,
        )
    title_match = _TITLE_RE.search(document.text)
    charset_match = _CHARSET_RE.search(document.text)
    published_match = _PUBLISHED_RE.search(document.text)
    return FetchOutcome(
        status="ok",
        text=text,
        charset=charset_match.group(1).casefold() if charset_match else "utf-8",
        url=url,
        final_url=document.final_url,
        aliases=list(document.redirects),
        http_status=200,
        title=(title_match.group(1).strip() if title_match else document.final_url),
        published=(published_match.group(1)[:10] if published_match else None),
        text_sha256=_sha256_text(text),
    )


def write_cache(ws, source_id, result, *, requested_url, aliases):
    text_path, meta_path = ws.cache_paths(source_id)
    ws.sources.mkdir(parents=True, exist_ok=True)
    text_path.write_text(result.text, encoding="utf-8")
    meta = {
        "url": result.final_url,
        "final_url": result.final_url,
        "aliases": aliases,
        "http_status": result.http_status,
        "charset": result.charset,
        "title": result.title,
        "published": result.published,
        "fetched_at": _now().isoformat(),
        "text_sha256": result.text_sha256 or _sha256_text(result.text),
        "transport": getattr(source_fidelity, "PRODUCTION_TRANSPORT", ""),
    }
    _write_json(meta_path, meta)
    return meta


def read_cache(ws, source_id):
    text_path, meta_path = ws.cache_paths(source_id)
    if not text_path.exists() or not meta_path.exists():
        return None
    return text_path.read_text(encoding="utf-8"), _read_json(meta_path)


def _registrable_domain(url):
    return validate_ledger._registrable_domain(url)


def _next_id(items, prefix, key):
    used = {
        int(item[key][1:])
        for item in items
        if isinstance(item.get(key), str) and item[key][1:].isdigit()
    }
    number = 1
    while number in used:
        number += 1
    return f"{prefix}{number}"


def _source_by_url(ledger, url):
    normalized = normalize_url(url)
    for source in ledger.get("sources", []):
        known = {normalize_url(source.get("url", ""))}
        known.update(normalize_url(alias) for alias in source.get("aliases", []))
        if normalized in known:
            return source
    return None


# --------------------------------------------------------------------------
# probes
# --------------------------------------------------------------------------


def extract_segments(extract):
    return [
        segment.strip()
        for segment in re.split(r"\.\.\.|…", str(extract or ""))
        if segment.strip()
    ]


def missing_probes(extract, cache_text):
    """Return the probe windows of one extract that the cache does not carry."""
    haystack = source_fidelity.normalize_text(cache_text)
    missing = []
    for segment in extract_segments(extract):
        for probe in source_fidelity.probe_strings(segment):
            if probe not in haystack:
                missing.append(probe)
    return missing


def probe_findings(ws, claim, evidence):
    source_id = evidence.get("source_id", "")
    extract = evidence.get("extract_or_location", "")
    claim_id = claim.get("claim_id", "")
    cached = read_cache(ws, source_id)
    if cached is None:
        return [
            finding(
                "fidelity/cache-missing",
                f"{source_id} has no fetched cache; the extract cannot be probed.",
                ids=[claim_id, source_id],
                fix=remedy("fetch-refresh", source_id=source_id),
                remove=remedy("claim-drop", claim_id=claim_id),
            )
        ]
    missing = missing_probes(extract, cached[0])
    if not missing:
        return []
    return [
        finding(
            "fidelity/mismatch",
            f"extract not found in {source_id}: {missing[0][:80]}",
            ids=[claim_id, source_id],
            fix=remedy("find", source_id=source_id, keyword=_keyword(missing[0])),
            remove=remedy("claim-drop", claim_id=claim_id),
        )
    ]


def _keyword(text):
    word = re.split(r"\s+", str(text).strip())[0]
    return word or "keyword"


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def _skeleton_report(subject, lang, report_day):
    date_line = report_contract.localized_date(lang, report_day)
    if lang == "en":
        standfirst = "Standfirst placeholder: one sentence on what this report decides."
        sources = "## Sources"
    else:
        standfirst = "导语占位：一句话说明本报告要回答的问题。"
        sources = "## 资料来源"
    return f"# {subject}\n\n> {standfirst}\n> {date_line}\n\n{sources}\n"


def _skeleton_ledger(args, subject, question, reader, report_day):
    ledger = {
        "schema_version": 4,
        "subject": subject,
        "research_question": question,
        "brief": {
            "intended_reader": reader,
            "decision_or_use": question,
            "archetype": args.archetype,
            "report_language": args.lang,
            "editorial_mode": "analytical",
            "scope": {
                "time_horizon": "Set in `alx ledger merge`.",
                "geography": "Set in `alx ledger merge`.",
                "inclusions": [],
                "exclusions": [],
            },
        },
        "people": [],
        "report_date": report_day.isoformat(),
        "coverage": [],
        "sources": [],
        "claims": [],
        "excluded_claims": [],
        "synthesis": {
            "central_judgment_claim_ids": [],
            "counterevidence_claim_ids": [],
            "adversarial_tests": [],
            "implications": [],
            "decisions_or_takeaways": [],
            "scenarios": [],
            "limitations": "Set in `alx ledger merge`.",
            "research_stop_reason": "Set in `alx ledger merge`.",
        },
        "unresolved_questions": [],
    }
    if args.archetype == "person":
        ledger["people"].append(
            {
                "person_id": "P1",
                "name": subject,
                "aliases": [],
                "living_status": args.subject_status,
                "public_role": "public",
                "relationship": "primary_subject",
            }
        )
    return ledger


def cmd_init(args):
    ws = Workspace(args.directory)
    if ws.ledger_path.exists() and not args.force:
        print(
            f"{ws.ledger_path} exists; `alx init` refuses to overwrite it. "
            "Use --force to reset the workspace.",
            file=sys.stderr,
        )
        return 1
    if args.archetype == "person" and not args.subject_status:
        print(
            "--subject-status {living,recently_deceased,deceased,unknown} is "
            "required for the person archetype.",
            file=sys.stderr,
        )
        return 1
    subject_text = Path(args.subject).read_text(encoding="utf-8").strip()
    lines = [line.strip() for line in subject_text.splitlines() if line.strip()]
    subject = lines[0] if lines else "Untitled subject"
    question = lines[1] if len(lines) > 1 else subject
    reader = (
        Path(args.reader).read_text(encoding="utf-8").strip()
        if args.reader
        else "Unspecified reader; set it with `alx ledger merge`."
    )
    for directory in (ws.dir, ws.sources, ws.claims, ws.reviews, ws.receipts, ws.alx):
        directory.mkdir(parents=True, exist_ok=True)
    report_day = date.today()
    ws.save_ledger(_skeleton_ledger(args, subject, question, reader, report_day))
    ws.report.write_text(
        _skeleton_report(subject, args.lang, report_day), encoding="utf-8"
    )
    started = _now()
    state = {
        "start_time": started.isoformat(),
        "deadline": (started + timedelta(minutes=args.budget_minutes)).isoformat(),
        "lang": args.lang,
        "archetype": args.archetype,
        "counters": {"fetch": 0, "claims": 0, "check": 0, "issue": 0},
        "reviews": {
            kind: {"iteration": 0, "finished": False} for kind in REVIEW_KINDS
        },
        "bindings": {},
        "mechanical_deletions": [],
        "last_check": {},
        "humanization": "pending",
    }
    ws.save_state(state)
    ws.worklog.touch()
    _emit(
        ws,
        state,
        "init",
        f"{args.lang} {args.archetype} workspace",
        [
            f"Workspace ready: {ws.dir}",
            "Next: `alx fetch <url> ...` for 8-15 reachable sources.",
        ],
    )
    return 0


# --------------------------------------------------------------------------
# fetch / source set
# --------------------------------------------------------------------------


def _upsert_source(ledger, source_id, result, args, aliases):
    domain = _registrable_domain(result.final_url) or ""
    existing = next(
        (
            source
            for source in ledger["sources"]
            if source.get("source_id") == source_id
        ),
        None,
    )
    source = existing or {"source_id": source_id}
    source.update(
        {
            "title": result.title or result.final_url,
            "url": result.final_url,
            "aliases": sorted(set(aliases) - {result.final_url}),
            "publisher": domain.split(".")[0].title() or domain,
            "accessed": date.today().isoformat(),
            "source_family": domain,
            "published": result.published or source.get("published"),
        }
    )
    source.setdefault("author", None)
    source["provenance"] = args.provenance or source.get("provenance", "unverified")
    source["evidence_type"] = args.type or source.get("evidence_type", "news_report")
    source["roles"] = args.role or source.get("roles", ["independent_analysis"])
    source["accountability_basis"] = args.accountability or source.get(
        "accountability_basis", "none"
    )
    if existing is None:
        ledger["sources"].append(source)
    return source


def _fetch_one(ws, ledger, args, url, lines):
    parsed = urlsplit(url)
    if parsed.scheme.casefold() not in {"http", "https"}:
        lines.append(f"{url} REJECTED (non-http scheme) — not added")
        return False
    aliases = [url]
    target = url
    if parsed.scheme.casefold() == "http":
        target = urlunsplit(("https",) + tuple(parsed)[1:])
    existing = _source_by_url(ledger, target) or _source_by_url(ledger, url)
    if existing is not None:
        lines.append(f"{existing['source_id']} already in the ledger: {existing['url']}")
        return True
    result = fetch_document(target, timeout=10)
    source_id = _next_id(ledger["sources"], "S", "source_id")
    if result.status == "unreachable":
        reason_class = result.reason_class or "dns"
        if parsed.scheme.casefold() == "http" and reason_class == "dns":
            reason_class = "plaintext-http"
        lines.append(
            f"{source_id} UNREACHABLE ({reason_class}: {result.reason}) — not added"
        )
        return False
    if result.status != "ok":
        lines.append(f"{source_id} UNDECODABLE ({result.charset}) — not added")
        return False
    aliases.extend(result.aliases)
    aliases.append(target)
    write_cache(ws, source_id, result, requested_url=url, aliases=sorted(set(aliases)))
    _upsert_source(ledger, source_id, result, args, sorted(set(aliases)))
    lines.append(
        f"{source_id} OK {len(result.text)} chars {result.charset} "
        f'"{result.title}" {result.final_url}'
    )
    return True


def _refresh_one(ws, ledger, args, source_id, lines):
    source = next(
        (item for item in ledger["sources"] if item.get("source_id") == source_id),
        None,
    )
    if source is None:
        lines.append(f"{source_id} is not in the ledger — nothing to refresh")
        return False
    cached = read_cache(ws, source_id)
    previous = cached[1].get("text_sha256") if cached else None
    result = fetch_document(source["url"], timeout=10)
    if result.status != "ok":
        lines.append(
            f"{source_id} UNREACHABLE ({result.reason_class}: {result.reason}) "
            "— cache kept"
        )
        return False
    aliases = sorted(set(source.get("aliases", [])) | set(result.aliases))
    write_cache(ws, source_id, result, requested_url=source["url"], aliases=aliases)
    source["accessed"] = date.today().isoformat()
    lines.append(
        f"{source_id} OK {len(result.text)} chars {result.charset} "
        f'"{result.title}" {result.final_url}'
    )
    if previous and previous != (result.text_sha256 or _sha256_text(result.text)):
        affected = [
            claim["claim_id"]
            for claim in ledger.get("claims", [])
            if source_id in claim.get("source_ids", [])
        ]
        if affected:
            lines.append(
                f"{source_id} text changed; claims {','.join(affected)} need re-probe"
            )
        else:
            lines.append(f"{source_id} text changed; no claims use it yet")
    return True


def cmd_fetch(args):
    ws, state, ledger = _open(args)
    lines = []
    ok = True
    if args.id:
        if not args.refresh:
            print("`alx fetch --id S<n>` requires --refresh.", file=sys.stderr)
            return 1
        ok = _refresh_one(ws, ledger, args, args.id, lines)
    else:
        if not args.urls:
            print("`alx fetch` needs one or more URLs.", file=sys.stderr)
            return 1
        for url in args.urls:
            _elapsed, remaining = _minutes(state)
            if remaining < FETCH_STOP_MINUTES:
                lines.append(
                    f"remaining {remaining} min: fetch batch stopped; draft with "
                    "the sources already in the ledger."
                )
                break
            ok = _fetch_one(ws, ledger, args, url, lines) and ok
    ws.save_ledger(ledger)
    state["counters"]["fetch"] = state["counters"].get("fetch", 0) + 1
    ws.save_state(state)
    _emit(ws, state, "fetch", f"{len(ledger['sources'])} sources", lines)
    return 0 if ok else 1


def cmd_source_set(args):
    ws, state, ledger = _open(args)
    source = next(
        (item for item in ledger["sources"] if item.get("source_id") == args.source_id),
        None,
    )
    if source is None:
        print(f"{args.source_id} is not in the ledger.", file=sys.stderr)
        return 1
    if args.provenance:
        source["provenance"] = args.provenance
    if args.type:
        source["evidence_type"] = args.type
    if args.role:
        source["roles"] = args.role
    if args.accountability:
        source["accountability_basis"] = args.accountability
    if args.published:
        source["published"] = args.published
    if args.undated_reason:
        source["undated_reason"] = Path(args.undated_reason).read_text(
            encoding="utf-8"
        ).strip()
    ws.save_ledger(ledger)
    _emit(
        ws,
        state,
        "source set",
        f"{args.source_id} classification",
        [f"{args.source_id} classification updated."],
    )
    return 0


# --------------------------------------------------------------------------
# find / show
# --------------------------------------------------------------------------


def cmd_find(args):
    ws, state, _ledger = _open(args)
    cached = read_cache(ws, args.source_id)
    if cached is None:
        print(f"{args.source_id} has no cache; run `alx fetch`.", file=sys.stderr)
        return 1
    text = cached[0]
    lines = []
    for index, match in enumerate(
        re.finditer(re.escape(args.keyword), text, re.IGNORECASE), start=1
    ):
        if index > args.max:
            break
        window = sentence_window(text, match.start(), len(args.keyword), args.context)
        lines.append(f"{index}. {window}")
    if not lines:
        lines.append(f"{args.source_id} does not contain {args.keyword}.")
    _emit(ws, state, "find", f"{args.source_id} {args.keyword}", lines)
    return 0


def cmd_show(args):
    ws, state, _ledger = _open(args)
    cached = read_cache(ws, args.source_id)
    if cached is None:
        print(f"{args.source_id} has no cache; run `alx fetch`.", file=sys.stderr)
        return 1
    text = cached[0]
    end = args.end if args.end is not None else min(len(text), args.start + 1000)
    lines = [
        f"{args.source_id} chars {args.start}-{min(end, len(text))} of {len(text)}",
        text[args.start : end],
    ]
    _emit(ws, state, "show", f"{args.source_id} window", lines)
    return 0


# --------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------


def _claim_input_schema_findings(item, claim_id):
    """Validate against references/claim-input.schema.json once T2 ships it."""
    schema_path = getattr(
        validate_ledger, "CLAIM_INPUT_SCHEMA", ROOT / "references" / "claim-input.schema.json"
    )
    if not Path(schema_path).exists():
        return []
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(
        _read_json(schema_path), format_checker=FormatChecker()
    )
    return [
        finding(
            "claim-input/schema",
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}",
            ids=[claim_id],
            fix=remedy("set-field", field="claim-input", file="claims/*.json"),
        )
        for error in validator.iter_errors(item)
    ]


def _claim_input_findings(ws, ledger, item, seen_ids):
    claim_id = item.get("claim_id")
    findings = _claim_input_schema_findings(item, claim_id or "<no claim_id>")
    if not isinstance(claim_id, str) or not re.fullmatch(r"C\d+", claim_id):
        findings.append(
            finding(
                "claim-input/schema",
                "claim-input has no `C<n>` claim_id.",
                fix="add claim_id",
            )
        )
        claim_id = claim_id or "<no claim_id>"
    elif claim_id in seen_ids:
        findings.append(
            finding(
                "claim-input/schema",
                f"{claim_id} is already in the ledger.",
                ids=[claim_id],
                fix="add claim_id",
            )
        )
    for key in ("claim", "kind", "importance"):
        if not item.get(key):
            findings.append(
                finding(
                    "claim-input/schema",
                    f"claim-input is missing `{key}`.",
                    ids=[claim_id],
                    fix=remedy("set-field", field=key, file="claims/*.json"),
                )
            )
    if item.get("kind") == "analysis" and not item.get("reasoning"):
        findings.append(
            finding(
                "claim-input/schema",
                "kind=analysis needs `reasoning`.",
                ids=[claim_id],
                fix=remedy("set-field", field="reasoning", file="claims/*.json"),
            )
        )
    if item.get("kind") == "estimate" and not item.get("assumptions"):
        findings.append(
            finding(
                "claim-input/schema",
                "kind=estimate needs `assumptions`.",
                ids=[claim_id],
                fix=remedy("set-field", field="assumptions", file="claims/*.json"),
            )
        )
    role = item.get("person_claim_role")
    if role == "response" and not item.get("responds_to_claim_ids"):
        findings.append(
            finding(
                "claim-input/schema",
                "person_claim_role=response needs `responds_to_claim_ids`.",
                ids=[claim_id],
                fix=remedy(
                    "set-field", field="responds_to_claim_ids", file="claims/*.json"
                ),
            )
        )
    if role == "resolution" and not item.get("resolves_claim_ids"):
        findings.append(
            finding(
                "claim-input/schema",
                "person_claim_role=resolution needs `resolves_claim_ids`.",
                ids=[claim_id],
                fix=remedy(
                    "set-field", field="resolves_claim_ids", file="claims/*.json"
                ),
            )
        )
    evidence = item.get("source_evidence")
    if not isinstance(evidence, list) or not evidence:
        findings.append(
            finding(
                "claim-input/schema",
                "claim-input needs `source_evidence[{source_id, extract_or_location}]`.",
                ids=[claim_id],
                fix=remedy("set-field", field="source_evidence", file="claims/*.json"),
            )
        )
        return findings
    known = {source.get("source_id") for source in ledger.get("sources", [])}
    for record in evidence:
        source_id = record.get("source_id", "")
        extract = str(record.get("extract_or_location", ""))
        if source_id not in known:
            findings.append(
                finding(
                    "claim-input/source",
                    f"{source_id or '<missing>'} is not a fetched source.",
                    ids=[claim_id],
                    fix="alx fetch <url>",
                )
            )
            continue
        normalized = source_fidelity.normalize_text(extract)
        if len(normalized) < MIN_EXTRACT_CHARS:
            findings.append(
                finding(
                    "claim-input/short-extract",
                    f"extract for {source_id} is {len(normalized)} normalized chars; "
                    f"minimum is {MIN_EXTRACT_CHARS}.",
                    ids=[claim_id],
                    fix=remedy("extend-quote", file="claims/*.json"),
                )
            )
            continue
        for segment in extract_segments(extract):
            length = len(source_fidelity.normalize_text(segment))
            if length < MIN_SEGMENT_CHARS:
                findings.append(
                    finding(
                        "claim-input/short-segment",
                        f"an ellipsis segment for {source_id} is {length} normalized "
                        f"chars; minimum is {MIN_SEGMENT_CHARS}.",
                        ids=[claim_id],
                        fix=remedy("extend-quote", file="claims/*.json"),
                    )
                )
    return findings


def _triangulation(ledger, source_ids):
    families = sorted(
        {
            source.get("source_family", "")
            for source in ledger.get("sources", [])
            if source.get("source_id") in source_ids
        }
    )
    if len(families) >= 2:
        return {
            "status": "met",
            "rationale": "Independent source families carry this claim: "
            + ", ".join(families)
            + ".",
        }
    return {
        "status": "limited",
        "rationale": "Only one source family carries this claim: "
        + (families[0] if families else "none")
        + ".",
    }


def expand_claim_input(ws, item, ledger):
    """claim-input -> full v4 claim (spec §6.4)."""
    pinned = getattr(validate_ledger, "expand_claim_input", None)
    evidence = list(item.get("source_evidence", []))
    source_ids = []
    for record in evidence:
        source_id = record.get("source_id")
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    cache_meta = {}
    for source_id in source_ids:
        cached = read_cache(ws, source_id)
        if cached is not None:
            cache_meta[source_id] = cached[1]
    if pinned is not None:
        return pinned(item, ledger, cache_meta=cache_meta)
    verified_at = sorted(
        (meta.get("fetched_at", "")[:10] for meta in cache_meta.values()),
        reverse=True,
    )
    claim = {
        "claim_id": item.get("claim_id"),
        "claim": item.get("claim"),
        "kind": item.get("kind"),
        "importance": item.get("importance"),
        "source_ids": source_ids,
        "extract_or_location": evidence[0].get("extract_or_location", "")
        if evidence
        else "",
        "source_evidence": evidence,
        "as_of": item.get("as_of") or ledger.get("report_date"),
        "verified_at": verified_at[0] if verified_at else None,
        "confidence": item.get("confidence", "medium"),
        "status": item.get("status", "supported"),
        "include_in_report": True,
        "report_excerpts": [],
        "supports": item.get("supports", []),
        "contradicts": item.get("contradicts", []),
        "person_ids": item.get("person_ids", []),
        "human_harm_review": item.get("human_harm_review"),
        "reasoning": item.get("reasoning"),
        "decision_relevance": item.get("decision_relevance"),
        "what_would_change": item.get("what_would_change"),
        "triangulation": _triangulation(ledger, source_ids),
        "resolution": item.get("resolution"),
        "limitations": item.get("limitations"),
    }
    for optional in (
        "assumptions",
        "derived_assertions",
        "time_sensitive",
        "evidence_of_absence",
        "person_claim_role",
        "person_claim_assessment",
        "responds_to_claim_ids",
        "resolves_claim_ids",
        "named_subjects",
    ):
        if optional in item:
            claim[optional] = item[optional]
    return claim


def _ledger_rule_findings(claim):
    findings = []
    for message in validate_ledger.evidence_coverage_errors(claim):
        text = str(message)
        severity = "warn" if gate_severity.is_warning(text) else "hard"
        findings.append(
            finding(
                "ledger/coverage",
                text.removeprefix(gate_severity.WARNING_PREFIX),
                severity=severity,
                ids=[claim.get("claim_id", "")],
                fix=remedy(
                    "find",
                    source_id=(claim.get("source_ids") or ["S1"])[0],
                    keyword=_keyword(claim.get("claim", "")),
                ),
                remove=remedy("claim-drop", claim_id=claim.get("claim_id", "")),
            )
        )
    return findings


def _person_findings(ledger, claim):
    findings = []
    claim_id = claim.get("claim_id", "")
    people = {person.get("person_id"): person for person in ledger.get("people", [])}
    for person_id in claim.get("person_ids", []):
        person = people.get(person_id)
        if person is None:
            findings.append(
                finding(
                    "person/unknown-id",
                    f"{person_id} is not in `people`; add the person first.",
                    ids=[claim_id],
                    fix=remedy("ledger-merge", file="people.json"),
                    remove=remedy("claim-drop", claim_id=claim_id),
                )
            )
            continue
        status = person.get("living_status")
        if status == "unknown":
            findings.append(
                finding(
                    "person/unknown-status",
                    f"{person_id} has living_status unknown; person-linked claims "
                    "are refused until it is set.",
                    ids=[claim_id],
                    fix="set people[0].living_status via `alx ledger merge`",
                    remove=remedy("claim-drop", claim_id=claim_id),
                )
            )
        if status in PROTECTED_STATUSES and claim.get("person_claim_role") in {
            "harmful",
            "sensitive_private_fact",
        }:
            review = claim.get("human_harm_review") or {}
            required = (
                "category",
                "legal_stage",
                "source_floor",
                "accountable_source_ids",
                "attributed_to",
                "sourcing_limitation_excerpt",
                "event_period",
                "resolution_status",
                "resolution_claim_ids",
                "resolution_search",
                "right_of_reply",
                "privacy_basis",
                "privacy_basis_source_ids",
                "governing_question_relevance",
            )
            missing = [key for key in required if key not in review]
            if missing:
                findings.append(
                    finding(
                        "person/harm-review",
                        f"human_harm_review is missing: {', '.join(missing)}.",
                        ids=[claim_id],
                        fix=remedy(
                            "set-field",
                            field="human_harm_review",
                            file="claims/*.json",
                        ),
                        remove=remedy("claim-drop", claim_id=claim_id),
                    )
                )
    return findings


def cmd_claim_add(args):
    ws, state, ledger = _open(args)
    items = []
    for path in args.files:
        payload = _read_json(path)
        items.extend(payload if isinstance(payload, list) else [payload])
    lines = []
    accepted = 0
    failed = False
    seen = {claim.get("claim_id") for claim in ledger.get("claims", [])}
    for item in items:
        claim_id = item.get("claim_id") or "<no claim_id>"
        findings = _claim_input_findings(ws, ledger, item, seen)
        claim = None
        if not findings:
            claim = expand_claim_input(ws, item, ledger)
            findings.extend(_ledger_rule_findings(claim))
            for evidence in claim.get("source_evidence", []):
                findings.extend(probe_findings(ws, claim, evidence))
            findings.extend(_person_findings(ledger, claim))
        for item_finding in findings:
            lines.append(
                f"{claim_id} FAIL [{item_finding.family}] {item_finding.message}"
                f" — fix: {item_finding.fix}"
            )
        if hard_findings(findings) or claim is None:
            failed = True
            continue
        ledger["claims"].append(claim)
        seen.add(claim["claim_id"])
        accepted += 1
        lines.append(f"{claim['claim_id']} added ({len(claim['source_ids'])} sources)")
    ws.save_ledger(ledger)
    state["counters"]["claims"] = len(ledger["claims"])
    ws.save_state(state)
    _emit(ws, state, "claim add", f"{accepted} accepted", lines)
    return 1 if failed else 0


def _claim_paragraph(state, claim):
    binding = state.get("bindings", {}).get(claim.get("claim_id"))
    return binding if binding else claim.get("report_paragraph")


def cmd_claim_bind(args):
    ws, state, ledger = _open(args)
    ids = {claim.get("claim_id") for claim in ledger.get("claims", [])}
    if args.claim_id not in ids:
        print(f"{args.claim_id} is not in the ledger.", file=sys.stderr)
        return 1
    state.setdefault("bindings", {})[args.claim_id] = args.paragraph
    ws.save_state(state)
    _emit(
        ws,
        state,
        "claim bind",
        f"{args.claim_id} -> paragraph {args.paragraph}",
        [f"{args.claim_id} is bound to paragraph {args.paragraph}."],
    )
    return 0


def _drop_plan(ws, state, ledger, claim_id):
    text = ws.report_text()
    mapping, _mapping_findings = paragraph_mapping(ws, state, ledger, text)
    paragraph = mapping.get(claim_id)
    co_mapped = [
        other
        for other, number in mapping.items()
        if number == paragraph and other != claim_id and paragraph is not None
    ]
    dropped = [claim_id, *co_mapped]
    dependents = [
        claim.get("claim_id")
        for claim in ledger.get("claims", [])
        if claim.get("claim_id") not in dropped
        and set(claim.get("supports", [])) & set(dropped)
    ]
    return paragraph, co_mapped, dependents


def cmd_claim_drop(args):
    ws, state, ledger = _open(args)
    claim_id = args.claim_id
    if claim_id not in {claim.get("claim_id") for claim in ledger.get("claims", [])}:
        print(f"{claim_id} is not in the ledger.", file=sys.stderr)
        return 1
    paragraph, co_mapped, dependents = _drop_plan(ws, state, ledger, claim_id)
    lines = [
        f"{claim_id} maps to paragraph {paragraph if paragraph else '<unmapped>'}."
    ]
    if co_mapped:
        lines.append(f"Also dropped (same paragraph): {', '.join(co_mapped)}")
    if dependents:
        lines.append(
            "HARD until re-pointed — claims that support a dropped claim: "
            + ", ".join(dependents)
        )
    if not args.apply:
        lines.append(f"Apply with `{remedy('claim-drop', claim_id=claim_id)}`.")
        _emit(ws, state, "claim drop", f"{claim_id} plan", lines)
        return 0
    dropped = [claim_id, *co_mapped]
    text = ws.report_text()
    if paragraph is not None:
        for number, start, end, block in body_paragraphs(text):
            if number == paragraph:
                state.setdefault("mechanical_deletions", []).append(
                    _sha256_text(masked_prose(block))
                )
                text = text[:start] + text[end:]
                text = re.sub(r"\n{3,}", "\n\n", text)
                break
        ws.report.write_text(text, encoding="utf-8")
        lines.append(f"Deleted paragraph {paragraph} of report.md.")
    stamp = _now().isoformat()
    remaining = []
    ledger.setdefault("excluded_claims", [])
    for claim in ledger.get("claims", []):
        if claim.get("claim_id") in dropped:
            excluded = dict(claim)
            excluded["reason"] = args.reason or "Class-F finding; scope dropped."
            excluded["dropped_at"] = stamp
            ledger["excluded_claims"].append(excluded)
        else:
            remaining.append(claim)
    ledger["claims"] = remaining
    for item in ledger.get("coverage", []):
        item["claim_ids"] = [
            value for value in item.get("claim_ids", []) if value not in dropped
        ]
    synthesis = ledger.get("synthesis", {})
    for key in ("central_judgment_claim_ids", "counterevidence_claim_ids"):
        synthesis[key] = [
            value for value in synthesis.get(key, []) if value not in dropped
        ]
    for bucket in ("adversarial_tests", "implications", "decisions_or_takeaways"):
        for entry in synthesis.get(bucket, []):
            if isinstance(entry, dict) and "claim_ids" in entry:
                entry["claim_ids"] = [
                    value for value in entry["claim_ids"] if value not in dropped
                ]
    for claim_id_dropped in dropped:
        state.get("bindings", {}).pop(claim_id_dropped, None)
    ws.save_ledger(ledger)
    ws.save_state(state)
    _regenerate_sources(ws, ledger)
    lines.append(f"Excluded: {', '.join(dropped)}")
    _emit(ws, state, "claim drop", f"{len(dropped)} excluded", lines)
    return 0


# --------------------------------------------------------------------------
# ledger merge
# --------------------------------------------------------------------------

MERGEABLE = ("brief", "people", "coverage", "synthesis")


def _deep_merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def cmd_ledger_merge(args):
    ws, state, ledger = _open(args)
    patch = _read_json(args.patch)
    forbidden = [key for key in ("claims", "sources") if key in patch]
    if forbidden:
        print(
            "sources only via fetch/source set; claims only via claim add "
            f"(patch carried: {', '.join(forbidden)}).",
            file=sys.stderr,
        )
        return 1
    unknown = [key for key in patch if key not in MERGEABLE]
    if unknown:
        print(
            f"`alx ledger merge` merges only {', '.join(MERGEABLE)}; "
            f"patch carried: {', '.join(unknown)}.",
            file=sys.stderr,
        )
        return 1
    for key, value in patch.items():
        if isinstance(value, list):
            ledger[key] = value
        elif isinstance(value, dict):
            _deep_merge(ledger.setdefault(key, {}), value)
        else:
            ledger[key] = value
    ws.save_ledger(ledger)
    findings = _ledger_findings(ws, ledger)
    lines = [render_grouped(findings)] if findings else ["Ledger merged; no findings."]
    _emit(ws, state, "ledger merge", ", ".join(patch), lines)
    return 1 if hard_findings(findings) else 0


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


def cmd_snapshot(args):
    ws, state, _ledger = _open(args)
    if args.restore:
        latest = ws.latest_snapshot()
        if latest is None:
            print("No snapshot to restore; run `alx snapshot` first.", file=sys.stderr)
            return 1
        shutil.copyfile(latest, ws.report)
        _emit(
            ws,
            state,
            "snapshot",
            f"restored {latest.name}",
            [f"report.md restored from {latest.name}."],
        )
        return 0
    base = ws.dir / "report.pre-rewild.md"
    if not base.exists():
        target = base
    elif args.iter:
        iteration = len(ws.snapshots())
        target = ws.dir / f"report.pre-rewild.iter{iteration}.md"
    else:
        print(
            f"{base.name} exists (write-once). Use `alx snapshot --iter` for the "
            "next humanization round.",
            file=sys.stderr,
        )
        return 1
    shutil.copyfile(ws.report, target)
    state["humanization"] = "snapshot"
    ws.save_state(state)
    _emit(ws, state, "snapshot", target.name, [f"Snapshot written: {target.name}"])
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def _integrity_findings(ws, state, ledger):
    findings = []
    raw = ws.report.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [
            finding(
                "integrity/encoding",
                f"report.md is not UTF-8: {exc}.",
                fix=remedy("snapshot-restore"),
                remove=remedy("snapshot-restore"),
            )
        ]
    controls = sorted({f"U+{ord(ch):04X}" for ch in _CONTROL_RE.findall(text)})
    if controls:
        findings.append(
            finding(
                "integrity/control-chars",
                f"report.md carries control characters: {', '.join(controls)}.",
                fix=remedy("snapshot-restore"),
                remove=remedy("snapshot-restore"),
            )
        )
    if "�" in text:
        findings.append(
            finding(
                "integrity/replacement-char",
                "report.md carries U+FFFD replacement characters.",
                fix=remedy("snapshot-restore"),
                remove=remedy("snapshot-restore"),
            )
        )
    lang = state.get("lang", "en")
    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        findings.append(
            finding(
                "integrity/structure",
                "report.md needs one H1 title.",
                fix=remedy("check-fix"),
            )
        )
    metadata = _metadata_lines(text)
    expected_date = report_contract.localized_date(
        lang, date.fromisoformat(ledger.get("report_date", date.today().isoformat()))
    )
    if not [line for line in metadata if line and line != expected_date]:
        findings.append(
            finding(
                "integrity/structure",
                "report.md needs a standfirst blockquote under the H1.",
                fix=remedy("set-field", field="standfirst", file="report.md"),
            )
        )
    if expected_date not in metadata:
        findings.append(
            finding(
                "integrity/structure",
                f"the date line must read `{expected_date}` (ledger.report_date "
                f"{ledger.get('report_date')}).",
                fix=remedy("check-fix"),
            )
        )
    minimum, maximum, unit = report_contract.report_length_policy(lang)
    measured = _length(text, lang)
    if measured < minimum:
        findings.append(
            finding(
                "integrity/length",
                f"report body is {measured} {unit}; minimum is {minimum}.",
                fix="extend the report body with evidence-backed sections",
            )
        )
    elif maximum and measured > maximum:
        findings.append(
            finding(
                "integrity/length",
                f"report body is {measured} {unit}; maximum is {maximum}.",
                fix="cut the weakest sections",
            )
        )
    snapshot = ws.latest_snapshot()
    if snapshot is not None:
        lost = [
            span
            for span in quoted_spans(snapshot.read_text(encoding="utf-8"))
            if span not in text
        ]
        if lost:
            findings.append(
                finding(
                    "fidelity/quotation-lost",
                    f"{len(lost)} quoted span(s) of {snapshot.name} are gone from "
                    f"report.md, first: {lost[0][:40]}",
                    fix=remedy("snapshot-restore"),
                    remove=remedy("snapshot-restore"),
                )
            )
    return findings


def _metadata_lines(text):
    lines = []
    found_h1 = False
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not found_h1:
            found_h1 = True
            continue
        if found_h1 and stripped.startswith(">"):
            collecting = True
            lines.append(stripped.lstrip(">").strip())
            continue
        if collecting and stripped:
            break
        if found_h1 and stripped and not collecting:
            break
    return lines


def _length(text, lang):
    sections = validate_report._h2_sections(text)
    prose = validate_report._report_prose(text, sections)
    if lang == "en":
        return len(re.findall(r"\b[\w'-]+\b", prose, re.UNICODE))
    return len(re.findall(r"[A-Za-z0-9㐀-鿿]", prose))


def _ledger_schema():
    """The v4 schema plus the §9 additions until T2 lands them in the file."""
    schema = _read_json(validate_ledger.DEFAULT_SCHEMA)
    source = schema["$defs"]["source"]["properties"]
    source.setdefault("aliases", {"type": "array", "items": {"type": "string"}})
    properties = schema["properties"]
    properties.setdefault(
        "excluded_claims", {"type": "array", "items": {"type": "object"}}
    )
    properties.setdefault("tooling", {"type": "object"})
    # Spec §6.4: excerpts stay empty until `check --fix` binds claims to
    # paragraphs, so the schema's include_in_report -> report_excerpts clause
    # cannot hold between `claim add` and binding; §6.7(c) reports the gap.
    schema["$defs"]["claim"]["allOf"] = [
        clause
        for clause in schema["$defs"]["claim"].get("allOf", [])
        if "report_excerpts" not in json.dumps(clause.get("then", {}))
    ]
    return schema


def _ledger_findings(ws, ledger):
    findings = []
    collect = getattr(validate_ledger, "collect_findings", None)
    if collect is not None:
        findings.extend(collect(ledger, cache_dir=ws.sources))
    else:
        schema = _ledger_schema()
        messages = validate_ledger.validate_schema(
            ledger, schema
        ) + validate_ledger.validate_references(ledger)
        for message in messages:
            text = str(message)
            severity = "warn" if gate_severity.is_warning(text) else "hard"
            findings.append(
                finding(
                    "ledger/rules",
                    text.removeprefix(gate_severity.WARNING_PREFIX),
                    severity=severity,
                    fix=remedy("check-fix"),
                )
            )
    excluded = {
        claim.get("claim_id") for claim in ledger.get("excluded_claims", []) or []
    }
    for claim in ledger.get("claims", []):
        named = sorted(set(claim.get("supports", [])) & excluded)
        if named:
            findings.append(
                finding(
                    "ledger/excluded-support",
                    f"supports names excluded claim(s) {', '.join(named)}; re-point "
                    "or drop this claim.",
                    ids=[claim.get("claim_id", "")],
                    fix=remedy(
                        "set-field", field="supports", file="claims/*.json"
                    ),
                    remove=remedy("claim-drop", claim_id=claim.get("claim_id", "")),
                )
            )
    key_source_ids = set()
    central = set(ledger.get("synthesis", {}).get("central_judgment_claim_ids", []))
    for claim in ledger.get("claims", []):
        if claim.get("importance") == "key" or claim.get("claim_id") in central:
            key_source_ids.update(claim.get("source_ids", []))
    for source in ledger.get("sources", []):
        source_id = source.get("source_id", "")
        cached = read_cache(ws, source_id)
        if cached is None:
            findings.append(
                finding(
                    "fidelity/cache-missing",
                    f"{source_id} has no `sources/{source_id}.txt` + meta pair.",
                    ids=[source_id],
                    fix=remedy("fetch-refresh", source_id=source_id),
                    remove=remedy("fetch-refresh", source_id=source_id),
                )
            )
            continue
        text, meta = cached
        if normalize_url(meta.get("url", "")) != normalize_url(source.get("url", "")):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache url {meta.get('url')} != ledger url "
                    f"{source.get('url')}.",
                    ids=[source_id],
                    fix=remedy("fetch-refresh", source_id=source_id),
                    remove=remedy("fetch-refresh", source_id=source_id),
                )
            )
        elif meta.get("text_sha256") != _sha256_text(text):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache text sha256 does not match its meta record.",
                    ids=[source_id],
                    fix=remedy("fetch-refresh", source_id=source_id),
                    remove=remedy("fetch-refresh", source_id=source_id),
                )
            )
        if source.get("provenance") == "unverified" and source_id in key_source_ids:
            findings.append(
                finding(
                    "ledger/provenance-unverified",
                    f"{source_id} carries a key or central claim while provenance is "
                    "`unverified` (treated as interested).",
                    ids=[source_id],
                    fix=remedy("source-set", source_id=source_id),
                    remove=remedy("claim-drop", claim_id="C<n>"),
                )
            )
    return findings


def paragraph_mapping(ws, state, ledger, text):
    """Return ({claim_id: paragraph}, findings) for every reported claim."""
    paragraphs = body_paragraphs(text)
    urls_by_paragraph = {
        number: {normalize_url(url) for _label, url in markdown_links(block)}
        for number, _start, _end, block in paragraphs
    }
    mapping = {}
    findings = []
    for claim in ledger.get("claims", []):
        if not claim.get("include_in_report", True):
            continue
        claim_id = claim.get("claim_id", "")
        explicit = _claim_paragraph(state, claim)
        if explicit:
            mapping[claim_id] = explicit
            continue
        claim_urls = {
            normalize_url(source.get("url", ""))
            for source in ledger.get("sources", [])
            if source.get("source_id") in claim.get("source_ids", [])
        }
        for source in ledger.get("sources", []):
            if source.get("source_id") in claim.get("source_ids", []):
                claim_urls.update(
                    normalize_url(alias) for alias in source.get("aliases", [])
                )
        candidates = [
            number
            for number, urls in urls_by_paragraph.items()
            if urls & claim_urls
        ]
        if len(candidates) == 1:
            mapping[claim_id] = candidates[0]
        else:
            detail = (
                f"candidates: {', '.join(str(item) for item in candidates)}"
                if candidates
                else "no body paragraph links to its sources"
            )
            findings.append(
                finding(
                    "binding/paragraph",
                    f"ambiguous claim->paragraph binding ({detail}).",
                    ids=[claim_id],
                    fix=remedy("claim-bind", claim_id=claim_id, paragraph=1),
                    remove=remedy("claim-drop", claim_id=claim_id),
                )
            )
    return mapping, findings


def _cited_sources(ledger, text):
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    by_url = {}
    for source in ledger.get("sources", []):
        by_url[normalize_url(source.get("url", ""))] = source
        for alias in source.get("aliases", []):
            by_url[normalize_url(alias)] = source
    ordered = []
    for _label, url in markdown_links(body):
        source = by_url.get(normalize_url(url))
        if source is not None and source not in ordered:
            ordered.append(source)
    return ordered


def _regenerate_sources(ws, ledger):
    text = ws.report_text()
    offset = sources_heading_offset(text)
    if offset is None:
        return False
    heading_end = text.index("\n", offset) if "\n" in text[offset:] else len(text)
    heading = text[offset:heading_end]
    listing = "\n".join(
        f"- [{source.get('title', source.get('url'))}]({source.get('url')})"
        for source in _cited_sources(ledger, text)
    )
    ws.report.write_text(
        text[:offset] + heading + "\n\n" + listing + "\n", encoding="utf-8"
    )
    return True


def _binding_findings(ws, state, ledger, *, fix=False):
    text = ws.report_text()
    findings = []
    known = set()
    for source in ledger.get("sources", []):
        known.add(normalize_url(source.get("url", "")))
        known.update(normalize_url(alias) for alias in source.get("aliases", []))
    for _label, url in markdown_links(text):
        if normalize_url(url) not in known:
            nearest = min(
                known,
                key=lambda candidate: abs(len(candidate) - len(url)),
                default="<no ledger source>",
            )
            findings.append(
                finding(
                    "binding/link-not-in-ledger",
                    f"{url} is not a ledger source url or alias; nearest ledger url "
                    f"is {nearest}.",
                    fix="alx fetch " + url,
                )
            )
    mapping, mapping_findings = paragraph_mapping(ws, state, ledger, text)
    findings.extend(mapping_findings)
    paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
    if fix:
        for claim in ledger.get("claims", []):
            number = mapping.get(claim.get("claim_id"))
            block = paragraphs.get(number)
            if block and not claim.get("report_excerpts"):
                excerpt = re.sub(r"\s+", " ", masked_prose(block))[:EXCERPT_CHARS]
                claim["report_excerpts"] = [excerpt]
        ws.save_ledger(ledger)
        _regenerate_sources(ws, ledger)
        text = ws.report_text()
    excluded_texts = state.get("mechanical_deletions", [])
    for number, _start, _end, block in body_paragraphs(text):
        if _sha256_text(masked_prose(block)) in excluded_texts:
            findings.append(
                finding(
                    "binding/leftover-prose",
                    f"paragraph {number} was dropped with its claim but is still in "
                    "report.md.",
                    fix=remedy("delete-paragraph", paragraph=number),
                )
            )
    offset = sources_heading_offset(text)
    if offset is None:
        findings.append(
            finding(
                "binding/sources-section",
                "report.md needs a final H2 Sources section.",
                fix=remedy("check-fix"),
            )
        )
    else:
        listed = {
            normalize_url(url) for _label, url in markdown_links(text[offset:])
        }
        cited = {
            normalize_url(source.get("url", ""))
            for source in _cited_sources(ledger, text)
        }
        if listed != cited:
            findings.append(
                finding(
                    "binding/sources-section",
                    f"the Sources section lists {len(listed)} url(s); the body cites "
                    f"{len(cited)}.",
                    fix=remedy("check-fix"),
                )
            )
        trailing = validate_report._h2_sections(text)
        if trailing and trailing[-1][1] < offset:
            findings.append(
                finding(
                    "binding/sources-section",
                    "Sources must be the final H2 section.",
                    fix=remedy("check-fix"),
                )
            )
    return findings, mapping


def _fidelity_findings(ws, ledger):
    findings = []
    for claim in ledger.get("claims", []):
        for evidence in claim.get("source_evidence", []):
            findings.extend(probe_findings(ws, claim, evidence))
    return findings


def _rewild_findings(ws, state):
    snapshot = ws.latest_snapshot()
    run_check = getattr(rewild_gate, "run_check", None)
    if snapshot is None or run_check is None:
        return []
    note = ws.reviews / "rewild.json"
    return list(
        run_check(
            ws.report,
            snapshot,
            lang=state.get("lang", "en"),
            review_note_path=note if note.exists() else None,
        )
    )


def _note_completeness(ws, kind):
    """Offline completeness of one review note (spec §6.7f)."""
    path = ws.reviews / f"{kind}.json"
    if not path.exists():
        return [f"reviews/{kind}.json is missing"]
    note = _read_json(path)
    missing = []
    if note.get("status") != "completed":
        missing.append("status=completed")
    if kind == "rewild":
        checks = note.get("fidelity_checks") or {}
        missing.extend(
            f"fidelity_checks.{name}"
            for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
            if checks.get(name) is not True
        )
        for index, item in enumerate(note.get("findings") or [], start=1):
            if item.get("disposition") not in {"resolved", "rejected"}:
                missing.append(f"findings[{index}].disposition")
            if item.get("category") in {"region", "fidelity"} and (
                item.get("disposition") != "resolved"
            ):
                missing.append(f"findings[{index}] unresolved {item.get('category')}")
        return missing
    scores = note.get("scores") or {}
    for name in CONTENT_SCORE_KEYS:
        entry = scores.get(name) or {}
        if not isinstance(entry.get("score"), int):
            missing.append(f"scores.{name}")
        elif entry["score"] < 4:
            missing.append(f"scores.{name}={entry['score']} below 4")
    checks = note.get("checks") or {}
    missing.extend(
        f"checks.{name}" for name in CONTENT_CHECK_KEYS if checks.get(name) is not True
    )
    if not note.get("section_reviews"):
        missing.append("section_reviews")
    if not note.get("completion_note"):
        missing.append("completion_note")
    for index, item in enumerate(note.get("findings") or [], start=1):
        if item.get("severity") == "critical" and item.get("disposition") != "fixed":
            missing.append(f"findings[{index}] critical not fixed")
        excerpt = item.get("report_disclosure_excerpt")
        if excerpt and excerpt not in ws.report_text():
            missing.append(f"findings[{index}].report_disclosure_excerpt not located")
    return missing


def _paragraph_set(text, state):
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    prefix = tuple(VERIFICATION_NOTE_PREFIX.values())
    blocks = []
    for _start, _end, block in _blocks(body):
        prose = masked_prose(block)
        if prose.startswith(prefix):
            continue
        blocks.append(prose)
    return blocks


def _mechanical_ledger(ledger):
    stripped = {
        key: value
        for key, value in ledger.items()
        if key not in {"claims", "sources", "excluded_claims"}
    }
    stripped["claims"] = [
        {
            key: value
            for key, value in claim.items()
            if key not in {"report_excerpts", "verified_at"}
        }
        for claim in ledger.get("claims", [])
    ]
    stripped["sources"] = [
        {
            key: value
            for key, value in source.items()
            if key not in {"accessed", "aliases"}
        }
        for source in ledger.get("sources", [])
    ]
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True)


def freshness_findings(ws, state, ledger, kind):
    """Spec §6.8: current inputs must equal the reviewed copy up to mechanics."""
    record = state.get("reviews", {}).get(kind, {})
    family = f"review/{kind}"
    if not record.get("finished"):
        return [
            finding(
                f"review/{kind}-missing",
                f"the {kind} review is missing.",
                fix=remedy("review-start", kind=kind),
                remove=remedy("review-restore", kind=kind)
                if kind == "content"
                else remedy("review-start", kind=kind),
            )
        ]
    reviewed = ws.review_dir(kind, record["iteration"])
    current = _paragraph_set(ws.report_text(), state)
    previous = _paragraph_set(
        (reviewed / "report.md").read_text(encoding="utf-8"), state
    )
    allowed = set(state.get("mechanical_deletions", []))
    changed = [block for block in current if block not in previous]
    removed = [
        block
        for block in previous
        if block not in current and _sha256_text(block) not in allowed
    ]
    findings = []
    if changed or removed:
        findings.append(
            finding(
                f"{family}-stale",
                f"re-review required: {len(changed)} paragraph(s) added or changed and "
                f"{len(removed)} removed since the {kind} review.",
                fix=remedy("review-iter", kind=kind),
                remove=remedy("review-restore", kind=kind),
            )
        )
    if kind == "content":
        reviewed_ledger = _read_json(reviewed / "ledger.json")
        if _mechanical_ledger(reviewed_ledger) != _mechanical_ledger(ledger):
            findings.append(
                finding(
                    f"{family}-stale",
                    "re-review required: the ledger changed beyond accessed/"
                    "verified_at/report_excerpts since the content review.",
                    fix=remedy("review-iter", kind=kind),
                    remove=remedy("review-restore", kind=kind),
                )
            )
    return findings


def _review_findings(ws, state, ledger):
    findings = []
    for kind in REVIEW_KINDS:
        note_missing = _note_completeness(ws, kind)
        record = state.get("reviews", {}).get(kind, {})
        if record.get("finished") and note_missing:
            findings.append(
                finding(
                    f"review/{kind}-stale",
                    f"the {kind} review note is incomplete: "
                    f"{', '.join(note_missing[:3])}.",
                    fix=remedy("review-iter", kind=kind),
                    remove=remedy("review-restore", kind=kind)
                    if kind == "content"
                    else remedy("review-start", kind=kind),
                )
            )
            continue
        findings.extend(freshness_findings(ws, state, ledger, kind))
    return findings


def mechanical_fixes(ws, ledger):
    """`check --fix`: derivations and refreshes only, never claim text or prose."""
    for source in ledger.get("sources", []):
        cached = read_cache(ws, source.get("source_id", ""))
        if cached is None:
            continue
        meta = cached[1]
        source["accessed"] = (meta.get("fetched_at") or "")[:10] or source.get(
            "accessed"
        )
        domain = _registrable_domain(source.get("url", "")) or ""
        if domain and not source.get("family_justification"):
            source["source_family"] = domain
    meta_by_source = {
        source.get("source_id"): (read_cache(ws, source.get("source_id", "")) or (None, {}))[1]
        for source in ledger.get("sources", [])
    }
    for claim in ledger.get("claims", []):
        derived = []
        for record in claim.get("source_evidence", []):
            source_id = record.get("source_id")
            if source_id and source_id not in derived:
                derived.append(source_id)
        if derived:
            claim["source_ids"] = derived
        stamps = sorted(
            (meta_by_source.get(source_id, {}).get("fetched_at", "")[:10]
             for source_id in claim.get("source_ids", [])),
            reverse=True,
        )
        if stamps and stamps[0]:
            claim["verified_at"] = stamps[0]
    ws.save_ledger(ledger)


def run_check(ws, state, ledger, *, fix=False, mapping_out=None):
    """Sections (a)-(f) of spec §6.7; every evaluator runs offline, every time."""
    if fix:
        mechanical_fixes(ws, ledger)
    findings = []
    findings.extend(_integrity_findings(ws, state, ledger))
    findings.extend(_ledger_findings(ws, ledger))
    binding, mapping = _binding_findings(ws, state, ledger, fix=fix)
    if mapping_out is not None:
        mapping_out.update(mapping)
    findings.extend(binding)
    findings.extend(_fidelity_findings(ws, ledger))
    findings.extend(_rewild_findings(ws, state))
    findings.extend(_review_findings(ws, state, ledger))
    return findings


def _status_line(state, findings, remaining):
    hard = len(hard_findings(findings))
    elapsed, _remaining = _minutes(state)
    next_step = "`alx issue`" if not hard else "fix HARD then `alx check`"
    tail = (
        " At remaining <= 15 min apply every \"Remove:\" remedy and run "
        "`alx issue --deliver`."
    )
    return (
        f"=== STATUS: check #{state['counters']['check']}, elapsed {elapsed} min, "
        f"remaining {max(remaining, 0)} min. Next: {next_step}.{tail} ==="
    )


def cmd_check(args):
    ws, state, ledger = _open(args)
    state["counters"]["check"] = state["counters"].get("check", 0) + 1
    mapping = {}
    findings = run_check(ws, state, ledger, fix=args.fix, mapping_out=mapping)
    ledger = ws.load_ledger()
    _elapsed, remaining = _minutes(state)
    table = ", ".join(
        f"{claim_id}={paragraph}" for claim_id, paragraph in sorted(mapping.items())
    )
    lines = [
        f"claim->paragraph: {table or 'none bound'}",
        render_grouped(findings),
        _status_line(state, findings, remaining),
    ]
    state["last_check"] = {
        "at": _now().isoformat(),
        "hard": len(hard_findings(findings)),
        "class_f": len(class_f_findings(findings)),
        "families": sorted({item.family for item in findings}),
    }
    ws.save_state(state)
    _emit(
        ws,
        state,
        "check",
        f"{len(hard_findings(findings))} hard",
        lines,
    )
    return 1 if hard_findings(findings) else 0


# --------------------------------------------------------------------------
# review lifecycle
# --------------------------------------------------------------------------


def _note_skeleton(ws, state, kind, ledger):
    lang = state.get("lang", "en")
    if kind == "rewild":
        snapshot = ws.latest_snapshot()
        return {
            "schema_version": 1,
            "status": "draft",
            "report_sha256": file_sha256(ws.report),
            "source_sha256": file_sha256(snapshot) if snapshot else "",
            "report_lang": lang,
            "profile": rewild_gate.PROFILES[lang][0],
            "fidelity_checks": {
                name: False for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
            },
            "findings": [],
        }
    return {
        "schema_version": 2,
        "status": "draft",
        "report_path": str(ws.report),
        "report_sha256": file_sha256(ws.report),
        "ledger_path": str(ws.ledger_path),
        "ledger_sha256": file_sha256(ws.ledger_path),
        "report_lang": lang,
        "reviewed_at": date.today().isoformat(),
        "reviewer_mode": "fresh_eyes",
        "scores": {},
        "checks": {},
        "section_reviews": [],
        "visual_assets": [],
        "findings": [],
        "evidence_limitations": [],
        "completion_note": "",
        "claim_support": [
            {"claim_id": claim.get("claim_id"), "disposition": ""}
            for claim in ledger.get("claims", [])
            if claim.get("include_in_report", True)
        ],
    }


def cmd_review_start(args):
    ws, state, ledger = _open(args)
    kind = args.kind
    record = state["reviews"].setdefault(kind, {"iteration": 0, "finished": False})
    iteration = record["iteration"] + 1 if (args.iter or not record["iteration"]) else record["iteration"]
    target = ws.review_dir(kind, iteration)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws.report, target / "report.md")
    if kind == "content":
        shutil.copyfile(ws.ledger_path, target / "ledger.json")
    lines = []
    if args.iter and record["iteration"]:
        previous = ws.review_dir(kind, record["iteration"]) / "report.md"
        diff = [
            block
            for block in _paragraph_set(ws.report_text(), state)
            if block not in _paragraph_set(previous.read_text(encoding="utf-8"), state)
        ]
        lines.append(f"{len(diff)} paragraph(s) changed since iteration {record['iteration']}:")
        lines.extend(f"  - {block[:80]}" for block in diff[:5])
    record.update(
        {
            "iteration": iteration,
            "finished": False,
            "report_sha256": file_sha256(ws.report),
            "ledger_sha256": file_sha256(ws.ledger_path),
        }
    )
    ws.reviews.mkdir(parents=True, exist_ok=True)
    _write_json(ws.reviews / f"{kind}.json", _note_skeleton(ws, state, kind, ledger))
    ws.save_state(state)
    protocol = (
        "references/rewild-gate.md blind-review protocol"
        if kind == "rewild"
        else "references/content-quality.md §13 review protocol"
    )
    lines.extend(
        [
            f"Review copy: {target}",
            f"Fill reviews/{kind}.json per {protocol}, then run "
            f"`alx review finish {kind}`.",
        ]
    )
    _emit(ws, state, f"review start {kind}", f"iteration {iteration}", lines)
    return 0


def cmd_review_finish(args):
    ws, state, _ledger = _open(args)
    kind = args.kind
    record = state["reviews"].get(kind, {})
    if not record.get("iteration"):
        print(f"Run `alx review start {kind}` first.", file=sys.stderr)
        return 1
    missing = _note_completeness(ws, kind)
    note = _read_json(ws.reviews / f"{kind}.json")
    if note.get("report_sha256") != record.get("report_sha256"):
        missing.append("report_sha256 no longer matches the reviewed copy")
    if missing:
        print(
            f"reviews/{kind}.json is incomplete: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    record["finished"] = True
    ws.save_state(state)
    _emit(
        ws,
        state,
        f"review finish {kind}",
        f"iteration {record['iteration']}",
        [f"{kind} review {record['iteration']} finished."],
    )
    return 0


def cmd_review_restore(args):
    ws, state, _ledger = _open(args)
    kind = args.kind
    record = state["reviews"].get(kind, {})
    if not record.get("finished"):
        print(f"No finished {kind} review to restore.", file=sys.stderr)
        return 1
    reviewed = ws.review_dir(kind, record["iteration"])
    shutil.copyfile(reviewed / "report.md", ws.report)
    if kind == "content":
        shutil.copyfile(reviewed / "ledger.json", ws.ledger_path)
    _emit(
        ws,
        state,
        f"review restore {kind}",
        f"iteration {record['iteration']}",
        [f"report.md restored from the {kind} review copy."],
    )
    return 0


# --------------------------------------------------------------------------
# issue
# --------------------------------------------------------------------------


def _verification_note(lang, notes):
    prefix = VERIFICATION_NOTE_PREFIX[lang]
    joiner = "; " if lang == "en" else "；"
    return f"{prefix} {joiner.join(notes)}"


def _insert_verification_note(ws, lang, notes):
    text = ws.report_text()
    prefixes = tuple(VERIFICATION_NOTE_PREFIX.values())
    cleaned = []
    for _start, _end, block in _blocks(text):
        if block.strip().startswith(prefixes):
            cleaned.append(block)
    for block in cleaned:
        text = text.replace(block + "\n\n", "")
    offset = sources_heading_offset(text)
    note = _verification_note(lang, notes)
    if offset is None:
        text = text.rstrip("\n") + "\n\n" + note + "\n"
    else:
        text = text[:offset] + note + "\n\n" + text[offset:]
    ws.report.write_text(text, encoding="utf-8")
    return note


def _auto_remedies(ws, state, ledger, findings, lines):
    """Spec §6.9.1: `--deliver` drops scope, it never waives Class F."""
    restore = [
        item
        for item in class_f_findings(findings)
        if item.family
        in {
            "fidelity/quotation-lost",
            "integrity/control-chars",
            "integrity/replacement-char",
        }
    ]
    if restore and ws.latest_snapshot() is not None:
        shutil.copyfile(ws.latest_snapshot(), ws.report)
        lines.append("auto-remedy: report.md restored from the latest snapshot.")
    claim_ids = []
    for item in class_f_findings(findings):
        for value in item.ids:
            if re.fullmatch(r"C\d+", str(value)) and value not in claim_ids:
                claim_ids.append(value)
    for claim_id in claim_ids:
        if claim_id not in {claim.get("claim_id") for claim in ledger.get("claims", [])}:
            continue
        drop_args = argparse.Namespace(
            dir=ws.dir, claim_id=claim_id, apply=True, reason="Class-F finding at issue."
        )
        cmd_claim_drop(drop_args)
        lines.append(f"auto-remedy: `alx claim drop {claim_id} --apply`.")
    return ws.load_state(), ws.load_ledger()


def _online_phase(ws, state, ledger, args, lines, delivery_notes, disclosures):
    """Step 2: deadline-bound live fidelity, then re-probe refreshed sources."""
    _elapsed, remaining = _minutes(state)
    if remaining < RESERVE_MINUTES:
        delivery_notes.append(
            f"online source fidelity skipped: {remaining} min left, reserve is "
            f"{RESERVE_MINUTES} min"
        )
        return [], True
    receipt_path = ws.receipts / "source-fidelity.json"
    cap = min(ONLINE_CAP_MINUTES, max(remaining - RESERVE_MINUTES, 1))
    kwargs = {"sample_size": args.sample_size, "timeout": min(10, cap * 60)}
    accepted = getattr(
        source_fidelity.issue_source_fidelity_receipt, "__code__", None
    )
    names = accepted.co_varnames if accepted is not None else ()
    if "cache_dir" in names:
        kwargs["cache_dir"] = ws.sources
    if "deadline" in names:
        kwargs["deadline"] = datetime.fromisoformat(state["deadline"])
    if "force" in names:
        kwargs["force"] = True
    try:
        result = source_fidelity.issue_source_fidelity_receipt(
            ws.ledger_path, receipt_path, **kwargs
        )
    except Exception as exc:  # availability failures are Class A
        delivery_notes.append(f"online source fidelity failed: {exc}")
        return [], False
    refreshed = list((result or {}).get("refreshed_source_ids", []))
    findings = []
    if refreshed:
        for claim in ledger.get("claims", []):
            if not set(claim.get("source_ids", [])) & set(refreshed):
                continue
            for evidence in claim.get("source_evidence", []):
                if evidence.get("source_id") in refreshed:
                    findings.extend(probe_findings(ws, claim, evidence))
    disclosure = list((result or {}).get("disclosure_required", []))
    if disclosure:
        disclosures.append(
            "central-judgment evidence not re-read live: " + ", ".join(disclosure)
        )
    lines.append(
        f"source fidelity: {(result or {}).get('status', 'unknown')}, "
        f"{len(refreshed)} source(s) refreshed."
    )
    return findings, True


def _receipt_phase(ws, state, ledger, lines, delivery_notes):
    """Step 4 receipts; the rule tiers were already classified by `check`."""
    snapshot = ws.latest_snapshot()
    receipts = {}
    for kind in REVIEW_KINDS:
        note_path = ws.reviews / f"{kind}.json"
        if not note_path.exists():
            continue
        note = _read_json(note_path)
        note["report_sha256"] = file_sha256(ws.report)
        if kind == "rewild" and snapshot is not None:
            note["source_sha256"] = file_sha256(snapshot)
        if kind == "content":
            note["ledger_sha256"] = file_sha256(ws.ledger_path)
        _write_json(note_path, note)
    rewild_receipt = ws.receipts / "rewild.json"
    errors = rewild_gate.run_gate(
        ws.report,
        snapshot,
        report_lang=state.get("lang", "en"),
        review_note_path=ws.reviews / "rewild.json",
        receipt_path=rewild_receipt,
        force=True,
    )
    if errors:
        delivery_notes.append(f"rewild receipt not issued: {errors[0]}")
    else:
        receipts["rewild"] = rewild_receipt
    content_receipt = ws.receipts / "content.json"
    errors = content_gate.run_content_gate(
        ws.report,
        ws.ledger_path,
        ws.reviews / "content.json",
        content_receipt,
        source_fidelity_receipt_path=ws.receipts / "source-fidelity.json",
        force=True,
    )
    if errors:
        delivery_notes.append(f"content receipt not issued: {errors[0]}")
    else:
        receipts["content"] = content_receipt
    lines.append(f"receipts written: {', '.join(sorted(receipts)) or 'none'}")
    return receipts


def cmd_issue(args):
    ws, state, ledger = _open(args)
    lines = []
    delivery_notes = []
    disclosures = []
    if ws.latest_snapshot() is None:
        shutil.copyfile(ws.report, ws.dir / "report.pre-rewild.md")
        state["humanization"] = "none"
        ws.save_state(state)
        disclosures.append("humanization: none (issue created the snapshot)")
    findings = run_check(ws, state, ledger, fix=False)
    blocking = class_f_findings(findings)
    if blocking and args.deliver:
        state, ledger = _auto_remedies(ws, state, ledger, blocking, lines)
        findings = run_check(ws, state, ledger, fix=False)
        blocking = class_f_findings(findings)
    if blocking:
        lines.append(render_grouped(blocking))
        lines.append("issue refused: Class F findings are never waivable.")
        _emit(ws, state, "issue", f"{len(blocking)} class-F", lines)
        return 1
    online_findings, ok = _online_phase(
        ws, state, ledger, args, lines, delivery_notes, disclosures
    )
    if online_findings:
        if args.deliver:
            state, ledger = _auto_remedies(ws, state, ledger, online_findings, lines)
        else:
            lines.append(render_grouped(online_findings))
            lines.append("issue refused: live fidelity found Class F findings.")
            _emit(ws, state, "issue", "online class-F", lines)
            return 1
    note_items = delivery_notes + disclosures
    if note_items:
        note = _insert_verification_note(ws, state.get("lang", "en"), note_items)
        lines.append(f"verification note: {note[:60]}")
    receipts = _receipt_phase(ws, state, ledger, lines, delivery_notes)
    if delivery_notes and not args.deliver:
        lines.append(render_grouped([_class_a_finding(note) for note in delivery_notes]))
        lines.append(
            "issue aborted before the receipt: rerun with `alx issue --deliver` to "
            "deliver with recorded limitations."
        )
        _emit(ws, state, "issue", "class-A abort", lines)
        return 1
    if delivery_notes:
        _write_json(
            ws.receipts / "delivery-notes.json",
            {"written_at": _now().isoformat(), "notes": delivery_notes},
        )
    receipt = {
        "schema_version": 1,
        "issued_at": _now().isoformat(),
        "report_sha256": file_sha256(ws.report),
        "ledger_sha256": file_sha256(ws.ledger_path),
        "receipts": {
            name: file_sha256(path) for name, path in sorted(receipts.items())
        },
        "notes": {
            kind: file_sha256(ws.reviews / f"{kind}.json")
            for kind in REVIEW_KINDS
            if (ws.reviews / f"{kind}.json").exists()
        },
        "checkers": {
            "alx": "09-14-01",
            "rewild_gate": getattr(rewild_gate, "SCHEMA_VERSION", 1),
        },
        "delivery_notes": delivery_notes,
    }
    if (ws.receipts / "source-fidelity.json").exists():
        receipt["receipts"]["source-fidelity"] = file_sha256(
            ws.receipts / "source-fidelity.json"
        )
    _write_json(ws.receipts / "issue.json", receipt)
    state["counters"]["issue"] = state["counters"].get("issue", 0) + 1
    ws.save_state(state)
    lines.append(f"receipts/issue.json written; next: `{remedy('render')}`.")
    _emit(ws, state, "issue", "issued", lines)
    return 0 if ok or args.deliver else 1


def _class_a_finding(message):
    return finding(
        "tooling/receipt",
        message,
        fix=remedy("issue-deliver"),
    )


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def cmd_render(args):
    ws, state, ledger = _open(args)
    receipt_path = ws.receipts / "issue.json"
    refusal = f"run `{remedy('issue')}` (or `{remedy('issue-deliver')}`)"
    if not receipt_path.exists():
        print(f"receipts/issue.json is missing; {refusal}.", file=sys.stderr)
        return 1
    receipt = _read_json(receipt_path)
    if receipt.get("report_sha256") != file_sha256(ws.report) or receipt.get(
        "ledger_sha256"
    ) != file_sha256(ws.ledger_path):
        print(
            f"receipts/issue.json does not match report.md and ledger.json; {refusal}.",
            file=sys.stderr,
        )
        return 1
    from scripts import md_to_pdf, render_pdf_pages  # heavy import, render only

    subject = f"{ledger.get('subject', '')} {ledger.get('research_question', '')}"
    templates = (
        [args.template]
        if args.template
        else ["executive", md_to_pdf.select_adaptive_companion(subject)]
    )
    lines = []
    for template in templates:
        output = ws.dir / f"report-{template}.pdf"
        kwargs = {
            "template": template,
            "lang": state.get("lang", "en"),
            "ledger": str(ws.ledger_path),
            "force": True,
        }
        for name, path in (
            ("rewild_receipt", ws.receipts / "rewild.json"),
            ("content_receipt", ws.receipts / "content.json"),
            ("source_fidelity_receipt", ws.receipts / "source-fidelity.json"),
        ):
            if path.exists():
                kwargs[name] = str(path)
        code = getattr(md_to_pdf.render_pdf, "__code__", None)
        if code is not None and "issue_receipt" in code.co_varnames:
            kwargs["issue_receipt"] = str(receipt_path)
        md_to_pdf.render_pdf(str(ws.report), str(output), **kwargs)
        pages = ws.dir / f"pages-{template}"
        render_pdf_pages.render_pages(str(output), str(pages))
        lines.append(f"{template}: {output}")
        lines.append(f"{template} contact sheet: {pages}")
    _emit(ws, state, "render", f"{len(templates)} PDFs", lines)
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def cmd_status(args):
    ws, state, ledger = _open(args)
    last = state.get("last_check") or {}
    reviews = state.get("reviews", {})
    lines = [
        f"sources {len(ledger.get('sources', []))}",
        f"claims {len(ledger.get('claims', []))}",
        f"snapshot {'yes' if ws.latest_snapshot() else 'no'}",
        "reviews "
        + ", ".join(
            f"{kind}={'finished' if reviews.get(kind, {}).get('finished') else 'pending'}"
            for kind in REVIEW_KINDS
        ),
        f"receipts {'issued' if (ws.receipts / 'issue.json').exists() else 'none'}",
        f"PDFs {len(list(ws.dir.glob('report-*.pdf')))}",
        "last check "
        + (
            f"#{state['counters'].get('check', 0)} with {last.get('hard', 0)} hard "
            f"({last.get('class_f', 0)} Class F)"
            if last
            else "not run"
        ),
        f"Next: {_next_command(ws, state, ledger)}",
    ]
    _emit(ws, state, "status", "phase checklist", lines)
    return 0


def _next_command(ws, state, ledger):
    if not ledger.get("sources"):
        return "`alx fetch <url>`"
    if not ledger.get("claims"):
        return "`alx claim add claims/batch.json`"
    if not state.get("last_check"):
        return f"`{remedy('check-fix')}`"
    if ws.latest_snapshot() is None:
        return "`alx snapshot`"
    if not all(
        state.get("reviews", {}).get(kind, {}).get("finished") for kind in REVIEW_KINDS
    ):
        return f"`{remedy('review-start', kind='rewild')}`"
    if not (ws.receipts / "issue.json").exists():
        return f"`{remedy('issue')}`"
    return f"`{remedy('render')}`"


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="alx", description="Alexandria research workspace commands"
    )
    parser.add_argument(
        "--dir", default=".", help="report workspace directory (default: .)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create the workspace")
    init.add_argument("directory")
    init.add_argument("--lang", choices=LANGUAGES, required=True)
    init.add_argument("--subject", required=True, help="file holding the subject")
    init.add_argument("--archetype", choices=ARCHETYPES, default="hybrid")
    init.add_argument("--subject-status", choices=LIVING_STATUSES)
    init.add_argument("--reader", help="file holding the intended reader")
    init.add_argument("--budget-minutes", type=int, default=60)
    init.add_argument("--force", action="store_true")
    init.set_defaults(handler=cmd_init)

    fetch = subparsers.add_parser("fetch", help="fetch sources into the cache")
    fetch.add_argument("urls", nargs="*")
    fetch.add_argument("--id", dest="id", help="ledger source id to refresh")
    fetch.add_argument("--refresh", action="store_true")
    fetch.add_argument("--provenance", choices=PROVENANCES)
    fetch.add_argument("--type", choices=EVIDENCE_TYPES)
    fetch.add_argument("--role", action="append", choices=SOURCE_ROLES)
    fetch.add_argument("--accountability", choices=ACCOUNTABILITY_BASES)
    fetch.set_defaults(handler=cmd_fetch)

    source = subparsers.add_parser("source", help="source classification")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_set = source_sub.add_parser("set")
    source_set.add_argument("source_id")
    source_set.add_argument("--provenance", choices=PROVENANCES)
    source_set.add_argument("--type", choices=EVIDENCE_TYPES)
    source_set.add_argument("--role", action="append", choices=SOURCE_ROLES)
    source_set.add_argument("--accountability", choices=ACCOUNTABILITY_BASES)
    source_set.add_argument("--published")
    source_set.add_argument("--undated-reason", dest="undated_reason")
    source_set.set_defaults(handler=cmd_source_set)

    find = subparsers.add_parser("find", help="verbatim windows from the cache")
    find.add_argument("source_id")
    find.add_argument("keyword")
    find.add_argument("--context", type=int, default=160)
    find.add_argument("--max", type=int, default=5)
    find.set_defaults(handler=cmd_find)

    show = subparsers.add_parser("show", help="a cache window")
    show.add_argument("source_id")
    show.add_argument("--start", type=int, default=0)
    show.add_argument("--end", type=int)
    show.set_defaults(handler=cmd_show)

    claim = subparsers.add_parser("claim", help="claim lifecycle")
    claim_sub = claim.add_subparsers(dest="claim_command", required=True)
    claim_add = claim_sub.add_parser("add")
    claim_add.add_argument("files", nargs="+")
    claim_add.set_defaults(handler=cmd_claim_add)
    claim_drop = claim_sub.add_parser("drop")
    claim_drop.add_argument("claim_id")
    claim_drop.add_argument("--apply", action="store_true")
    claim_drop.add_argument("--reason")
    claim_drop.set_defaults(handler=cmd_claim_drop)
    claim_bind = claim_sub.add_parser("bind")
    claim_bind.add_argument("claim_id")
    claim_bind.add_argument("--paragraph", type=int, required=True)
    claim_bind.set_defaults(handler=cmd_claim_bind)

    ledger = subparsers.add_parser("ledger", help="ledger edits")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_merge = ledger_sub.add_parser("merge")
    ledger_merge.add_argument("patch")
    ledger_merge.set_defaults(handler=cmd_ledger_merge)

    snapshot = subparsers.add_parser("snapshot", help="pre-humanization snapshot")
    snapshot.add_argument("--iter", action="store_true")
    snapshot.add_argument("--restore", action="store_true")
    snapshot.set_defaults(handler=cmd_snapshot)

    check = subparsers.add_parser("check", help="every offline evaluator, grouped")
    check.add_argument("--fix", action="store_true")
    check.set_defaults(handler=cmd_check)

    review = subparsers.add_parser("review", help="review lifecycle")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_start = review_sub.add_parser("start")
    review_start.add_argument("kind", choices=REVIEW_KINDS)
    review_start.add_argument("--iter", action="store_true")
    review_start.set_defaults(handler=cmd_review_start)
    review_finish = review_sub.add_parser("finish")
    review_finish.add_argument("kind", choices=REVIEW_KINDS)
    review_finish.set_defaults(handler=cmd_review_finish)
    review_restore = review_sub.add_parser("restore")
    review_restore.add_argument("kind", choices=REVIEW_KINDS)
    review_restore.set_defaults(handler=cmd_review_restore)

    issue = subparsers.add_parser("issue", help="receipts, once, at the end")
    issue.add_argument("--deliver", action="store_true")
    issue.add_argument("--sample-size", type=int, default=8)
    issue.set_defaults(handler=cmd_issue)

    render = subparsers.add_parser("render", help="PDFs from a passed issue")
    render.add_argument("--template")
    render.set_defaults(handler=cmd_render)

    status = subparsers.add_parser("status", help="elapsed, phase, next command")
    status.set_defaults(handler=cmd_status)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
