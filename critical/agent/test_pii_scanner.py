"""
Tests PII Scanner V1.7 - Sprint 40
===================================

Tests unitaires pour agent/core/pii_scanner.py
Valide les patterns EU avec checksums.

(c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import pytest
import tempfile
import os

from agent.core.pii_scanner import (
    scan_file_for_pii,
    get_pii_patterns_info,
    PII_PATTERNS,
    PII_VALIDATORS,
    _validate_dni_es,
    _validate_nie_es,
    _validate_nif_pt,
    _validate_pesel_pl,
    _validate_bsn_nl,
    _validate_niss_be,
    _validate_codice_fiscale_it,
    _validate_iban,
)


class TestPIIPatterns:
    """Test PII pattern detection."""

    def test_patterns_count(self):
        """V1.7.2 should have 30 patterns (12 original + 8 Article 9 + 8 Finance/Tax + 2 API/Secrets)."""
        assert len(PII_PATTERNS) == 30

    def test_validators_count(self):
        """V1.7.R should have 9 validators (added iban_fr)."""
        assert len(PII_VALIDATORS) == 9

    def test_email_pattern(self):
        """Test email detection."""
        assert PII_PATTERNS['email'].search("test@example.com")
        assert PII_PATTERNS['email'].search("user.name@domain.fr")
        assert not PII_PATTERNS['email'].search("not an email")

    def test_phone_fr_pattern(self):
        """Test French phone detection."""
        assert PII_PATTERNS['phone_fr'].search("+33612345678")
        assert PII_PATTERNS['phone_fr'].search("06 12 34 56 78")
        assert PII_PATTERNS['phone_fr'].search("0612345678")

    def test_iban_pattern(self):
        """Test IBAN detection."""
        assert PII_PATTERNS['iban'].search("FR7630006000011234567890189")
        assert PII_PATTERNS['iban'].search("DE89370400440532013000")

    def test_iban_fr_pattern(self):
        """Test FR-specific IBAN detection."""
        assert PII_PATTERNS['iban_fr'].search("FR7630006000011234567890189")
        assert not PII_PATTERNS['iban_fr'].search("DE89370400440532013000")

    def test_ssn_fr_pattern(self):
        """Test French SSN detection."""
        assert PII_PATTERNS['ssn_fr'].search("1 85 12 75 108 008 42")
        assert PII_PATTERNS['ssn_fr'].search("2 93 07 99 123 456 78")


class TestDNIValidator:
    """Test Spanish DNI checksum validation."""

    def test_valid_dni(self):
        """Valid DNI: 12345678Z."""
        assert _validate_dni_es("12345678Z") is True

    def test_invalid_dni_wrong_letter(self):
        """Invalid DNI: wrong letter."""
        assert _validate_dni_es("12345678A") is False

    def test_invalid_dni_format(self):
        """Invalid DNI: wrong format."""
        assert _validate_dni_es("1234567Z") is False
        assert _validate_dni_es("ABCDEFGHZ") is False


class TestNIEValidator:
    """Test Spanish NIE checksum validation."""

    def test_valid_nie_x(self):
        """Valid NIE starting with X."""
        assert _validate_nie_es("X0000000T") is True

    def test_valid_nie_y(self):
        """Valid NIE starting with Y."""
        assert _validate_nie_es("Y0000000Z") is True

    def test_invalid_nie(self):
        """Invalid NIE: wrong letter."""
        assert _validate_nie_es("X1234567A") is False


class TestNIFValidator:
    """Test Portuguese NIF checksum validation."""

    def test_valid_nif(self):
        """Valid NIF: 123456789."""
        assert _validate_nif_pt("123456789") is True

    def test_invalid_nif_checksum(self):
        """Invalid NIF: wrong checksum."""
        assert _validate_nif_pt("123456788") is False

    def test_invalid_nif_first_digit(self):
        """Invalid NIF: invalid first digit (0, 3, 4)."""
        assert _validate_nif_pt("012345678") is False
        assert _validate_nif_pt("312345678") is False


class TestPESELValidator:
    """Test Polish PESEL checksum validation."""

    def test_valid_pesel(self):
        """Valid PESEL: 02070803628."""
        assert _validate_pesel_pl("02070803628") is True

    def test_invalid_pesel(self):
        """Invalid PESEL: wrong checksum."""
        assert _validate_pesel_pl("44051401358") is False

    def test_invalid_pesel_length(self):
        """Invalid PESEL: wrong length."""
        assert _validate_pesel_pl("1234567890") is False


class TestBSNValidator:
    """Test Dutch BSN 11-proof validation."""

    def test_valid_bsn(self):
        """Valid BSN: 111222333."""
        assert _validate_bsn_nl("111222333") is True

    def test_invalid_bsn(self):
        """Invalid BSN: fails 11-proof."""
        assert _validate_bsn_nl("123456789") is False

    def test_invalid_bsn_length(self):
        """Invalid BSN: wrong length."""
        assert _validate_bsn_nl("12345678") is False


class TestNISSValidator:
    """Test Belgian NISS mod 97 validation."""

    def test_valid_niss(self):
        """Valid NISS: 85073003328."""
        assert _validate_niss_be("85073003328") is True

    def test_valid_niss_with_dots(self):
        """Valid NISS with formatting."""
        assert _validate_niss_be("85.07.30-033.28") is True

    def test_invalid_niss(self):
        """Invalid NISS: wrong checksum."""
        assert _validate_niss_be("85073003329") is False


class TestCodiceFiscaleValidator:
    """Test Italian Codice Fiscale checksum validation."""

    def test_valid_cf(self):
        """Valid Codice Fiscale."""
        assert _validate_codice_fiscale_it("RSSMRA85M01H501Q") is True

    def test_invalid_cf(self):
        """Invalid Codice Fiscale: wrong check char."""
        assert _validate_codice_fiscale_it("RSSMRA85M01H501Z") is False


class TestIBANValidator:
    """Test IBAN mod 97 validation."""

    def test_valid_iban_fr(self):
        """Valid French IBAN."""
        assert _validate_iban("FR7630006000011234567890189") is True

    def test_valid_iban_de(self):
        """Valid German IBAN."""
        assert _validate_iban("DE89370400440532013000") is True

    def test_invalid_iban(self):
        """Invalid IBAN: wrong checksum."""
        assert _validate_iban("FR7630006000011234567890188") is False


class TestScanFile:
    """Test file scanning functionality."""

    def test_scan_file_with_pii(self):
        """Scan file containing PII."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Contact: jean@example.fr\n")
            f.write("Phone: +33612345678\n")
            f.write("IBAN: FR7630006000011234567890189\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert result.pii_count >= 3
            assert 'email' in result.pii_types
            assert 'phone_fr' in result.pii_types
            assert 'iban' in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_scan_file_without_pii(self):
        """Scan file without PII."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("This is a normal file.\n")
            f.write("No personal data here.\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is False
            assert result.pii_count == 0
        finally:
            os.unlink(temp_path)

    def test_scan_nonexistent_file(self):
        """Scan non-existent file returns error."""
        result = scan_file_for_pii("/nonexistent/file.txt")
        assert result.has_pii is False
        assert result.scan_error is not None

    def test_scan_binary_file_skipped(self):
        """Binary files should be skipped."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b'\x00\x01\x02\x03')
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            # Binary files should be skipped (not scannable extension)
            assert result.pii_count == 0
        finally:
            os.unlink(temp_path)


class TestScanMultipleFiles:
    """Test batch file scanning."""

    def test_scan_multiple_files(self):
        """Scan multiple files individually."""
        files = []
        try:
            # Create test files
            for i in range(3):
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                    f.write(f"Email: user{i}@test.com\n")
                    files.append(f.name)

            # Scan each file individually
            results = [scan_file_for_pii(f) for f in files]
            assert len(results) == 3
            for result in results:
                assert result.has_pii is True
        finally:
            for f in files:
                os.unlink(f)


class TestGetPatternsInfo:
    """Test pattern info retrieval."""

    def test_get_patterns_info(self):
        """Get pattern info returns dict."""
        info = get_pii_patterns_info()
        assert isinstance(info, dict)
        assert 'email' in info
        assert 'iban' in info
        assert len(info) == 29  # 11 original + 8 Article 9 + 8 Finance/Tax + 2 API/Secrets


class TestChecksumIntegration:
    """Integration tests - checksum filtering in scan."""

    def test_invalid_dni_not_detected(self):
        """Invalid DNI should not be detected due to checksum."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Invalid DNI (wrong letter)
            f.write("DNI: 12345678A\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert 'dni_es' not in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_valid_dni_detected(self):
        """Valid DNI should be detected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("DNI: 12345678Z\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert 'dni_es' in result.pii_types
        finally:
            os.unlink(temp_path)


# =============================================================================
# ARTICLE 9 RGPD - SENSITIVE DATA TESTS (Sprint 59)
# =============================================================================

class TestArticle9Patterns:
    """Test Article 9 RGPD sensitive data patterns."""

    def test_health_data_pattern_fr(self):
        """Test health data detection - French terms."""
        assert PII_PATTERNS['health_data'].search("diagnostic cancer")
        assert PII_PATTERNS['health_data'].search("traitement diabete")
        assert PII_PATTERNS['health_data'].search("arret maladie")
        assert PII_PATTERNS['health_data'].search("hospitalisation")
        assert not PII_PATTERNS['health_data'].search("hello world")

    def test_health_data_pattern_en(self):
        """Test health data detection - English terms."""
        assert PII_PATTERNS['health_data'].search("cancer diagnosis")
        assert PII_PATTERNS['health_data'].search("medical treatment")
        assert PII_PATTERNS['health_data'].search("sick leave")
        assert PII_PATTERNS['health_data'].search("health insurance")

    def test_biometric_pattern(self):
        """Test biometric data detection."""
        assert PII_PATTERNS['biometric'].search("empreinte digitale")
        assert PII_PATTERNS['biometric'].search("fingerprint scan")
        assert PII_PATTERNS['biometric'].search("test ADN")
        assert PII_PATTERNS['biometric'].search("DNA analysis")
        assert PII_PATTERNS['biometric'].search("reconnaissance faciale")
        assert PII_PATTERNS['biometric'].search("facial recognition")

    def test_political_pattern_fr(self):
        """Test political/union data detection - French."""
        assert PII_PATTERNS['political'].search("adherent syndicat")
        assert PII_PATTERNS['political'].search("delegue CGT")
        assert PII_PATTERNS['political'].search("greve")
        assert PII_PATTERNS['political'].search("comite entreprise")

    def test_political_pattern_en(self):
        """Test political/union data detection - English."""
        assert PII_PATTERNS['political'].search("trade union member")
        assert PII_PATTERNS['political'].search("strike action")
        assert PII_PATTERNS['political'].search("works council")

    def test_religious_pattern(self):
        """Test religious data detection."""
        assert PII_PATTERNS['religious'].search("pratiquant catholique")
        assert PII_PATTERNS['religious'].search("catholic church")
        assert PII_PATTERNS['religious'].search("mosquee")
        assert PII_PATTERNS['religious'].search("mosque")
        assert PII_PATTERNS['religious'].search("confession religieuse")
        assert PII_PATTERNS['religious'].search("religious belief")

    def test_sexual_orientation_pattern(self):
        """Test sexual orientation detection."""
        assert PII_PATTERNS['sexual_orientation'].search("orientation sexuelle")
        assert PII_PATTERNS['sexual_orientation'].search("sexual orientation")
        assert PII_PATTERNS['sexual_orientation'].search("LGBT")
        assert PII_PATTERNS['sexual_orientation'].search("gay pride")

    def test_ethnic_origin_pattern_fr(self):
        """Test ethnic origin detection - French."""
        assert PII_PATTERNS['ethnic_origin'].search("origine ethnique")
        assert PII_PATTERNS['ethnic_origin'].search("origine raciale")
        assert PII_PATTERNS['ethnic_origin'].search("groupe ethnique")

    def test_ethnic_origin_pattern_en(self):
        """Test ethnic origin detection - English."""
        assert PII_PATTERNS['ethnic_origin'].search("ethnic origin")
        assert PII_PATTERNS['ethnic_origin'].search("racial origin")
        assert PII_PATTERNS['ethnic_origin'].search("ethnicity")
        assert PII_PATTERNS['ethnic_origin'].search("African American")

    def test_eeo_ethnicity_pattern(self):
        """Test US EEO ethnicity categories."""
        assert PII_PATTERNS['eeo_ethnicity'].search("Native American")
        assert PII_PATTERNS['eeo_ethnicity'].search("African American")
        assert PII_PATTERNS['eeo_ethnicity'].search("Hispanic American")
        assert PII_PATTERNS['eeo_ethnicity'].search("Asian American")
        assert PII_PATTERNS['eeo_ethnicity'].search("Pacific Islander")

    def test_gender_pattern(self):
        """Test gender detection (contextual pattern, fix M-015)."""
        # True positives — structured label:value
        assert PII_PATTERNS['gender'].search("genre: masculin")
        assert PII_PATTERNS['gender'].search("Gender: Male")
        assert PII_PATTERNS['gender'].search("sex=female")
        assert PII_PATTERNS['gender'].search("Sexe: F")
        assert PII_PATTERNS['gender'].search("gender: feminin")
        assert PII_PATTERNS['gender'].search("genderqueer identity")
        # True negatives — common words in prose
        assert not PII_PATTERNS['gender'].search("The old man")
        assert not PII_PATTERNS['gender'].search("strong woman")
        assert not PII_PATTERNS['gender'].search("male connector")
        assert not PII_PATTERNS['gender'].search("female adapter")


class TestArticle9ScanFile:
    """Integration tests - Article 9 file scanning."""

    def test_scan_file_with_health_data(self):
        """Scan file containing health data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Patient: diagnostic cancer stade 2\n")
            f.write("Traitement: chimiotherapie\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'health_data' in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_scan_file_with_biometric(self):
        """Scan file containing biometric data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Fichier empreinte digitale employe\n")
            f.write("ADN: analyse complete\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'biometric' in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_scan_file_with_political(self):
        """Scan file containing political/union data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Liste adherents syndicat CGT\n")
            f.write("Delegue: Jean Dupont\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'political' in result.pii_types
        finally:
            os.unlink(temp_path)


# =============================================================================
# FINANCIAL & TAX DATA TESTS (Sprint 59)
# =============================================================================

class TestFinanceTaxPatterns:
    """Test Financial & Tax data patterns (PCI-DSS, SOX, IRS)."""

    def test_credit_card_visa(self):
        """Test Visa credit card detection."""
        assert PII_PATTERNS['credit_card'].search("4111111111111111")  # Visa test
        assert PII_PATTERNS['credit_card'].search("4532015112830366")  # Visa

    def test_credit_card_mastercard(self):
        """Test Mastercard detection."""
        assert PII_PATTERNS['credit_card'].search("5425233430109903")  # MC test
        assert PII_PATTERNS['credit_card'].search("5105105105105100")  # MC

    def test_credit_card_amex(self):
        """Test Amex detection."""
        assert PII_PATTERNS['credit_card'].search("371449635398431")  # Amex (15 digits)
        assert PII_PATTERNS['credit_card'].search("340000000000009")  # Amex

    def test_ssn_us_with_dashes(self):
        """Test US SSN with dashes."""
        assert PII_PATTERNS['ssn_us'].search("123-45-6789")
        assert PII_PATTERNS['ssn_us'].search("987-65-4321")

    def test_ssn_us_with_spaces(self):
        """Test US SSN with spaces."""
        assert PII_PATTERNS['ssn_us'].search("123 45 6789")

    def test_ein_us(self):
        """Test US EIN detection."""
        assert PII_PATTERNS['ein_us'].search("12-3456789")
        assert PII_PATTERNS['ein_us'].search("99-1234567")

    def test_itin_us(self):
        """Test US ITIN detection (starts with 9)."""
        assert PII_PATTERNS['itin_us'].search("912-34-5678")
        assert PII_PATTERNS['itin_us'].search("999-88-7777")

    def test_salary_data_fr(self):
        """Test salary data detection - French."""
        assert PII_PATTERNS['salary_data'].search("bulletin de paie")
        assert PII_PATTERNS['salary_data'].search("salaire brut")
        assert PII_PATTERNS['salary_data'].search("fiche de paie")

    def test_salary_data_en(self):
        """Test salary data detection - English."""
        assert PII_PATTERNS['salary_data'].search("payslip")
        assert PII_PATTERNS['salary_data'].search("gross salary")
        assert PII_PATTERNS['salary_data'].search("RSU")

    def test_crypto_wallet_bitcoin(self):
        """Test Bitcoin address detection."""
        # P2PKH (starts with 1)
        assert PII_PATTERNS['crypto_wallet'].search("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")
        # P2SH (starts with 3)
        assert PII_PATTERNS['crypto_wallet'].search("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")

    def test_crypto_wallet_ethereum(self):
        """Test Ethereum address detection."""
        assert PII_PATTERNS['crypto_wallet'].search("0x742d35Cc6634C0532925a3b844Bc9e7595f3E7c7")

    def test_tax_id_keyword_fr(self):
        """Test tax ID keywords - French."""
        assert PII_PATTERNS['tax_id_keyword'].search("numero fiscal")
        assert PII_PATTERNS['tax_id_keyword'].search("TVA intracommunautaire")
        assert PII_PATTERNS['tax_id_keyword'].search("avis d imposition")

    def test_tax_id_keyword_en(self):
        """Test tax ID keywords - English."""
        assert PII_PATTERNS['tax_id_keyword'].search("tax ID")
        assert PII_PATTERNS['tax_id_keyword'].search("W-2")
        assert PII_PATTERNS['tax_id_keyword'].search("1099")

    def test_bank_routing_us(self):
        """Test US bank routing number detection (contextual pattern, fix M-016)."""
        # True positives — keyword + number
        assert PII_PATTERNS['bank_routing_us'].search("routing: 021000021")
        assert PII_PATTERNS['bank_routing_us'].search("ABA: 121000358")
        assert PII_PATTERNS['bank_routing_us'].search("ACH #021000021")
        assert PII_PATTERNS['bank_routing_us'].search("wire transfer 121000358")
        assert PII_PATTERNS['bank_routing_us'].search("Bank code: 021000021")
        # True negatives — bare numbers (no context)
        assert not PII_PATTERNS['bank_routing_us'].search("021000021")
        assert not PII_PATTERNS['bank_routing_us'].search("ID: 121000358")
        assert not PII_PATTERNS['bank_routing_us'].search("zipcode 123456789")


class TestFinanceTaxScanFile:
    """Integration tests - Finance/Tax file scanning."""

    def test_scan_file_with_credit_card(self):
        """Scan file containing credit card data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Customer card: 4111111111111111\n")
            f.write("Expiry: 12/25\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'credit_card' in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_scan_file_with_salary(self):
        """Scan file containing salary data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Employee John Doe\n")
            f.write("Salaire brut: 45000 EUR\n")
            f.write("Bonus: 5000 EUR\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'salary_data' in result.pii_types
        finally:
            os.unlink(temp_path)

    def test_scan_file_with_ssn_us(self):
        """Scan file containing US SSN."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Employee SSN: 123-45-6789\n")
            temp_path = f.name

        try:
            result = scan_file_for_pii(temp_path)
            assert result.has_pii is True
            assert 'ssn_us' in result.pii_types
        finally:
            os.unlink(temp_path)
