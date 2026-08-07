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

from tests.source_fidelity_transport import mock_production_transport

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
        "report_date": "2026-07-28",
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

    def test_mixed_public_and_private_dns_answers_are_rejected(self):
        with self.assertRaises(ValueError):
            source_fidelity.validate_public_http_url(
                "https://example.com/",
                resolver=self.mixed_resolver,
            )

    def test_encoded_and_translation_addresses_are_rejected(self):
        unsafe_addresses = (
            "64:ff9b::7f00:1",
            "64:ff9b:1::7f00:1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "2002:7f00:1::",
            "2001::1",
            "::",
            "0.0.0.0",
        )
        for address in unsafe_addresses:
            def resolver(_host, port, _address=address, **_kwargs):
                return [(2, 1, 6, "", (_address, port))]

            with self.subTest(address=address), self.assertRaises(ValueError):
                source_fidelity.validate_public_http_url(
                    "https://example.com/",
                    resolver=resolver,
                )

        target = source_fidelity.validate_public_http_url(
            "https://example.com/",
            resolver=self.public_resolver,
        )
        self.assertEqual(("93.184.216.34",), target.addresses)

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
                ssl.SSLEOFError("transient two"),
                response,
            ],
        ) as request:
            fetched = source_fidelity.default_fetcher(
                "https://example.com/",
                resolver=self.public_resolver,
            )

        self.assertEqual("example domain", source_fidelity.strip_markup(fetched.text))
        self.assertEqual(3, request.call_count)

    def test_benchmark_dns_mapping_cannot_be_enabled_by_environment_variables(self):
        def codex_resolver(_host, _port, **_kwargs):
            return [(2, 1, 6, "", ("198.18.5.201", 443))]

        with mock.patch.dict(
            source_fidelity.os.environ,
            {"CODEX_THREAD_ID": "thread", "CODEX_SHELL": "1"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                source_fidelity.validate_public_http_url(
                    "https://example.com/", resolver=codex_resolver
                )
        with mock.patch.dict(source_fidelity.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                source_fidelity.validate_public_http_url(
                    "https://example.com/", resolver=codex_resolver
                )


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
        self.assertEqual(2, result["counts"]["unverified"])
        self.assertTrue(
            all(
                "Could not verify" in check["detail"]
                for check in result["checks"]
            ),
            result["checks"],
        )
        self.assertTrue(source_fidelity.fidelity_errors(result))
        self.assertEqual(
            [],
            source_fidelity.fidelity_errors(result, allow_unverified=True),
        )

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

            self.assertTrue(
                any(
                    "source document changed" in error.casefold()
                    for error in errors
                ),
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


if __name__ == "__main__":
    unittest.main()
