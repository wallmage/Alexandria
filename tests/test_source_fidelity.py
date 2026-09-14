import importlib.util
import io
import json
import ssl
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tests.source_fidelity_transport import (
    CHANGED_CONTEXT_PAGE,
    fixture_responses,
    mock_production_transport,
)

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "source_fidelity.py"
SPEC = importlib.util.spec_from_file_location("source_fidelity", MODULE_PATH)
source_fidelity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_fidelity)


PRICING_PAGE = """
<html><head><style>.x{color:red}</style></head><body>
<h1>Pricing</h1>
<p>Free: &ldquo;Claude Code: Included&rdquo;, with 50% of weekly limits.</p>
<script>var adoption = "72% of teams";</script>
</body></html>
"""

ADOPTION_PAGE = "<html><body><p>The survey covers developer tooling.</p></body></html>"


def receipt_responses():
    return {
        "example.org": (
            200,
            {"content-type": "text/html"},
            PRICING_PAGE.encode(),
        ),
        "example.net": (
            200,
            {"content-type": "text/html"},
            b"<p>72% of teams reported daily use in 2026.</p>",
        ),
    }


def ledger():
    return {
        "schema_version": 4,
        "report_date": datetime.now(timezone.utc).date().isoformat(),
        "synthesis": {"central_judgment_claim_ids": ["C2"]},
        "sources": [
            {"source_id": "S1", "url": "https://example.org/pricing"},
            {"source_id": "S2", "url": "https://example.net/adoption"},
        ],
        "claims": [
            {
                "claim_id": "C1",
                "importance": "supporting",
                "include_in_report": False,
                "source_ids": ["S1"],
                "extract_or_location": (
                    'Pricing page: "Claude Code: Included", '
                    '"with 50% of weekly limits".'
                ),
                "source_evidence": [
                    {
                        "source_id": "S1",
                        "extract_or_location": (
                            'Pricing page: "Claude Code: Included", '
                            '"with 50% of weekly limits".'
                        ),
                    }
                ],
            },
            {
                "claim_id": "C2",
                "importance": "key",
                "include_in_report": True,
                "source_ids": ["S2"],
                "extract_or_location": (
                    'Adoption table: "72% of teams reported daily use in 2026".'
                ),
                "source_evidence": [
                    {
                        "source_id": "S2",
                        "extract_or_location": (
                            'Adoption table: "72% of teams reported daily use '
                            'in 2026".'
                        ),
                    }
                ],
            },
        ],
    }


def fake_fetcher(pages):
    def fetch(url):
        if url not in pages:
            raise OSError(f"no route to {url}")
        return pages[url]

    return fetch


class ProbeTests(unittest.TestCase):
    def test_malformed_pdf_is_reported_as_unreadable(self):
        with self.assertRaisesRegex(ValueError, "PDF source could not be read"):
            source_fidelity._decode_document(
                b"%PDF-1.7\n",
                "application/pdf",
                None,
            )

    def test_pdf_parser_timeout_interrupts_the_blocked_parser(self):
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("pdf parser", 0.01),
        ):
            with self.assertRaisesRegex(ValueError, "time limit"):
                source_fidelity._decode_document(
                    b"%PDF-1.7\n",
                    "application/pdf",
                    None,
                )

    def test_pdf_over_page_budget_is_rejected_before_text_extraction(self):
        from pypdf import PdfWriter

        payload = io.BytesIO()
        writer = PdfWriter()
        for _ in range(501):
            writer.add_blank_page(width=72, height=72)
        writer.write(payload)

        with self.assertRaisesRegex(ValueError, "page limit"):
            source_fidelity._decode_document(
                payload.getvalue(),
                "application/pdf",
                None,
            )

    def test_pdf_cumulative_text_budget_is_enforced(self):
        pages = [mock.Mock(), mock.Mock()]
        for page in pages:
            page.extract_text.return_value = "x" * 3_000_000
        fake_pypdf = mock.Mock()
        fake_pypdf.PdfReader.return_value = mock.Mock(
            is_encrypted=False,
            pages=pages,
        )

        with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
            with self.assertRaisesRegex(ValueError, "text limit"):
                source_fidelity._extract_pdf_text(b"pdf")

    def test_pdf_inside_resource_budget_still_decodes(self):
        page = mock.Mock()
        page.extract_text.return_value = "verified evidence"
        fake_pypdf = mock.Mock()
        fake_pypdf.PdfReader.return_value = mock.Mock(
            is_encrypted=False,
            pages=[page],
        )

        with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
            self.assertEqual(
                "verified evidence",
                source_fidelity._extract_pdf_text(b"pdf"),
            )

    def test_pdf_worker_applies_memory_and_cpu_limits(self):
        from pypdf import PdfWriter

        payload = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(payload)
        fake_resource = mock.Mock(RLIMIT_AS=1, RLIMIT_CPU=2)
        events = []
        fake_resource.setrlimit.side_effect = (
            lambda _kind, _limits: events.append("limit")
        )
        stdin = mock.Mock(buffer=io.BytesIO(payload.getvalue()))
        stdout = mock.Mock(buffer=io.BytesIO())

        def extract(_payload):
            events.append("extract")
            return "verified evidence"

        with (
            mock.patch.object(source_fidelity, "resource", fake_resource),
            mock.patch.object(source_fidelity.sys, "stdin", stdin),
            mock.patch.object(source_fidelity.sys, "stdout", stdout),
            mock.patch.object(
                source_fidelity,
                "_extract_pdf_text",
                side_effect=extract,
            ),
        ):
            self.assertEqual(0, source_fidelity._run_pdf_worker())

        self.assertEqual(["limit", "limit", "extract"], events)
        fake_resource.setrlimit.assert_has_calls(
            [
                mock.call(
                    fake_resource.RLIMIT_AS,
                    (
                        source_fidelity.PDF_WORKER_MEMORY_LIMIT_BYTES,
                        source_fidelity.PDF_WORKER_MEMORY_LIMIT_BYTES,
                    ),
                ),
                mock.call(
                    fake_resource.RLIMIT_CPU,
                    (
                        source_fidelity.PDF_WORKER_CPU_LIMIT_SECONDS,
                        source_fidelity.PDF_WORKER_CPU_LIMIT_SECONDS,
                    ),
                ),
            ]
        )

    def test_pdf_worker_memory_error_is_reported_as_unreadable(self):
        completed = subprocess.CompletedProcess(
            args=["pdf-worker"],
            returncode=1,
            stdout=b"",
            stderr=b"MemoryError: allocation failed\n",
        )
        with mock.patch.object(
            source_fidelity.subprocess,
            "run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "PDF source could not be read: MemoryError",
            ):
                source_fidelity._decode_pdf_document(b"%PDF-1.7\n")

    def test_hidden_html_subtrees_are_not_reader_visible_evidence(self):
        hidden_documents = (
            "<template>The vendor sold customer records.</template><p>Visible page.</p>",
            "<div hidden>The vendor sold customer records.</div><p>Visible page.</p>",
            (
                '<div aria-hidden="true">The vendor sold customer records.</div>'
                "<p>Visible page.</p>"
            ),
            (
                '<div style="display:none">The vendor sold customer records.</div>'
                "<p>Visible page.</p>"
            ),
            (
                '<div style="visibility: hidden">The vendor sold customer records.</div>'
                "<p>Visible page.</p>"
            ),
        )
        for document in hidden_documents:
            with self.subTest(document=document):
                visible = source_fidelity.strip_markup(document)
                self.assertNotIn("vendor sold", visible)
                self.assertIn("visible page", visible)

    def test_unknown_declared_charset_fails_cleanly(self):
        with self.assertRaisesRegex(ValueError, "unsupported character encoding"):
            source_fidelity._decode_document(
                b"plain text",
                "text/plain",
                "not-a-real-charset",
            )

    def test_quoted_spans_become_the_probes(self):
        probes = source_fidelity.probe_strings(
            'Table IV: "mandatory tool confirmation, no auto-approve flag"; '
            "and a short 'x' quote."
        )
        self.assertEqual(
            [
                "mandatory tool confirmation, no auto-approve flag",
                "and a short 'x' quote.",
            ],
            probes,
        )

    def test_unquoted_extract_still_produces_a_probe(self):
        probes = source_fidelity.probe_strings(
            "Cloud environments page, network access section; short bit"
        )
        self.assertEqual(
            [
                "cloud environments page, network access section",
                "short bit",
            ],
            probes,
        )

    def test_probes_cover_long_tails_and_every_unquoted_segment(self):
        genuine = " ".join(f"genuine-{index}" for index in range(40))
        fabricated = "The company secretly sold customer records to advertisers"
        probes = source_fidelity.probe_strings(
            f'{genuine}; "A genuine quoted observation"; {fabricated}.'
        )

        self.assertTrue(
            any("customer records" in probe for probe in probes),
            probes,
        )
        self.assertTrue(
            any("genuine-20" in probe for probe in probes),
            probes,
        )
        self.assertTrue(
            any("genuine quoted observation" in probe for probe in probes),
            probes,
        )
        self.assertTrue(
            all(len(probe) <= source_fidelity.MAX_PROBE_CHARACTERS for probe in probes)
        )

    def test_empty_extract_produces_no_probe(self):
        self.assertEqual([], source_fidelity.probe_strings(None))
        self.assertEqual([], source_fidelity.probe_strings("   "))
        self.assertEqual([], source_fidelity.probe_strings("... ; , 。"))


class SafeTargetTests(unittest.TestCase):
    @staticmethod
    def public_resolver(_host, _port, **_kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    @staticmethod
    def mixed_resolver(_host, _port, **_kwargs):
        return [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    def test_only_public_http_and_https_targets_are_accepted(self):
        for url in (
            "file:///etc/hosts",
            "data:text/plain,secret",
            "ftp://example.com/file",
            "http://127.0.0.1/",
            "http://[::1]/",
            "http://169.254.169.254/latest/meta-data",
            "https://user:secret@example.com/",
            "https://example.com:8443/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                source_fidelity.validate_public_http_url(
                    url, resolver=self.public_resolver
                )

        target = source_fidelity.validate_public_http_url(
            "https://example.com/research?q=1",
            resolver=self.public_resolver,
        )
        self.assertEqual("example.com", target.host)
        self.assertEqual(("93.184.216.34",), target.addresses)

    def test_resolved_addresses_are_accepted_regardless_of_range(self):
        target = source_fidelity.validate_public_http_url(
            "https://example.com/",
            resolver=self.mixed_resolver,
        )
        self.assertEqual(("93.184.216.34", "127.0.0.1"), target.addresses)

        local_addresses = (
            "198.18.5.201",
            "64:ff9b::7f00:1",
            "64:ff9b:1::7f00:1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "2002:7f00:1::",
            "2001::1",
            "::",
            "0.0.0.0",
        )
        for address in local_addresses:
            def resolver(_host, port, _address=address, **_kwargs):
                return [(2, 1, 6, "", (_address, port))]

            with self.subTest(address=address):
                resolved = source_fidelity.validate_public_http_url(
                    "https://example.com/",
                    resolver=resolver,
                )
                self.assertEqual((address,), resolved.addresses)

    def test_clash_fake_ip_answers_are_accepted(self):
        def clash_resolver(_host, _port, **_kwargs):
            return [(2, 1, 6, "", ("198.18.5.201", 443))]

        target = source_fidelity.validate_public_http_url(
            "https://example.com/",
            resolver=clash_resolver,
        )
        self.assertEqual(("198.18.5.201",), target.addresses)

    def test_plaintext_http_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Plaintext HTTP"):
            source_fidelity.validate_public_http_url(
                "http://example.com/",
                resolver=self.public_resolver,
            )

        target = source_fidelity.validate_public_http_url(
            "https://example.com/",
            resolver=self.public_resolver,
        )
        self.assertEqual("https", target.scheme)

    def test_default_fetcher_rejects_local_files_before_opening(self):
        with self.assertRaises(ValueError):
            source_fidelity.default_fetcher("file:///etc/hosts")

    def test_default_fetcher_retries_transient_tls_disconnects(self):
        response = (
            200,
            {"content-type": "text/html"},
            b"<p>Example Domain</p>",
        )
        with mock.patch.object(
            source_fidelity,
            "_request_pinned",
            side_effect=[
                ssl.SSLEOFError("transient one"),
                response,
            ],
        ) as request:
            fetched = source_fidelity.default_fetcher(
                "https://example.com/",
                resolver=self.public_resolver,
            )

        self.assertEqual("example domain", source_fidelity.strip_markup(fetched.text))
        # Spec §6.11: 1 retry → 2 attempts. Was 3 (DEFAULT_FETCH_ATTEMPTS).
        self.assertEqual(2, request.call_count)

class SamplingTests(unittest.TestCase):
    def test_central_and_key_claims_are_sampled_first(self):
        samples = source_fidelity.select_samples(ledger(), sample_size=1)
        self.assertEqual(["C2"], [sample["claim_id"] for sample in samples])

    def test_sample_size_zero_checks_everything(self):
        samples = source_fidelity.select_samples(ledger(), sample_size=0)
        self.assertEqual({"C1", "C2"}, {sample["claim_id"] for sample in samples})

    def test_each_source_receives_only_its_own_recorded_extract(self):
        value = ledger()
        value["claims"] = [
            {
                "claim_id": "C3",
                "importance": "key",
                "include_in_report": True,
                "source_ids": ["S1", "S2"],
                "extract_or_location": "Two independent sources support the claim.",
                "source_evidence": [
                    {
                        "source_id": "S1",
                        "extract_or_location": '"Alpha evidence belongs to source one."',
                    },
                    {
                        "source_id": "S2",
                        "extract_or_location": '"Beta evidence belongs to source two."',
                    },
                ],
            }
        ]
        samples = source_fidelity.select_samples(value, sample_size=0)
        probes = {
            sample["source_id"]: sample["probes"]
            for sample in samples
        }
        self.assertEqual(
            {
                "S1": ["alpha evidence belongs to source one."],
                "S2": ["beta evidence belongs to source two."],
            },
            probes,
        )


class FidelityTests(unittest.TestCase):
    def test_hidden_source_text_cannot_verify_a_probe(self):
        value = ledger()
        value["sources"] = value["sources"][:1]
        value["claims"] = value["claims"][:1]
        value["claims"][0]["source_evidence"][0]["extract_or_location"] = (
            "The vendor sold customer records."
        )
        result = source_fidelity.check_source_fidelity(
            value,
            fetcher=fake_fetcher(
                {
                    "https://example.org/pricing": (
                        "<template>The vendor sold customer records.</template>"
                        "<p>Visible page.</p>"
                    )
                }
            ),
            online=True,
            sample_size=0,
        )

        self.assertEqual("failed", result["status"], result["checks"])
        self.assertEqual("mismatch", result["checks"][0]["status"])

    def test_receipt_replay_allows_adjacent_utc_and_local_report_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            value = ledger()
            value["report_date"] = "2026-07-29"
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(value), encoding="utf-8")
            receipt_path = work / "receipt.json"

            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                    now=datetime(
                        2026, 7, 28, 23, 6, tzinfo=timezone.utc
                    ),
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [],
                source_fidelity.validate_source_fidelity_receipt(
                    ledger_path, receipt
                ),
            )

    def test_online_run_with_no_candidates_is_incomplete(self):
        value = ledger()
        value["claims"] = []
        result = source_fidelity.check_source_fidelity(
            value,
            online=True,
            sample_size=0,
        )
        self.assertEqual("incomplete", result["status"])
        self.assertTrue(source_fidelity.fidelity_errors(result))

    def test_distinct_evidence_on_two_sources_verifies(self):
        value = ledger()
        value["claims"] = [
            {
                "claim_id": "C3",
                "importance": "key",
                "include_in_report": True,
                "source_ids": ["S1", "S2"],
                "extract_or_location": "Two independent sources support the claim.",
                "source_evidence": [
                    {
                        "source_id": "S1",
                        "extract_or_location": '"Alpha evidence belongs to source one."',
                    },
                    {
                        "source_id": "S2",
                        "extract_or_location": '"Beta evidence belongs to source two."',
                    },
                ],
            }
        ]
        result = source_fidelity.check_source_fidelity(
            value,
            fetcher=fake_fetcher(
                {
                    "https://example.org/pricing": (
                        "<p>Alpha evidence belongs to source one.</p>"
                    ),
                    "https://example.net/adoption": (
                        "<p>Beta evidence belongs to source two.</p>"
                    ),
                }
            ),
            online=True,
            sample_size=0,
        )
        self.assertEqual("passed", result["status"], result["checks"])
        self.assertEqual(2, result["counts"]["verified"])

    def test_matching_extract_verifies(self):
        result = source_fidelity.check_source_fidelity(
            ledger(),
            fetcher=fake_fetcher({"https://example.org/pricing": PRICING_PAGE}),
            online=True,
            sample_size=0,
        )
        verified = [
            check for check in result["checks"] if check["claim_id"] == "C1"
        ]
        self.assertEqual(["verified"], [check["status"] for check in verified])

    def test_extract_absent_from_the_page_is_a_mismatch(self):
        result = source_fidelity.check_source_fidelity(
            ledger(),
            fetcher=fake_fetcher(
                {
                    "https://example.org/pricing": PRICING_PAGE,
                    "https://example.net/adoption": ADOPTION_PAGE,
                }
            ),
            online=True,
            sample_size=0,
        )
        self.assertEqual("failed", result["status"])
        errors = source_fidelity.fidelity_errors(result)
        self.assertTrue(
            any("C2" in error and "does not appear" in error for error in errors),
            errors,
        )

    def test_genuine_quote_cannot_hide_a_fabricated_unquoted_tail(self):
        value = ledger()
        value["sources"] = value["sources"][:1]
        value["claims"] = value["claims"][:1]
        value["claims"][0]["source_evidence"][0]["extract_or_location"] = (
            '"A genuine quoted observation"; '
            "The company secretly sold customer records to advertisers."
        )
        result = source_fidelity.check_source_fidelity(
            value,
            fetcher=fake_fetcher(
                {
                    "https://example.org/pricing": (
                        "<p>A genuine quoted observation</p>"
                    )
                }
            ),
            online=True,
            sample_size=0,
        )

        self.assertEqual("failed", result["status"], result["checks"])
        self.assertTrue(
            any(
                "customer records" in check.get("detail", "")
                for check in result["checks"]
            ),
            result["checks"],
        )

    def test_unreachable_source_is_recorded_not_passed(self):
        result = source_fidelity.check_source_fidelity(
            ledger(),
            fetcher=fake_fetcher({}),
            online=True,
            sample_size=0,
        )
        self.assertEqual("incomplete", result["status"])
        # Status vocab is unreachable|undecodable, not unverified (§7.2.2).
        self.assertEqual(2, result["counts"]["unreachable"])
        self.assertTrue(
            all(
                "Could not verify" in check["detail"]
                for check in result["checks"]
            ),
            result["checks"],
        )
        self.assertTrue(source_fidelity.fidelity_errors(result))
        self.assertNotIn("--allow-unverified", " ".join(source_fidelity.fidelity_errors(result)))

    def test_offline_run_is_a_visible_skip_and_never_a_pass(self):
        result = source_fidelity.check_source_fidelity(ledger(), sample_size=0)
        self.assertEqual("skipped", result["status"])
        self.assertEqual(2, result["counts"]["skipped"])
        self.assertIn("not requested", result["skip_reason"])
        self.assertTrue(
            source_fidelity.fidelity_errors(result, allow_skip=False)
        )

    def test_cli_prints_the_skip_and_writes_the_result(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            out = work / "fidelity.json"
            stderr, stdout = io.StringIO(), io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(stdout):
                code = source_fidelity.main(
                    [str(ledger_path), "--out", str(out), "--sample-size", "0"]
                )
            self.assertEqual(2, code)
            self.assertIn("[SKIP]", stderr.getvalue())
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual("skipped", written["status"])
            self.assertEqual(1, written["schema_version"])

    def test_cli_out_cannot_overwrite_ledger_input(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            original = json.dumps(ledger()).encode()
            ledger_path.write_bytes(original)
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--out",
                        str(ledger_path),
                        "--sample-size",
                        "0",
                    ]
                )

            self.assertEqual(1, code)
            self.assertEqual(original, ledger_path.read_bytes())
            self.assertIn("must be separate from ledger", stderr.getvalue())

    def test_cli_out_refuses_existing_file_without_explicit_force(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            out = work / "result.json"
            out.write_text("keep this", encoding="utf-8")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                code = source_fidelity.main(
                    [str(ledger_path), "--out", str(out), "--sample-size", "0"]
                )

            self.assertEqual(1, code)
            self.assertEqual("keep this", out.read_text(encoding="utf-8"))
            self.assertIn("already exists", stderr.getvalue())

    def test_cli_force_output_replaces_only_unrelated_result_file(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            out = work / "result.json"
            out.write_text("replace this", encoding="utf-8")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--out",
                        str(out),
                        "--force-output",
                        "--sample-size",
                        "0",
                    ]
                )

            self.assertEqual(2, code)
            self.assertEqual(
                "skipped",
                json.loads(out.read_text(encoding="utf-8"))["status"],
            )
            self.assertEqual(0o600, out.stat().st_mode & 0o777)

    def test_cli_force_output_never_waives_input_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            original = json.dumps(ledger()).encode()
            ledger_path.write_bytes(original)
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--out",
                        str(ledger_path),
                        "--force-output",
                        "--sample-size",
                        "0",
                    ]
                )

            self.assertEqual(1, code)
            self.assertEqual(original, ledger_path.read_bytes())
            self.assertIn("must be separate from ledger", stderr.getvalue())

    def test_cli_never_treats_an_offline_pass_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = source_fidelity.main([str(ledger_path)])
            self.assertEqual(2, code)
            self.assertIn("Source fidelity was skipped", stderr.getvalue())

    def test_passing_receipt_is_bound_to_the_exact_ledger_and_probe_set(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "source-receipt.json"
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [],
                source_fidelity.validate_source_fidelity_receipt(
                    ledger_path, receipt
                ),
            )
            for field in ("ledger_schema_path", "verifier_path"):
                with self.subTest(field=field):
                    malformed = {**receipt, field: "\x00"}
                    errors = source_fidelity.validate_source_fidelity_receipt(
                        ledger_path,
                        malformed,
                    )
                    self.assertTrue(
                        any("path" in error and "valid" in error for error in errors),
                        errors,
                    )
            changed = ledger()
            changed["claims"][0]["source_evidence"][0][
                "extract_or_location"
            ] = '"A changed probe that was never fetched."'
            ledger_path.write_text(json.dumps(changed), encoding="utf-8")
            self.assertTrue(
                source_fidelity.validate_source_fidelity_receipt(
                    ledger_path, receipt
                )
            )

    def test_live_revalidation_does_not_trust_passing_receipt_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "source-receipt.json"
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["checks"][0]["observation"]["response_sha256"] = "0" * 64
            with mock_production_transport(
                {
                    "example.org": (
                        200,
                        {"content-type": "text/html"},
                        b"<p>The recorded pricing evidence is absent.</p>",
                    ),
                    "example.net": receipt_responses()["example.net"],
                },
                module=source_fidelity,
            ):
                errors = (
                    source_fidelity.validate_source_fidelity_receipt_online(
                        ledger_path,
                        receipt,
                    )
                )
            self.assertTrue(
                any("live source" in error.casefold() for error in errors),
                errors,
            )

    def test_live_revalidation_rejects_changed_evidentiary_context(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "source-receipt.json"
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            changed_responses = receipt_responses()
            changed_responses["example.org"] = (
                200,
                {"content-type": "text/html"},
                (
                    PRICING_PAGE
                    + "<p>CORRECTION: the prior pricing result is invalid "
                    "and retracted.</p>"
                ).encode(),
            )
            with mock_production_transport(
                changed_responses,
                module=source_fidelity,
            ):
                errors = (
                    source_fidelity.validate_source_fidelity_receipt_online(
                        ledger_path,
                        receipt,
                    )
                )

            self.assertTrue(
                any("context changed" in error.casefold() for error in errors),
                errors,
            )

    def test_live_revalidation_rejects_a_distant_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            value = ledger()
            filler = " stable filler" * 100
            responses = receipt_responses()
            responses["example.org"] = (
                200,
                {"content-type": "text/html"},
                (PRICING_PAGE + f"<p>{filler}</p>").encode(),
            )
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(value), encoding="utf-8")
            receipt_path = work / "source-receipt.json"
            with mock_production_transport(
                responses,
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            responses["example.org"] = (
                200,
                {"content-type": "text/html"},
                (
                    PRICING_PAGE
                    + f"<p>{filler}</p>"
                    + "<h1>CORRECTION</h1><p>The prior pricing result is "
                    "invalid and retracted.</p>"
                ).encode(),
            )
            with mock_production_transport(
                responses,
                module=source_fidelity,
            ):
                errors = (
                    source_fidelity.validate_source_fidelity_receipt_online(
                        ledger_path,
                        receipt,
                    )
                )

            # Whole-document hash equality dropped (§7.2.6). Distant
            # correction outside the probe window is not a context change.
            self.assertFalse(
                any(
                    "source document changed" in error.casefold()
                    for error in errors
                ),
                errors,
            )
            self.assertFalse(
                any("context changed" in error.casefold() for error in errors),
                errors,
            )

    def test_test_transport_cannot_issue_a_production_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            with self.assertRaises(ValueError):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    work / "receipt.json",
                    fetcher=fake_fetcher(
                        {
                            "https://example.org/pricing": PRICING_PAGE,
                            "https://example.net/adoption": (
                                "<p>72% of teams reported daily use in 2026.</p>"
                            ),
                        }
                    ),
                    sample_size=0,
                )


class ResilienceFetchTests(unittest.TestCase):
    @staticmethod
    def public_resolver(_host, _port, **_kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def test_fetch_document_decodes_gbk_from_meta_charset(self):
        with mock_production_transport(
            {"gbk.example.org": fixture_responses()["gbk.example.org"]},
            module=source_fidelity,
        ):
            result = source_fidelity.fetch_document(
                "https://gbk.example.org/page",
                timeout=10,
            )
        self.assertEqual("ok", result.status)
        self.assertIn("简体中文", result.text)
        self.assertEqual("gbk", result.charset.casefold())
        self.assertEqual("GBK标题页", result.title)
        self.assertEqual("2026-03-01", result.published)

    def test_fetch_document_honors_utf8_bom_before_meta(self):
        with mock_production_transport(
            {"bom.example.org": fixture_responses()["bom.example.org"]},
            module=source_fidelity,
        ):
            result = source_fidelity.fetch_document(
                "https://bom.example.org/page",
            )
        self.assertEqual("ok", result.status)
        self.assertIn("BOM encoded visible text", result.text)
        self.assertEqual("BOM Title", result.title)
        self.assertEqual("2026-04-02", result.published)

    def test_cross_domain_redirect_is_unreachable_with_final_url(self):
        responses = {
            "example.org": (
                302,
                {"location": "https://evil.example.net/final"},
                b"",
            ),
            "evil.example.net": (
                200,
                {"content-type": "text/html"},
                b"<p>other registrable domain</p>",
            ),
        }
        with mock_production_transport(responses, module=source_fidelity):
            result = source_fidelity.fetch_document("https://example.org/start")
        self.assertEqual("unreachable", result.status)
        self.assertEqual("cross-domain-redirect", result.reason_class)
        self.assertIn("evil.example.net", result.reason)

    def test_http_403_is_unreachable_http_status(self):
        with mock_production_transport(
            {"blocked.example.org": fixture_responses()["blocked.example.org"]},
            module=source_fidelity,
        ):
            result = source_fidelity.fetch_document(
                "https://blocked.example.org/secret",
            )
        self.assertEqual("unreachable", result.status)
        self.assertEqual("http-403", result.reason_class)
        self.assertEqual(403, result.http_status)

    def test_timeout_is_unreachable_and_retries_once(self):
        calls = []

        def boom(target, *, timeout):
            del target
            calls.append(timeout)
            raise TimeoutError("slow")

        with (
            mock.patch.object(
                source_fidelity.socket, "getaddrinfo",
                side_effect=self.public_resolver,
            ),
            mock.patch.object(
                source_fidelity, "_request_pinned", side_effect=boom,
            ),
        ):
            result = source_fidelity.fetch_document(
                "https://slow.example.org/page",
                timeout=10,
            )
        self.assertEqual("unreachable", result.status)
        self.assertEqual("timeout", result.reason_class)
        self.assertEqual(2, len(calls))

    def test_deadline_expires_before_fetch(self):
        result = source_fidelity.fetch_document(
            "https://example.org/page",
            deadline=0,
        )
        self.assertEqual("unreachable", result.status)
        self.assertEqual("timeout", result.reason_class)

    def test_plaintext_http_reason_class_exists(self):
        result = source_fidelity.fetch_document("http://example.org/page")
        self.assertEqual("unreachable", result.status)
        self.assertEqual("plaintext-http", result.reason_class)

    def test_fffd_ratio_over_one_percent_is_undecodable(self):
        garbage = (
            "<html><body>" + ("\ufffd" * 20) + "ok</body></html>"
        ).encode("utf-8")
        with mock_production_transport(
            {
                "bad.example.org": (
                    200,
                    {"content-type": "text/plain; charset=utf-8"},
                    garbage,
                )
            },
            module=source_fidelity,
        ):
            result = source_fidelity.fetch_document(
                "https://bad.example.org/x",
            )
        self.assertEqual("undecodable", result.status)

    def test_browser_like_user_agent(self):
        self.assertIn("Mozilla/5.0", source_fidelity.USER_AGENT)


class ProbeResilienceTests(unittest.TestCase):
    def test_ellipsis_splits_inside_quoted_spans(self):
        probes = source_fidelity.probe_strings(
            '"Alpha evidence belongs to source one. … Beta clause after ellipsis."'
        )
        joined = " ".join(probes)
        self.assertIn("alpha evidence belongs to source one.", joined)
        self.assertIn("beta clause after ellipsis.", joined)
        self.assertFalse(any("…" in probe or "..." in probe for probe in probes))

    def test_quote_glyph_families_fold_on_both_sides(self):
        probes = source_fidelity.probe_strings(
            '「Alpha evidence belongs to source one。」'
        )
        text = source_fidelity.strip_markup(
            "<p>“Alpha evidence belongs to source one.”</p>"
        )
        self.assertTrue(any(probe in text for probe in probes), (probes, text))

    def test_short_segment_is_hard_finding_not_skipped(self):
        findings = source_fidelity.probe_findings(
            {"claim_id": "C9"},
            {"source_id": "S1"},
            "enough surrounding document text for a match",
        )
        # empty extract: no findings
        self.assertEqual([], findings)
        findings = source_fidelity.probe_findings(
            {
                "claim_id": "C9",
                "source_evidence": [
                    {"source_id": "S1", "extract_or_location": "short"}
                ],
            },
            {"source_id": "S1"},
            "short is present in the cached page text here",
        )
        families = [item.family for item in findings]
        self.assertIn("fidelity/short-segment", families)
        finding = next(
            item for item in findings if item.family == "fidelity/short-segment"
        )
        self.assertEqual("hard", finding.severity)
        self.assertEqual("extend the quote in claims/<file>", finding.fix)

    def test_cjk_ascii_punct_folded_for_probe(self):
        probes = source_fidelity.probe_strings("他说，今天很好。")
        text = source_fidelity.normalize_text("他说,今天很好.")
        self.assertTrue(any(probe in text for probe in probes), probes)


class CacheAndPolicyTests(unittest.TestCase):
    def test_cache_round_trip_and_offline_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            result = source_fidelity.FetchResult(
                status="ok",
                reason_class="",
                reason="",
                text="<p>Alpha evidence belongs to source one.</p>",
                charset="utf-8",
                url="https://example.org/a",
                final_url="https://example.org/a",
                aliases=["https://example.org/a"],
                http_status=200,
                title="Alpha",
                published=None,
                text_sha256="",
            )
            source_fidelity.write_cache(cache, "S1", result)
            txt, meta = source_fidelity.cache_paths(cache, "S1")
            self.assertTrue(txt.is_file())
            self.assertTrue(meta.is_file())
            text, stored = source_fidelity.read_cache(cache, "S1")
            self.assertIn("alpha evidence belongs to source one.", text)
            for key in (
                "url",
                "final_url",
                "aliases",
                "http_status",
                "charset",
                "title",
                "published",
                "fetched_at",
                "text_sha256",
                "transport",
            ):
                self.assertIn(key, stored)
            value = ledger()
            value["claims"] = value["claims"][:1]
            value["sources"] = value["sources"][:1]
            value["claims"][0]["source_evidence"][0]["extract_or_location"] = (
                '"Alpha evidence belongs to source one."'
            )
            checked = source_fidelity.check_source_fidelity(
                value,
                cache_dir=cache,
                online=False,
                sample_size=0,
            )
            self.assertEqual("verified", checked["checks"][0]["status"])

    def test_online_refreshes_cache_and_lists_source_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            value = ledger()
            value["claims"] = value["claims"][:1]
            value["sources"] = value["sources"][:1]
            value["claims"][0]["source_evidence"][0]["extract_or_location"] = (
                '"Alpha evidence belongs to source one."'
            )
            checked = source_fidelity.check_source_fidelity(
                value,
                fetcher=fake_fetcher(
                    {
                        "https://example.org/pricing": (
                            "<p>Alpha evidence belongs to source one.</p>"
                        )
                    }
                ),
                cache_dir=cache,
                online=True,
                sample_size=0,
            )
            self.assertIn("S1", checked.get("refreshed_source_ids", []))
            self.assertIsNotNone(source_fidelity.read_cache(cache, "S1"))

    def test_policy_v2_substitutes_and_sets_disclosure(self):
        value = ledger()
        value["synthesis"] = {"central_judgment_claim_ids": ["C2"]}
        value["sources"].append(
            {"source_id": "S9", "url": "https://example.org/other"}
        )
        value["claims"][1]["source_ids"] = ["S2", "S9"]
        value["claims"][1]["source_evidence"] = [
            {
                "source_id": "S2",
                "extract_or_location": (
                    '"72% of teams reported daily use in 2026"'
                ),
            },
            {
                "source_id": "S9",
                "extract_or_location": '"Claude Code: Included"',
            },
        ]
        def fetch(url):
            if url == "https://example.net/adoption":
                raise OSError("down")
            return PRICING_PAGE

        result = source_fidelity.check_source_fidelity(
            value,
            fetcher=fetch,
            online=True,
            sample_size=1,
        )
        self.assertEqual(["S9"], [check["source_id"] for check in result["checks"]])
        self.assertEqual(["verified"], [check["status"] for check in result["checks"]])
        self.assertEqual([], result["disclosure_required"])

        value["claims"][1]["source_ids"] = ["S2"]
        value["claims"][1]["source_evidence"] = value["claims"][1]["source_evidence"][:1]
        failed = source_fidelity.check_source_fidelity(
            value,
            fetcher=fetch,
            online=True,
            sample_size=1,
        )
        self.assertEqual(["unreachable"], [check["status"] for check in failed["checks"]])
        self.assertEqual(["C2"], failed["disclosure_required"])

    def test_v1_receipt_still_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "source-receipt.json"
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                    policy="weighted-source-evidence-v1",
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["policy"]["name"] = "weighted-source-evidence-v1"
            self.assertEqual(
                [],
                source_fidelity.validate_source_fidelity_receipt(
                    ledger_path, receipt
                ),
            )

    def test_context_change_is_hard_finding_quoting_window(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            first = source_fidelity.FetchResult(
                status="ok",
                reason_class="",
                reason="",
                text=PRICING_PAGE,
                charset="utf-8",
                url="https://context.example.org/p",
                final_url="https://context.example.org/p",
                aliases=[],
                http_status=200,
                title="Pricing",
                published=None,
                text_sha256="",
            )
            source_fidelity.write_cache(cache, "S1", first)
            claim = ledger()["claims"][0]
            probes = source_fidelity.probe_strings(
                claim["source_evidence"][0]["extract_or_location"]
            )
            source_fidelity.record_probe_contexts(cache, "S1", "C1", probes)
            changed = source_fidelity.FetchResult(
                status="ok",
                reason_class="",
                reason="",
                text=CHANGED_CONTEXT_PAGE.decode("utf-8"),
                charset="utf-8",
                url="https://context.example.org/p",
                final_url="https://context.example.org/p",
                aliases=[],
                http_status=200,
                title="Pricing",
                published=None,
                text_sha256="",
            )
            source_fidelity.write_cache(cache, "S1", changed)
            text, meta = source_fidelity.read_cache(cache, "S1")
            self.assertIn("C1", meta.get("probe_contexts") or {})
            findings = source_fidelity.probe_findings(
                claim,
                {"source_id": "S1", "url": "https://context.example.org/p"},
                text,
                cache_meta=meta,
            )
            families = [item.family for item in findings]
            self.assertIn("fidelity/context-changed", families)
            message = next(
                item.message
                for item in findings
                if item.family == "fidelity/context-changed"
            )
            self.assertIn("re-read", message.casefold())
            self.assertTrue(
                any(marker in message for marker in ("更正", "correction", "retract")),
                message,
            )


class CliResilienceTests(unittest.TestCase):
    def test_cli_sections_and_no_allow_unverified_help(self):
        help_text = source_fidelity.build_parser().format_help()
        self.assertNotIn("--allow-unverified", help_text)
        self.assertIn("--force", help_text)
        self.assertIn("--explain", help_text)
        self.assertIn("--cache-dir", help_text)
        self.assertIn("--online", help_text)

    def test_explain_prints_probes_without_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            stderr, stdout = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(source_fidelity, "default_fetcher") as fetch,
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            ):
                code = source_fidelity.main(
                    [str(ledger_path), "--explain", "C1"]
                )
            self.assertEqual(0, code)
            fetch.assert_not_called()
            self.assertIn("claude code: included", stdout.getvalue().casefold())

    def test_force_overwrites_receipt_after_printing_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "receipt.json"
            receipt_path.write_text("{}", encoding="utf-8")
            stderr = io.StringIO()
            with (
                mock_production_transport(
                    {
                        "example.org": (
                            200,
                            {"content-type": "text/html"},
                            b"<p>nope</p>",
                        ),
                        "example.net": (
                            200,
                            {"content-type": "text/html"},
                            b"<p>nope</p>",
                        ),
                    },
                    module=source_fidelity,
                ),
                redirect_stderr(stderr),
            ):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--online",
                        "--receipt",
                        str(receipt_path),
                        "--force",
                        "--sample-size",
                        "0",
                    ]
                )
            self.assertNotEqual(0, code)
            self.assertIn("mismatch", stderr.getvalue().casefold())
            self.assertIn("===", stderr.getvalue())

    def test_hard_findings_block_and_out_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            source_fidelity.write_cache(
                cache,
                "S1",
                source_fidelity.FetchResult(
                    status="ok",
                    reason_class="",
                    reason="",
                    text=PRICING_PAGE,
                    charset="utf-8",
                    url="https://example.org/pricing",
                    final_url="https://example.org/pricing",
                    aliases=[],
                    http_status=200,
                    title="Pricing",
                    published=None,
                    text_sha256="",
                ),
            )
            value = ledger()
            value["claims"] = value["claims"][:1]
            value["sources"] = value["sources"][:1]
            probes = source_fidelity.probe_strings(
                value["claims"][0]["source_evidence"][0]["extract_or_location"]
            )
            source_fidelity.record_probe_contexts(cache, "S1", "C1", probes)
            source_fidelity.write_cache(
                cache,
                "S1",
                source_fidelity.FetchResult(
                    status="ok",
                    reason_class="",
                    reason="",
                    text=CHANGED_CONTEXT_PAGE.decode("utf-8"),
                    charset="utf-8",
                    url="https://example.org/pricing",
                    final_url="https://example.org/pricing",
                    aliases=[],
                    http_status=200,
                    title="Pricing",
                    published=None,
                    text_sha256="",
                ),
            )
            checked = source_fidelity.check_source_fidelity(
                value,
                cache_dir=cache,
                online=False,
                sample_size=0,
            )
            errors = source_fidelity.fidelity_errors(
                checked, policy=source_fidelity.POLICY_V2
            )
            self.assertTrue(
                any("context" in error.casefold() for error in errors),
                errors,
            )
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(value), encoding="utf-8")
            out = Path(directory) / "out.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--cache-dir",
                        str(cache),
                        "--out",
                        str(out),
                        "--sample-size",
                        "0",
                    ]
                )
            self.assertNotEqual(0, code)
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(written["findings"])
            self.assertIsInstance(written["findings"][0], dict)

    def test_v2_fidelity_errors_tolerate_unverified_quorum(self):
        value = ledger()
        extra = []
        for index in range(3, 5):
            sid = f"S{index}"
            cid = f"C{index}"
            value["sources"].append(
                {"source_id": sid, "url": f"https://example.org/p{index}"}
            )
            extra.append(
                {
                    "claim_id": cid,
                    "importance": "supporting",
                    "include_in_report": True,
                    "source_ids": [sid],
                    "source_evidence": [
                        {
                            "source_id": sid,
                            "extract_or_location": '"Claude Code: Included"',
                        }
                    ],
                }
            )
        value["claims"].extend(extra)
        pages = {
            "https://example.org/pricing": PRICING_PAGE,
            "https://example.org/p3": PRICING_PAGE,
            "https://example.org/p4": PRICING_PAGE,
        }

        def fetch(url):
            if url == "https://example.net/adoption":
                raise OSError("down")
            return pages[url]

        result = source_fidelity.check_source_fidelity(
            value,
            fetcher=fetch,
            online=True,
            sample_size=0,
        )
        self.assertEqual(1, result["counts"]["unreachable"])
        self.assertTrue(
            source_fidelity.fidelity_errors(result),
        )
        self.assertEqual(
            [],
            source_fidelity.fidelity_errors(
                result, policy=source_fidelity.POLICY_V2
            ),
        )

    def test_v2_receipt_issues_after_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            value = ledger()
            value["sources"].append(
                {"source_id": "S9", "url": "https://example.org/other"}
            )
            value["claims"][1]["source_ids"] = ["S2", "S9"]
            value["claims"][1]["source_evidence"] = [
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        '"72% of teams reported daily use in 2026"'
                    ),
                },
                {
                    "source_id": "S9",
                    "extract_or_location": '"Claude Code: Included"',
                },
            ]
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(value), encoding="utf-8")
            receipt_path = work / "receipt.json"
            responses = receipt_responses()
            responses["example.net"] = (
                403,
                {"content-type": "text/html"},
                b"no",
            )
            with mock_production_transport(responses, module=source_fidelity):
                result = source_fidelity.issue_source_fidelity_receipt(
                    ledger_path,
                    receipt_path,
                    sample_size=0,
                )
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "weighted-source-evidence-v2",
                receipt["policy"]["name"],
            )
            pairs = {
                (check["claim_id"], check["source_id"])
                for check in receipt["checks"]
            }
            self.assertIn(("C2", "S9"), pairs)
            self.assertEqual(
                [],
                source_fidelity.validate_source_fidelity_receipt(
                    ledger_path, receipt
                ),
            )
            self.assertIn("S1", result.get("refreshed_source_ids", []) + [
                check["source_id"] for check in result["checks"]
            ])

    def test_receipt_online_is_one_live_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = Path(directory) / "receipt.json"
            calls = []
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                inner = source_fidelity._request_pinned

                def counted(target, *, timeout):
                    calls.append(target.host)
                    return inner(target, timeout=timeout)

                with mock.patch.object(
                    source_fidelity,
                    "_request_pinned",
                    side_effect=counted,
                ):
                    code = source_fidelity.main(
                        [
                            str(ledger_path),
                            "--online",
                            "--receipt",
                            str(receipt_path),
                            "--sample-size",
                            "0",
                        ]
                    )
            self.assertEqual(0, code)
            self.assertEqual(2, len(calls), calls)

    def test_stale_receipt_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            ledger_path = work / "ledger.json"
            ledger_path.write_text(json.dumps(ledger()), encoding="utf-8")
            receipt_path = work / "receipt.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "ledger_sha256": "0" * 64,
                        "status": "passed",
                    }
                ),
                encoding="utf-8",
            )
            with mock_production_transport(
                receipt_responses(),
                module=source_fidelity,
            ):
                code = source_fidelity.main(
                    [
                        str(ledger_path),
                        "--online",
                        "--receipt",
                        str(receipt_path),
                        "--sample-size",
                        "0",
                    ]
                )
            self.assertEqual(0, code)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                source_fidelity.file_sha256(ledger_path),
                receipt["ledger_sha256"],
            )


if __name__ == "__main__":
    unittest.main()


class ProbeContextReconfirmationTests(unittest.TestCase):
    EXTRACT = "The tariff rose to 12 percent in 2026."

    def _result(self, text):
        return source_fidelity.FetchResult(
            status="ok",
            reason_class="",
            reason="",
            text=text,
            charset="utf-8",
            url="https://example.org/p",
            final_url="https://example.org/p",
            aliases=[],
            http_status=200,
            title="Tariffs",
            published=None,
            text_sha256="",
        )

    def _claim(self):
        return {
            "claim_id": "C1",
            "source_ids": ["S1"],
            "source_evidence": [
                {"source_id": "S1", "extract_or_location": self.EXTRACT}
            ],
        }

    def _families(self, cache):
        text, meta = source_fidelity.read_cache(cache, "S1")
        return [
            item.family
            for item in source_fidelity.probe_findings(
                self._claim(),
                {"source_id": "S1", "url": "https://example.org/p"},
                text,
                cache_meta=meta,
            )
        ]

    def _refreshed_cache(self, directory):
        cache = Path(directory)
        source_fidelity.write_cache(
            cache,
            "S1",
            self._result(f"Background as researched. {self.EXTRACT} Closing line."),
        )
        source_fidelity.record_probe_contexts(
            cache, "S1", "C1", source_fidelity.probe_strings(self.EXTRACT)
        )
        source_fidelity.write_cache(
            cache,
            "S1",
            self._result(f"A rewritten opening. {self.EXTRACT} A rewritten close."),
        )
        return cache

    def test_refresh_alone_keeps_the_context_change(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = self._refreshed_cache(directory)
            self.assertIn("fidelity/context-changed", self._families(cache))

    def test_recording_after_refresh_clears_the_context_change(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = self._refreshed_cache(directory)
            source_fidelity.record_probe_contexts(
                cache, "S1", "C1", source_fidelity.probe_strings(self.EXTRACT)
            )
            self.assertEqual([], self._families(cache))
