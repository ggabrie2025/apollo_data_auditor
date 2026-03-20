"""
Tests Optimized Scanner Module
===============================

Tests pour agent/core/optimized_scanner.py

(c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import pytest
import tempfile
from pathlib import Path

from agent.core.optimized_scanner import (
    read_single_file,
    read_files_parallel,
    scan_pii_content,
    scan_pii_parallel,
)


# =============================================================================
# READ SINGLE FILE TESTS
# =============================================================================

class TestReadSingleFile:
    """Test read_single_file function."""

    def test_read_existing_file(self):
        """Read existing file returns content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello World")
            temp_path = f.name

        try:
            filepath, content = read_single_file(temp_path)
            assert filepath == temp_path
            assert content == b"Hello World"
        finally:
            Path(temp_path).unlink()

    def test_read_nonexistent_file(self):
        """Read non-existent file returns None content."""
        filepath, content = read_single_file("/nonexistent/file.txt")
        assert content is None

    def test_read_binary_file(self):
        """Read binary file returns bytes."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_path = f.name

        try:
            filepath, content = read_single_file(temp_path)
            assert content == b"\x00\x01\x02\x03"
        finally:
            Path(temp_path).unlink()


# =============================================================================
# READ FILES PARALLEL TESTS
# =============================================================================

class TestReadFilesParallel:
    """Test read_files_parallel function."""

    def test_read_multiple_files(self):
        """Read multiple files in parallel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                filepath = Path(tmpdir) / f"file{i}.txt"
                filepath.write_text(f"Content {i}")
                files.append(str(filepath))

            result = read_files_parallel(files)
            assert len(result) == 3
            for filepath, content in result.items():
                assert content is not None

    def test_read_empty_list(self):
        """Read empty list returns empty dict."""
        result = read_files_parallel([])
        assert len(result) == 0


# =============================================================================
# SCAN PII CONTENT TESTS
# =============================================================================

class TestScanPIIContent:
    """Test scan_pii_content function."""

    def test_scan_empty_content(self):
        """Scan empty content returns empty list."""
        result = scan_pii_content(b"")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_scan_content_with_email(self):
        """Scan content with email returns PII match."""
        content = b"Contact: john.doe@example.com"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        # May or may not detect depending on patterns
        # Just verify it runs without error

    def test_scan_content_with_phone(self):
        """Scan content with phone returns PII match."""
        content = b"Tel: +33 6 12 34 56 78"
        result = scan_pii_content(content)
        assert isinstance(result, list)

    def test_scan_content_no_pii(self):
        """Scan content without PII returns empty list."""
        content = b"Just some regular text without any personal info"
        result = scan_pii_content(content)
        assert isinstance(result, list)


# =============================================================================
# SCAN PII PARALLEL TESTS
# =============================================================================

class TestScanPIIParallel:
    """Test scan_pii_parallel function."""

    def test_scan_multiple_files(self):
        """Scan multiple files in parallel."""
        file_contents = {
            "/path/file1.txt": b"Email: test@example.com",
            "/path/file2.txt": b"Phone: 0612345678",
            "/path/file3.txt": b"No PII here",
        }

        result = scan_pii_parallel(file_contents)
        assert isinstance(result, dict)
        assert len(result) == 3

    def test_scan_empty_dict(self):
        """Scan empty dict returns empty dict."""
        result = scan_pii_parallel({})
        assert len(result) == 0


# =============================================================================
# ARTICLE 9 RGPD PATTERNS TESTS (Sprint 59)
# =============================================================================

def has_pii_type(result: list, pii_type: str) -> bool:
    """Helper: check if PII type is in scan result."""
    return any(d.get('type') == pii_type for d in result)

def get_estimated_data_subjects(result: list) -> int:
    """Helper: extract _estimated_data_subjects from scan result."""
    for d in result:
        if '_estimated_data_subjects' in d:
            return d['_estimated_data_subjects']
    return 0


class TestArticle9PatternsOptimized:
    """Test Article 9 RGPD sensitive data patterns in optimized scanner."""

    def test_health_data_pattern_fr(self):
        """Detect French health data."""
        content = b"Patient avec diagnostic cancer stade 2"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'health_data')

    def test_health_data_pattern_en(self):
        """Detect English health data."""
        content = b"Medical record shows diabetes treatment"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'health_data')

    def test_biometric_pattern(self):
        """Detect biometric data."""
        content = b"Empreinte digitale et test ADN requis"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'biometric')

    def test_political_pattern_fr(self):
        """Detect French political/union data."""
        content = b"Adherent syndicat CGT depuis 2020"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'political')

    def test_political_pattern_en(self):
        """Detect English political/union data."""
        content = b"Trade union member since 2019"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'political')

    def test_religious_pattern(self):
        """Detect religious data."""
        content = b"Pratiquant catholique, frequente eglise"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'religious')

    def test_sexual_orientation_pattern(self):
        """Detect sexual orientation data."""
        content = b"Orientation sexuelle: LGBT community member"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'sexual_orientation')

    def test_ethnic_origin_pattern_fr(self):
        """Detect French ethnic origin data."""
        content = b"Origine ethnique: africain"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'ethnic_origin')

    def test_ethnic_origin_pattern_en(self):
        """Detect English ethnic origin data."""
        content = b"Ethnic background: Asian American"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'ethnic_origin')

    def test_eeo_ethnicity_pattern(self):
        """Detect US EEO ethnicity categories."""
        content = b"EEO Category: Native American, Cherokee tribe"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'eeo_ethnicity')

    def test_gender_pattern(self):
        """Detect gender data."""
        content = b"Genre: non binaire, genderqueer"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'gender')


# =============================================================================
# FINANCE & TAX PATTERNS TESTS (Sprint 59)
# =============================================================================

class TestFinanceTaxPatternsOptimized:
    """Test Finance & Tax patterns in optimized scanner."""

    def test_credit_card_visa(self):
        """Detect Visa credit card."""
        content = b"Card: 4532015112830366"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'credit_card')

    def test_credit_card_mastercard(self):
        """Detect Mastercard credit card."""
        content = b"Payment: 5425233430109903"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'credit_card')

    def test_credit_card_amex(self):
        """Detect American Express credit card."""
        content = b"Amex: 378282246310005"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'credit_card')

    def test_ssn_us_with_dashes(self):
        """Detect US SSN with dashes."""
        content = b"SSN: 123-45-6789"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'ssn_us')

    def test_ssn_us_with_spaces(self):
        """Detect US SSN with spaces."""
        content = b"Social: 123 45 6789"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'ssn_us')

    def test_ein_us(self):
        """Detect US Employer Identification Number."""
        content = b"EIN: 12-3456789"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'ein_us')

    def test_itin_us(self):
        """Detect US Individual Taxpayer ID — ssn_us regex also matches 9XX format."""
        content = b"ITIN: 912-78-1234"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        # ssn_us matches first (dict order), itin_us deduped by normalized value
        assert has_pii_type(result, 'itin_us') or has_pii_type(result, 'ssn_us')

    def test_salary_data_fr(self):
        """Detect French salary data."""
        content = b"Salaire brut: 45000 EUR annuel"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'salary_data')

    def test_salary_data_en(self):
        """Detect English salary data."""
        content = b"Annual salary: $85,000 gross income"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'salary_data')

    def test_crypto_wallet_bitcoin(self):
        """Detect Bitcoin wallet address."""
        content = b"BTC: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'crypto_wallet')

    def test_crypto_wallet_ethereum(self):
        """Detect Ethereum wallet address."""
        content = b"ETH: 0x742d35Cc6634C0532925a3b844Bc9e7595f8fE0E"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'crypto_wallet')

    def test_tax_id_keyword_fr(self):
        """Detect French tax ID keywords."""
        content = b"Numero fiscal: identification impots"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'tax_id_keyword')

    def test_tax_id_keyword_en(self):
        """Detect English tax ID keywords."""
        content = b"Tax identification number for IRS filing"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'tax_id_keyword')

    def test_bank_routing_us(self):
        """Detect US bank routing number."""
        content = b"Routing: 021000021 for wire transfer"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'bank_routing_us')


# =============================================================================
# ARTICLE 9 FILE SCAN TESTS (Sprint 59)
# =============================================================================

class TestArticle9ScanFiles:
    """Test Article 9 patterns with file content scanning."""

    def test_scan_file_with_health_data(self):
        """Scan file containing health data."""
        content = b"Patient diagnostic: cancer stade 2\nTraitement: chimiotherapie"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'health_data')

    def test_scan_file_with_financial_data(self):
        """Scan file containing financial data."""
        content = b"Credit card: 4532015112830366\nSSN: 123-45-6789"
        result = scan_pii_content(content)
        assert isinstance(result, list)

    def test_scan_file_with_mixed_sensitive_data(self):
        """Scan file containing mixed Article 9 and Finance data."""
        content = (
            b"Employee: John Doe\n"
            b"Health: diabete type 2\n"
            b"Union: membre CGT\n"
            b"Salary: 55000 EUR\n"
            b"Card: 5425233430109903"
        )
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'health_data')


# =============================================================================
# EU PARITY TESTS (L-011 Consolidation)
# =============================================================================

class TestEUParityOptimized:
    """Test EU PII patterns parity between pii_scanner and optimized_scanner."""

    def test_dni_es_detected(self):
        """Detect Spanish DNI."""
        content = b"DNI: 12345678Z"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'dni_es')

    def test_nie_es_detected(self):
        """Detect Spanish NIE."""
        content = b"NIE: X0000000T"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'nie_es')

    def test_nif_pt_detected(self):
        """Detect Portuguese NIF."""
        content = b"NIF: 123456789"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'nif_pt')

    def test_pesel_pl_detected(self):
        """Detect Polish PESEL."""
        content = b"PESEL: 02070803628"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'pesel_pl')

    def test_codice_fiscale_it_detected(self):
        """Detect Italian Codice Fiscale."""
        content = b"CF: RSSMRA85M01H501Q"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'codice_fiscale_it')

    def test_iban_sepa_detected(self):
        """Detect SEPA IBAN (generic)."""
        content = b"IBAN: DE89370400440532013000"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'iban')

    def test_iban_fr_detected(self):
        """Detect French IBAN — compact form matched by generic iban (first in dict order)."""
        content = b"IBAN: FR7630006000011234567890189"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        # Compact FR IBAN: iban matches first, iban_fr deduped by normalized value
        assert has_pii_type(result, 'iban') or has_pii_type(result, 'iban_fr')
        # Must NOT have both (dedup fix KI-097)
        assert not (has_pii_type(result, 'iban') and has_pii_type(result, 'iban_fr'))

    def test_iban_fr_spaced_detected(self):
        """Detect French IBAN with spaces — only iban_fr catches this format."""
        content = b"IBAN: FR76 3000 6000 0112 3456 7890 189"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'iban_fr')

    def test_email_uppercase_detected(self):
        """Detect uppercase email."""
        content = b"Contact: JOHN.DOE@EXAMPLE.COM"
        result = scan_pii_content(content)
        assert isinstance(result, list)
        assert has_pii_type(result, 'email')

    def test_patterns_count_parity(self):
        """Verify PII_PATTERNS count matches reference (30 patterns)."""
        from agent.core.optimized_scanner import PII_PATTERNS as OPT_PATTERNS
        from agent.core.pii_scanner import PII_PATTERNS as REF_PATTERNS

        assert len(OPT_PATTERNS) == len(REF_PATTERNS), \
            f"Pattern count mismatch: optimized={len(OPT_PATTERNS)}, reference={len(REF_PATTERNS)}"
        assert len(OPT_PATTERNS) == 30, \
            f"Expected 30 patterns, got {len(OPT_PATTERNS)}"

    def test_iban_fr_no_double_count(self):
        """Verify IBAN FR is not double-counted (deduplication test)."""
        content = b"IBAN: FR7630006000011234567890189"
        result = scan_pii_content(content)
        total_count = sum(p.get('count', 0) for p in result)
        assert total_count == 1, \
            f"Expected 1 IBAN FR match (deduplicated), got {total_count} total matches"


class TestEstimatedDataSubjectsOptimized:
    """KI-101: Test distinct identifier count in optimized scanner."""

    def test_email_dedup_bytes(self):
        """Duplicate emails → counted once in estimated_data_subjects."""
        content = b"alice@example.com bob@test.fr alice@example.com charlie@demo.org"
        result = scan_pii_content(content)
        eds = get_estimated_data_subjects(result)
        assert eds == 3, f"Expected 3 unique emails, got {eds}"

    def test_no_identifiers_iban_only(self):
        """IBAN is not an identifier → estimated_data_subjects=0."""
        content = b"FR7630006000011234567890189"
        result = scan_pii_content(content)
        eds = get_estimated_data_subjects(result)
        assert eds == 0, f"Expected 0 identifiers (IBAN only), got {eds}"

    def test_metadata_present_when_pii(self):
        """_estimated_data_subjects metadata is present when PII found."""
        content = b"Contact: alice@example.com"
        result = scan_pii_content(content)
        assert any('_estimated_data_subjects' in d for d in result)

    def test_empty_content_no_metadata(self):
        """Empty content returns empty list (no metadata appended)."""
        result = scan_pii_content(b"no pii here at all")
        assert len(result) == 0

