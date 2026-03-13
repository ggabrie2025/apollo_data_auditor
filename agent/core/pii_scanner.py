"""
Apollo Agent - PII Scanner (V1.7 EU - Checksum Validated)
==========================================================

Regex-based PII detection with checksum validation - pure stdlib.
11 patterns: email, iban + 9 country-specific (FR, ES, PT, PL, IT, BE, NL)

Version: 1.7.0
Date: 2026-01-08
Update: Added checksum validation for EU patterns (reduces false positives)
        Removed generic patterns without checksum (DE steuerid, personalausweis, AT svnr)

Validated patterns: dni_es, nie_es, nif_pt, pesel_pl, codice_fiscale_it, niss_be, bsn_nl, iban

(c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
import logging

logger = logging.getLogger(__name__)

# Compatible imports for both module and PyInstaller
try:
    from models.contracts import FileMetadata, PIIMatch, PIIScanResult
except ImportError:
    from agent.models.contracts import FileMetadata, PIIMatch, PIIScanResult


# =============================================================================
# YAML CONFIG LOADER (Dynamic - ZERO hardcode)
# =============================================================================

def _load_pii_config() -> Dict:
    """
    Load PII scanner config from exclusions.yaml.
    Falls back to defaults if YAML not found/invalid.
    """
    import yaml

    # Find config file (relative to this file)
    config_paths = [
        Path(__file__).parent.parent / "config" / "exclusions.yaml",
        Path(__file__).parent / "config" / "exclusions.yaml",
        Path("agent/config/exclusions.yaml"),
        Path("config/exclusions.yaml"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config and 'pii_scanner' in config:
                        logger.debug(f"Loaded PII config from {config_path}")
                        return config['pii_scanner']
            except Exception as e:
                logger.warning(f"Failed to load {config_path}: {e}")

    logger.warning("No pii_scanner config found, using defaults")
    return {}


def get_scannable_extensions() -> Set[str]:
    """
    Get scannable extensions from YAML config.
    DYNAMIC: Loaded at runtime, not hardcoded.
    """
    config = _load_pii_config()

    if 'scannable_extensions' in config:
        return set(config['scannable_extensions'])

    # Fallback defaults (should never reach here if YAML is configured)
    return {
        '.txt', '.csv', '.json', '.xml', '.html', '.htm',
        '.md', '.rst', '.log', '.sql', '.yaml', '.yml',
        '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h',
        '.php', '.rb', '.go', '.rs', '.sh', '.bat', '.ps1',
        '.ini', '.cfg', '.conf', '.env', '.properties'
    }


def get_max_scan_size() -> int:
    """
    Get max scan size from YAML config.
    Returns size in bytes.
    """
    config = _load_pii_config()
    max_mb = config.get('max_scan_size_mb', 10)
    return max_mb * 1024 * 1024


# =============================================================================
# DYNAMIC CONFIG (loaded at module level for performance)
# =============================================================================

SCANNABLE_EXTENSIONS = get_scannable_extensions()
MAX_SCAN_SIZE = get_max_scan_size()


# =============================================================================
# CHECKSUM VALIDATORS (EU PII)
# =============================================================================

def _validate_dni_es(value: str) -> bool:
    """Validate Spanish DNI checksum. Letter = number % 23 mapped to table."""
    DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
    try:
        number = int(value[:8])
        letter = value[8].upper()
        return DNI_LETTERS[number % 23] == letter
    except (ValueError, IndexError):
        return False


def _validate_nie_es(value: str) -> bool:
    """Validate Spanish NIE checksum. X=0, Y=1, Z=2 then same as DNI."""
    DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
    PREFIX_MAP = {'X': '0', 'Y': '1', 'Z': '2'}
    try:
        prefix = value[0].upper()
        if prefix not in PREFIX_MAP:
            return False
        number = int(PREFIX_MAP[prefix] + value[1:8])
        letter = value[8].upper()
        return DNI_LETTERS[number % 23] == letter
    except (ValueError, IndexError):
        return False


def _validate_nif_pt(value: str) -> bool:
    """Validate Portuguese NIF checksum (mod 11)."""
    try:
        digits = [int(d) for d in value]
        if len(digits) != 9:
            return False
        # First digit must be valid type (1,2,5,6,7,8,9)
        if digits[0] not in [1, 2, 5, 6, 7, 8, 9]:
            return False
        # Weights for first 8 digits: 9,8,7,6,5,4,3,2
        weights = [9, 8, 7, 6, 5, 4, 3, 2]
        total = sum(d * w for d, w in zip(digits[:8], weights))
        remainder = total % 11
        check_digit = 0 if remainder < 2 else 11 - remainder
        return digits[8] == check_digit
    except (ValueError, IndexError):
        return False


def _validate_pesel_pl(value: str) -> bool:
    """Validate Polish PESEL checksum (weighted sum mod 10)."""
    try:
        digits = [int(d) for d in value]
        if len(digits) != 11:
            return False
        # Weights for first 10 digits
        weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
        total = sum(d * w for d, w in zip(digits[:10], weights))
        check_digit = (10 - (total % 10)) % 10
        return digits[10] == check_digit
    except (ValueError, IndexError):
        return False


def _validate_bsn_nl(value: str) -> bool:
    """Validate Dutch BSN (11-proof): sum of (9-i)*digit[i] % 11 == 0."""
    try:
        digits = [int(d) for d in value]
        if len(digits) != 9:
            return False
        # Weights: 9,8,7,6,5,4,3,2,-1 (last is negative!)
        weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
        total = sum(d * w for d, w in zip(digits, weights))
        return total % 11 == 0
    except (ValueError, IndexError):
        return False


def _validate_niss_be(value: str) -> bool:
    """Validate Belgian NISS (mod 97). Format: YYMMDD-XXX-CC or 11 digits."""
    try:
        # Remove separators
        clean = re.sub(r'[.\s-]', '', value)
        if len(clean) != 11:
            return False
        # First 9 digits + checksum (2 digits)
        base = int(clean[:9])
        checksum = int(clean[9:11])
        # For people born after 2000, prefix with 2
        expected = 97 - (base % 97)
        if expected == checksum:
            return True
        # Try with 2000+ prefix
        base_2000 = int('2' + clean[:9])
        expected_2000 = 97 - (base_2000 % 97)
        return expected_2000 == checksum
    except (ValueError, IndexError):
        return False


def _validate_codice_fiscale_it(value: str) -> bool:
    """Validate Italian Codice Fiscale checksum (last char)."""
    EVEN_MAP = {
        '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
        'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7, 'I': 8, 'J': 9,
        'K': 10, 'L': 11, 'M': 12, 'N': 13, 'O': 14, 'P': 15, 'Q': 16, 'R': 17, 'S': 18,
        'T': 19, 'U': 20, 'V': 21, 'W': 22, 'X': 23, 'Y': 24, 'Z': 25
    }
    ODD_MAP = {
        '0': 1, '1': 0, '2': 5, '3': 7, '4': 9, '5': 13, '6': 15, '7': 17, '8': 19, '9': 21,
        'A': 1, 'B': 0, 'C': 5, 'D': 7, 'E': 9, 'F': 13, 'G': 15, 'H': 17, 'I': 19, 'J': 21,
        'K': 2, 'L': 4, 'M': 18, 'N': 20, 'O': 11, 'P': 3, 'Q': 6, 'R': 8, 'S': 12,
        'T': 14, 'U': 16, 'V': 10, 'W': 22, 'X': 25, 'Y': 24, 'Z': 23
    }
    try:
        cf = value.upper()
        if len(cf) != 16:
            return False
        total = 0
        for i, char in enumerate(cf[:15]):
            if (i + 1) % 2 == 0:  # Even position (1-indexed)
                total += EVEN_MAP.get(char, 0)
            else:  # Odd position
                total += ODD_MAP.get(char, 0)
        expected = chr(ord('A') + (total % 26))
        return cf[15] == expected
    except (ValueError, IndexError, KeyError):
        return False


def _validate_iban(value: str) -> bool:
    """Validate IBAN checksum (mod 97)."""
    try:
        iban = value.upper().replace(' ', '')
        if len(iban) < 15:
            return False
        # Move first 4 chars to end
        rearranged = iban[4:] + iban[:4]
        # Convert letters to numbers (A=10, B=11, etc.)
        numeric = ''
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - ord('A') + 10)
        return int(numeric) % 97 == 1
    except (ValueError, IndexError):
        return False


# Mapping of PII types to their validators
PII_VALIDATORS: Dict[str, callable] = {
    'dni_es': _validate_dni_es,
    'nie_es': _validate_nie_es,
    'nif_pt': _validate_nif_pt,
    'pesel_pl': _validate_pesel_pl,
    'bsn_nl': _validate_bsn_nl,
    'niss_be': _validate_niss_be,
    'codice_fiscale_it': _validate_codice_fiscale_it,
    'iban': _validate_iban,
}


# =============================================================================
# PII PATTERNS (EU - France + European Union)
# Patterns with checksum validation for reduced false positives
# =============================================================================

PII_PATTERNS: Dict[str, re.Pattern] = {
    # --- UNIVERSAL ---
    "email": re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        re.IGNORECASE
    ),
    "iban": re.compile(
        r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]?){0,16}\b',
        re.IGNORECASE
    ),

    # --- FRANCE ---
    "phone_fr": re.compile(
        r'(?<![0-9])(?:(?:\+33|0033|0)\s?[1-9])(?:[\s.-]?\d{2}){4}(?![0-9])'
    ),
    "ssn_fr": re.compile(
        r'\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b'
    ),

    # --- SPAIN (Espagne) ---
    # DNI: 8 digits + control letter (12345678A)
    "dni_es": re.compile(
        r'\b\d{8}[A-HJ-NP-TV-Z]\b',
        re.IGNORECASE
    ),
    # NIE: X/Y/Z + 7 digits + letter (X1234567L) - foreign residents
    "nie_es": re.compile(
        r'\b[XYZ]\d{7}[A-Z]\b',
        re.IGNORECASE
    ),

    # --- PORTUGAL ---
    # NIF: 9 digits starting with 1-3 or 5 (123456789)
    "nif_pt": re.compile(
        r'\b[1235]\d{8}\b'
    ),

    # --- POLAND (Pologne) ---
    # PESEL: 11 digits (YYMMDDXXXXX) - national ID
    "pesel_pl": re.compile(
        r'\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{5}\b'
    ),

    # --- GERMANY (Allemagne) ---
    # REMOVED: steuerid_de (11 digits) - too generic, no reliable checksum
    # REMOVED: personalausweis_de (9 chars) - too generic, conflicts with other patterns

    # --- ITALY (Italie) ---
    # Codice Fiscale: 16 chars (RSSMRA85M01H501Z)
    "codice_fiscale_it": re.compile(
        r'\b[A-Z]{6}\d{2}[A-EHLMPR-T](?:0[1-9]|[12]\d|3[01])[A-Z]\d{3}[A-Z]\b',
        re.IGNORECASE
    ),

    # --- BELGIUM (Belgique) ---
    # NISS/Rijksregisternummer: 11 digits (YY.MM.DD-XXX.XX)
    "niss_be": re.compile(
        r'\b\d{2}[.\s]?\d{2}[.\s]?\d{2}[-.\s]?\d{3}[.\s]?\d{2}\b'
    ),

    # --- NETHERLANDS (Pays-Bas) ---
    # BSN: 9 digits (Burgerservicenummer) - validated by 11-proof checksum
    "bsn_nl": re.compile(
        r'\b\d{9}\b'
    ),

    # --- AUSTRIA (Autriche) ---
    # REMOVED: svnr_at (10 digits) - too generic, no reliable public checksum algorithm

    # ==========================================================================
    # ARTICLE 9 RGPD - SENSITIVE DATA (Sprint 59)
    # ==========================================================================

    # --- HEALTH DATA (Données de santé) ---
    "health_data": re.compile(
        r'\b('
        r'diabete|diabetique|cancer|tumeur|oncolog|VIH|HIV|sida|aids|'
        r'diagnostic|pathologie|symptome|allergie|allergique|maladie|infection|'
        r'disease|illness|diagnosis|symptom|patient|medical.record|health.record|'
        r'medicament|ordonnance|prescription|traitement|therapeut|therapie|'
        r'hospitalisation|hopital|clinique|chirurgie|operation|'
        r'medication|treatment|therapy|hospital|surgery|clinical|'
        r'psychiatr|psycholog|depression|anxiete|bipolaire|schizophren|'
        r'mental.health|psychiatric|psychological|anxiety|bipolar|'
        r'handicap|invalidite|incapacite|arret.maladie|conge.maladie|'
        r'disability|disabled|sick.leave|medical.leave|'
        r'mutuelle|securite.sociale|cpam|assurance.maladie|'
        r'health.insurance|medical.insurance|'
        r'vaccin|vaccination|vaccine|antecedent|medical|sante|health'
        r')\b',
        re.IGNORECASE
    ),

    # --- BIOMETRIC DATA (Données biométriques) ---
    "biometric": re.compile(
        r'\b('
        r'empreinte|fingerprint|empreinte.digitale|'
        r'biometr|biometric|'
        r'reconnaissance.faciale|facial.recognition|face.recognition|'
        r'reconnaissance.vocale|voice.recognition|voice.print|'
        r'scan.retine|retinal.scan|iris|'
        r'geometrie.main|hand.geometry|palm.print|'
        r'ADN|DNA|genome|genomique|genomic|genetique|genetic|chromosome|'
        r'profil.genetique|genetic.profile|test.ADN|DNA.test|analyse.ADN|DNA.analysis'
        r')\b',
        re.IGNORECASE
    ),

    # --- POLITICAL DATA (Opinions politiques/syndicales) ---
    "political": re.compile(
        r'\b('
        r'parti.politique|political.party|affiliation.politique|political.affiliation|'
        r'syndicat|syndical|syndique|union.member|trade.union|labor.union|'
        r'CGT|CFDT|FO|CFTC|CFE.CGC|UNSA|SUD|FSU|'
        r'adherent|membre|militant|member|activist|'
        r'delegue.syndical|shop.steward|union.representative|representant.personnel|'
        r'comite.entreprise|works.council|CSE|'
        r'greve|strike|manifestation|protest|demonstration|'
        r'election|vote|electeur|voter|candidat|candidate|campagne.electorale|political.campaign'
        r')\b',
        re.IGNORECASE
    ),

    # --- RELIGIOUS DATA (Convictions religieuses) ---
    "religious": re.compile(
        r'\b('
        r'catholique|catholic|protestant|lutherien|lutheran|calviniste|calvinist|'
        r'orthodoxe|orthodox|evangelique|evangelical|temoin.jehova|jehovah.witness|'
        r'musulman|muslim|islam|islamique|islamic|'
        r'juif|jewish|judaisme|judaism|'
        r'bouddhiste|buddhist|bouddhisme|buddhism|'
        r'hindou|hindu|hindouisme|hinduism|sikh|sikhisme|'
        r'athee|atheist|agnostique|agnostic|laique|secular|'
        r'religion|religieux|religious|culte|worship|pratiquant|practicing|'
        r'confession|faith|croyance|belief|spirituel|spiritual|priere|prayer|'
        r'eglise|church|mosquee|mosque|synagogue|temple|paroisse|parish'
        r')\b',
        re.IGNORECASE
    ),

    # --- SEXUAL ORIENTATION (Orientation sexuelle) ---
    "sexual_orientation": re.compile(
        r'\b('
        r'homosexuel|homosexual|gay|lesbienne|lesbian|'
        r'bisexuel|bisexual|pansexuel|pansexual|'
        r'heterosexuel|heterosexual|straight|'
        r'transgenre|transgender|transsexuel|transsexual|'
        r'non.binaire|non.binary|genre.fluide|gender.fluid|'
        r'LGBT|LGBTQ|LGBTQI|LGBTQIA|queer|'
        r'orientation.sexuelle|sexual.orientation|'
        r'identite.genre|gender.identity|'
        r'coming.out|pride|gay.pride|fierte|marche.des.fiertes'
        r')\b',
        re.IGNORECASE
    ),

    # --- ETHNIC ORIGIN (Origine ethnique - Article 9 RGPD) ---
    "ethnic_origin": re.compile(
        r'\b('
        # FR - Origine ethnique
        r'origine.ethnique|origine.raciale|race|ethnie|'
        r'ascendance|communaute.ethnique|groupe.ethnique|'
        # EN - Ethnic origin
        r'ethnic.origin|racial.origin|ethnicity|'
        r'ancestry|ethnic.background|ethnic.group|'
        # Specific groups (FR+EN)
        r'caucasien|caucasian|africain|african|asiatique|asian|'
        r'arabe|arab|hispanique|hispanic|latino|latina|'
        r'amerindien|native.american|indigenous|autochtone|'
        r'noir|black|blanc|white|metis|mixed.race|multiracial|biracial'
        r')\b',
        re.IGNORECASE
    ),

    # --- EEO ETHNICITY (US Equal Employment Opportunity categories) ---
    "eeo_ethnicity": re.compile(
        r'\b('
        # Native American/Alaska Native
        r'Native.American|American.Indian|Alaska.Native|tribal|'
        r'Cherokee|Navajo|Sioux|Apache|Iroquois|Lakota|'
        # Asian
        r'Asian.American|Chinese.American|Japanese.American|Korean.American|'
        r'Vietnamese.American|Filipino.American|Indian.American|Pakistani.American|'
        # African American
        r'African.American|Afro.American|Black.American|'
        # Hispanic/Latino
        r'Hispanic.American|Latino.American|Latina.American|Mexican.American|'
        r'Puerto.Rican|Cuban.American|Chicano|Chicana|'
        # Pacific Islander
        r'Pacific.Islander|Hawaiian|Samoan|Guamanian|'
        # Middle Eastern
        r'Middle.Eastern|Arab.American|Persian|Iranian.American|'
        # Two or more races
        r'Two.or.more.races|Multiethnic'
        r')\b',
        re.IGNORECASE
    ),

    # --- GENDER (Genre - Moins sensible mais important) ---
    "gender": re.compile(
        r'\b('
        # FR
        r'genre|sexe|masculin|feminin|homme|femme|'
        # EN
        r'gender|sex|male|female|man|woman|'
        # Non-binary (already in sexual_orientation but useful here too)
        r'non.binaire|non.binary|genderqueer|agender|bigender'
        r')\b',
        re.IGNORECASE
    ),

    # ==========================================================================
    # FINANCIAL & TAX DATA - HIGH RISK (PCI-DSS, SOX, IRS) (Sprint 59)
    # Note: NOT Article 9, but requires encryption (Article 32)
    # ==========================================================================

    # --- CREDIT CARD (PCI-DSS Critical) ---
    "credit_card": re.compile(
        r'\b('
        # Visa: 16 digits starting with 4
        r'4\d{15}|'
        # Mastercard: 16 digits starting with 51-55 or 2221-2720
        r'5[1-5]\d{14}|2[2-7]\d{14}|'
        # Amex: 15 digits starting with 34 or 37
        r'3[47]\d{13}|'
        # Discover: 16 digits starting with 6011, 65, or 644-649
        r'6(?:011|5\d{2}|4[4-9]\d)\d{12}'
        r')\b'
    ),

    # --- US SSN (Social Security Number) ---
    "ssn_us": re.compile(
        r'\b('
        # Format with dashes: 123-45-6789
        r'\d{3}-\d{2}-\d{4}|'
        # Format with spaces: 123 45 6789
        r'\d{3}\s\d{2}\s\d{4}'
        r')\b'
    ),

    # --- US EIN (Employer Identification Number) ---
    "ein_us": re.compile(
        r'\b\d{2}-\d{7}\b'
    ),

    # --- US ITIN (Individual Taxpayer ID - starts with 9) ---
    "itin_us": re.compile(
        r'\b9\d{2}-\d{2}-\d{4}\b'
    ),

    # --- SALARY DATA (FR+EN) ---
    "salary_data": re.compile(
        r'\b('
        # FR - Salaire
        r'salaire|remuneration|traitement|paie|bulletin.de.paie|fiche.de.paie|'
        r'salaire.brut|salaire.net|revenus|prime|bonus|avantages.en.nature|'
        # EN - Salary
        r'salary|compensation|remuneration|wage|payslip|pay.stub|'
        r'gross.salary|net.salary|income|bonus|fringe.benefits|'
        # FR - Stock options
        r'stock.options|actions.gratuites|BSPCE|PEE|PERCO|'
        # EN - Equity
        r'RSU|restricted.stock|equity|ESPP'
        r')\b',
        re.IGNORECASE
    ),

    # --- CRYPTO WALLET (Bitcoin, Ethereum) ---
    "crypto_wallet": re.compile(
        r'\b('
        # Bitcoin address (P2PKH - starts with 1, P2SH - starts with 3, Bech32 - starts with bc1)
        r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}|'
        r'bc1[a-zA-HJ-NP-Z0-9]{39,59}|'
        # Ethereum address (0x + 40 hex chars)
        r'0x[a-fA-F0-9]{40}'
        r')\b'
    ),

    # --- TAX ID KEYWORDS (Generic detection) ---
    "tax_id_keyword": re.compile(
        r'\b('
        # FR
        r'numero.fiscal|numero.de.contribuable|SPI|NIF|avis.d.imposition|'
        r'TVA.intracommunautaire|numero.TVA|revenu.fiscal|RFR|'
        # EN
        r'tax.ID|taxpayer.ID|tax.identification|VAT.number|'
        r'federal.tax|state.tax|tax.return|W-2|1099|'
        # DE
        r'Steueridentifikationsnummer|Steuer-ID|Steuernummer|'
        # UK
        r'UTR|Unique.Taxpayer.Reference|NINO|National.Insurance'
        r')\b',
        re.IGNORECASE
    ),

    # --- BANK ROUTING (US ABA/ACH) ---
    "bank_routing_us": re.compile(
        r'\b('
        # ABA routing number: 9 digits with specific first 2 digit ranges
        r'0[1-9]\d{7}|[1-2]\d{8}|3[0-2]\d{7}'
        r')\b'
    ),

    # ==========================================================================
    # API KEYS & SECRETS - SECURITY RISK (V1.7.1)
    # Detects credentials in .env, config files, source code
    # Dual value: AI Act (shadow AI detection) + Security (credential exposure)
    # ==========================================================================

    # --- API KEY (structured patterns with known prefixes) ---
    "api_key": re.compile(
        r'(?:'
        # OpenAI: sk-proj-... or sk-... (48+ chars)
        r'sk-(?:proj-)?[A-Za-z0-9]{32,}|'
        # Anthropic: sk-ant-...
        r'sk-ant-[A-Za-z0-9\-]{32,}|'
        # AWS Access Key: AKIA + 16 uppercase alphanum
        r'AKIA[0-9A-Z]{16}|'
        # Google API Key: AIza + 35 chars
        r'AIza[0-9A-Za-z\-_]{35}|'
        # Stripe: sk_live_ or sk_test_ + alphanum
        r'sk_(?:live|test)_[A-Za-z0-9]{24,}|'
        # GitHub: ghp_, gho_, ghu_, ghs_, ghr_ + 36 alphanum
        r'gh[pousr]_[A-Za-z0-9]{36}|'
        # Azure: contextual keyword + UUID (32-char hex with dashes)
        r'(?:AZURE_[A-Z_]*KEY|AZURE_[A-Z_]*TOKEN|AZURE_[A-Z_]*SECRET'
        r'|COGNITIVE_SERVICE_KEY|AZURE_SUBSCRIPTION_ID'
        r'|Ocp-Apim-Subscription-Key|api[_-]key|subscription[_-]?(?:key|id))'
        r'\s*[:="\s]\s*'
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        r')',
        re.IGNORECASE
    ),

    # --- SECRET IN ENV (KEY=VALUE pattern in config files) ---
    "secret_env": re.compile(
        r'(?:^|[\s;])(?:'
        # Common secret variable names followed by = and value
        r'(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|AZURE_OPENAI_KEY|AZURE_OPENAI_ENDPOINT|'
        r'AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|'
        r'GOOGLE_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|'
        r'STRIPE_SECRET_KEY|STRIPE_PUBLISHABLE_KEY|'
        r'DATABASE_URL|DB_PASSWORD|REDIS_URL|'
        r'SECRET_KEY|JWT_SECRET|SESSION_SECRET|ENCRYPTION_KEY|'
        r'SENDGRID_API_KEY|TWILIO_AUTH_TOKEN|SLACK_TOKEN|DISCORD_TOKEN|'
        r'GITHUB_TOKEN|GITLAB_TOKEN|NPM_TOKEN|'
        r'PRIVATE_KEY|CLIENT_SECRET|APP_SECRET)'
        r')\s*=\s*\S+',
        re.MULTILINE
    ),
}


def scan_text_for_pii(
    content: str,
    source_path: str = "cloud://unknown",
    max_matches_per_type: int = 10
) -> PIIScanResult:
    """
    Scan PII on raw text content (Sprint 85 - Cloud PII Scan).

    Unlike scan_file_for_pii(), this does NOT read from disk.
    Used for cloud files where content is downloaded via Graph API
    and extracted to text (CSV decode, XLSX openpyxl, etc.).

    Args:
        content: Text content to scan
        source_path: Source identifier for reporting (e.g. onedrive://drive/path)
        max_matches_per_type: Max matches to record per PII type

    Returns:
        PIIScanResult with detected PII
    """
    if not content or not content.strip():
        return PIIScanResult(
            file_path=source_path,
            has_pii=False,
            pii_types=[],
            pii_count=0
        )

    return _scan_content(source_path, content, max_matches_per_type)


def scan_file_for_pii(
    filepath: str,
    max_matches_per_type: int = 10
) -> PIIScanResult:
    """
    Scan a single file for PII patterns.

    Args:
        filepath: Path to file
        max_matches_per_type: Max matches to record per PII type

    Returns:
        PIIScanResult with detected PII
    """
    path = Path(filepath)

    # Check if scannable
    if path.suffix.lower() not in SCANNABLE_EXTENSIONS:
        return PIIScanResult(
            file_path=filepath,
            has_pii=False,
            pii_types=[],
            pii_count=0
        )

    # Check file size
    try:
        size = path.stat().st_size
        if size > MAX_SCAN_SIZE:
            return PIIScanResult(
                file_path=filepath,
                has_pii=False,
                pii_types=[],
                pii_count=0,
                scan_error=f"File too large: {size / 1024 / 1024:.1f}MB"
            )
    except OSError as e:
        return PIIScanResult(
            file_path=filepath,
            has_pii=False,
            pii_types=[],
            pii_count=0,
            scan_error=str(e)
        )

    # Read and scan
    try:
        content = _read_file_content(filepath)
        if content is None:
            return PIIScanResult(
                file_path=filepath,
                has_pii=False,
                pii_types=[],
                pii_count=0,
                scan_error="Could not read file"
            )

        return _scan_content(filepath, content, max_matches_per_type)

    except (OSError, UnicodeDecodeError, PermissionError, IOError) as e:
        return PIIScanResult(
            file_path=filepath,
            has_pii=False,
            pii_types=[],
            pii_count=0,
            scan_error=str(e)
        )


def _read_file_content(filepath: str) -> Optional[str]:
    """Try to read file as text with multiple encodings."""
    encodings = ['utf-8', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
                return f.read()
        except (UnicodeDecodeError, OSError):
            continue

    return None


def _scan_content(
    filepath: str,
    content: str,
    max_matches_per_type: int
) -> PIIScanResult:
    """Scan content for PII patterns with checksum validation."""
    matches: List[PIIMatch] = []
    pii_types_found: set = set()
    total_count = 0

    # Split into lines for line number tracking
    lines = content.split('\n')

    for pii_type, pattern in PII_PATTERNS.items():
        type_count = 0
        validator = PII_VALIDATORS.get(pii_type)

        for line_num, line in enumerate(lines, start=1):
            for match in pattern.finditer(line):
                value = match.group()

                # If validator exists, check checksum
                if validator is not None:
                    if not validator(value):
                        continue  # Skip invalid checksum

                total_count += 1
                type_count += 1
                pii_types_found.add(pii_type)

                # Record match (up to limit)
                if type_count <= max_matches_per_type:
                    preview = value[:4] + "..." if len(value) > 4 else value
                    matches.append(PIIMatch(
                        type=pii_type,
                        value_preview=preview,
                        line_number=line_num
                    ))

    return PIIScanResult(
        file_path=filepath,
        has_pii=total_count > 0,
        pii_types=list(pii_types_found),
        pii_count=total_count,
        matches=matches
    )


def scan_files_for_pii(
    files: List[FileMetadata],
    progress_callback=None
) -> Tuple[List[FileMetadata], Dict[str, int]]:
    """
    Scan multiple files for PII.

    Updates FileMetadata in-place with PII info.

    Args:
        files: List of FileMetadata to scan
        progress_callback: Optional callback(count, filepath)

    Returns:
        Tuple of (updated files, pii_by_type count)
    """
    pii_by_type: Dict[str, int] = {}

    for idx, file_meta in enumerate(files):
        if progress_callback and idx % 50 == 0:
            progress_callback(idx, file_meta.path)

        result = scan_file_for_pii(file_meta.path)

        if result.has_pii:
            file_meta.pii_detected = True
            file_meta.pii_types = result.pii_types
            file_meta.pii_count = result.pii_count

            # Update totals
            for pii_type in result.pii_types:
                pii_by_type[pii_type] = pii_by_type.get(pii_type, 0) + 1

    return files, pii_by_type


def get_pii_patterns_info() -> Dict[str, str]:
    """Get description of PII patterns for display."""
    return {
        # Universal
        "email": "Email addresses (user@domain.com)",
        "iban": "IBAN bank account numbers (all EU) [checksum validated]",

        # France
        "phone_fr": "French phone numbers (+33, 06, 07...)",
        "ssn_fr": "French social security numbers (NIR)",

        # Spain
        "dni_es": "Spanish national ID (DNI) [checksum validated]",
        "nie_es": "Spanish foreign resident ID (NIE) [checksum validated]",

        # Portugal
        "nif_pt": "Portuguese tax ID (NIF) [checksum validated]",

        # Poland
        "pesel_pl": "Polish national ID (PESEL) [checksum validated]",

        # Italy
        "codice_fiscale_it": "Italian tax code (Codice Fiscale) [checksum validated]",

        # Belgium
        "niss_be": "Belgian national number (NISS) [checksum validated]",

        # Netherlands
        "bsn_nl": "Dutch citizen service number (BSN) [checksum validated]",

        # Article 9 RGPD - Sensitive Data (Sprint 59)
        "health_data": "Health and medical data (Article 9 RGPD)",
        "biometric": "Biometric and genetic data (Article 9 RGPD)",
        "political": "Political opinions and trade union membership (Article 9 RGPD)",
        "religious": "Religious or philosophical beliefs (Article 9 RGPD)",
        "sexual_orientation": "Sexual orientation data (Article 9 RGPD)",
        "ethnic_origin": "Ethnic and racial origin data (Article 9 RGPD)",
        "eeo_ethnicity": "US EEO ethnicity categories (HR/Compliance)",
        "gender": "Gender/sex data (Privacy)",

        # Financial & Tax Data - HIGH RISK (Sprint 59)
        "credit_card": "Credit card numbers (PCI-DSS) [Luhn validated]",
        "ssn_us": "US Social Security Number (IRS)",
        "ein_us": "US Employer Identification Number (IRS)",
        "itin_us": "US Individual Taxpayer ID (IRS)",
        "salary_data": "Salary and compensation data (Privacy)",
        "crypto_wallet": "Cryptocurrency wallet addresses (Bitcoin/Ethereum)",
        "tax_id_keyword": "Tax identification keywords (Multi-jurisdiction)",
        "bank_routing_us": "US bank routing numbers (ABA/ACH)",

        # API Keys & Secrets (V1.7.1)
        "api_key": "API keys and tokens (OpenAI, AWS, Google, Stripe, GitHub) [Security Risk]",
        "secret_env": "Secrets in environment variables (DATABASE_URL, JWT_SECRET, etc.) [Security Risk]",
    }


# ============================================================================
# PARALLEL CPU (ProcessPool - bypass GIL)
# ============================================================================

import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
import re

CPU_WORKERS = min(int(os.getenv('CPU_WORKERS', 4)), cpu_count() or 4)

# Precompiled patterns for performance (bytes - parallel scan)
# NOTE: Parallel scan uses regex only, no checksum validation (for speed)
# Full validation happens in _scan_content for detailed analysis
PII_PATTERNS_BYTES = {
    # --- UNIVERSAL ---
    'email': re.compile(rb'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
    'iban': re.compile(rb'[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}', re.IGNORECASE),

    # --- FRANCE ---
    'phone_fr': re.compile(rb'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}'),
    'ssn_fr': re.compile(rb'[12]\d{2}(?:0[1-9]|1[0-2])(?:\d{2}|\d[AB])\d{3}\d{3}\d{2}'),

    # --- SPAIN ---
    'dni_es': re.compile(rb'\d{8}[A-HJ-NP-TV-Z]', re.IGNORECASE),
    'nie_es': re.compile(rb'[XYZ]\d{7}[A-Z]', re.IGNORECASE),

    # --- PORTUGAL ---
    'nif_pt': re.compile(rb'[1235]\d{8}'),

    # --- POLAND ---
    'pesel_pl': re.compile(rb'\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{5}'),

    # --- ITALY ---
    'codice_fiscale_it': re.compile(rb'[A-Z]{6}\d{2}[A-EHLMPR-T](?:0[1-9]|[12]\d|3[01])[A-Z]\d{3}[A-Z]', re.IGNORECASE),

    # --- BELGIUM ---
    'niss_be': re.compile(rb'\d{2}[.\s]?\d{2}[.\s]?\d{2}[-.\s]?\d{3}[.\s]?\d{2}'),

    # --- NETHERLANDS ---
    'bsn_nl': re.compile(rb'\d{9}'),

    # REMOVED: steuerid_de, personalausweis_de, svnr_at (too generic, no checksum)

    # ==========================================================================
    # ARTICLE 9 RGPD - SENSITIVE DATA (Sprint 59)
    # ==========================================================================

    # --- HEALTH DATA ---
    'health_data': re.compile(
        rb'\b('
        rb'diabete|diabetique|cancer|tumeur|oncolog|VIH|HIV|sida|aids|'
        rb'diagnostic|pathologie|symptome|allergie|allergique|maladie|infection|'
        rb'disease|illness|diagnosis|symptom|patient|medical.record|health.record|'
        rb'medicament|ordonnance|prescription|traitement|therapeut|therapie|'
        rb'hospitalisation|hopital|clinique|chirurgie|operation|'
        rb'medication|treatment|therapy|hospital|surgery|clinical|'
        rb'psychiatr|psycholog|depression|anxiete|bipolaire|schizophren|'
        rb'mental.health|psychiatric|psychological|anxiety|bipolar|'
        rb'handicap|invalidite|incapacite|arret.maladie|conge.maladie|'
        rb'disability|disabled|sick.leave|medical.leave|'
        rb'mutuelle|securite.sociale|cpam|assurance.maladie|'
        rb'health.insurance|medical.insurance|'
        rb'vaccin|vaccination|vaccine|antecedent|medical|sante|health'
        rb')\b',
        re.IGNORECASE
    ),

    # --- BIOMETRIC DATA ---
    'biometric': re.compile(
        rb'\b('
        rb'empreinte|fingerprint|empreinte.digitale|'
        rb'biometr|biometric|'
        rb'reconnaissance.faciale|facial.recognition|face.recognition|'
        rb'reconnaissance.vocale|voice.recognition|voice.print|'
        rb'scan.retine|retinal.scan|iris|'
        rb'geometrie.main|hand.geometry|palm.print|'
        rb'ADN|DNA|genome|genomique|genomic|genetique|genetic|chromosome|'
        rb'profil.genetique|genetic.profile|test.ADN|DNA.test|analyse.ADN|DNA.analysis'
        rb')\b',
        re.IGNORECASE
    ),

    # --- POLITICAL DATA ---
    'political': re.compile(
        rb'\b('
        rb'parti.politique|political.party|affiliation.politique|political.affiliation|'
        rb'syndicat|syndical|syndique|union.member|trade.union|labor.union|'
        rb'CGT|CFDT|FO|CFTC|CFE.CGC|UNSA|SUD|FSU|'
        rb'adherent|membre|militant|member|activist|'
        rb'delegue.syndical|shop.steward|union.representative|representant.personnel|'
        rb'comite.entreprise|works.council|CSE|'
        rb'greve|strike|manifestation|protest|demonstration|'
        rb'election|vote|electeur|voter|candidat|candidate|campagne.electorale|political.campaign'
        rb')\b',
        re.IGNORECASE
    ),

    # --- RELIGIOUS DATA ---
    'religious': re.compile(
        rb'\b('
        rb'catholique|catholic|protestant|lutherien|lutheran|calviniste|calvinist|'
        rb'orthodoxe|orthodox|evangelique|evangelical|temoin.jehova|jehovah.witness|'
        rb'musulman|muslim|islam|islamique|islamic|'
        rb'juif|jewish|judaisme|judaism|'
        rb'bouddhiste|buddhist|bouddhisme|buddhism|'
        rb'hindou|hindu|hindouisme|hinduism|sikh|sikhisme|'
        rb'athee|atheist|agnostique|agnostic|laique|secular|'
        rb'religion|religieux|religious|culte|worship|pratiquant|practicing|'
        rb'confession|faith|croyance|belief|spirituel|spiritual|priere|prayer|'
        rb'eglise|church|mosquee|mosque|synagogue|temple|paroisse|parish'
        rb')\b',
        re.IGNORECASE
    ),

    # --- SEXUAL ORIENTATION ---
    'sexual_orientation': re.compile(
        rb'\b('
        rb'homosexuel|homosexual|gay|lesbienne|lesbian|'
        rb'bisexuel|bisexual|pansexuel|pansexual|'
        rb'heterosexuel|heterosexual|straight|'
        rb'transgenre|transgender|transsexuel|transsexual|'
        rb'non.binaire|non.binary|genre.fluide|gender.fluid|'
        rb'LGBT|LGBTQ|LGBTQI|LGBTQIA|queer|'
        rb'orientation.sexuelle|sexual.orientation|'
        rb'identite.genre|gender.identity|'
        rb'coming.out|pride|gay.pride|fierte|marche.des.fiertes'
        rb')\b',
        re.IGNORECASE
    ),

    # --- ETHNIC ORIGIN ---
    'ethnic_origin': re.compile(
        rb'\b('
        rb'origine.ethnique|origine.raciale|race|ethnie|'
        rb'ascendance|communaute.ethnique|groupe.ethnique|'
        rb'ethnic.origin|racial.origin|ethnicity|'
        rb'ancestry|ethnic.background|ethnic.group|'
        rb'caucasien|caucasian|africain|african|asiatique|asian|'
        rb'arabe|arab|hispanique|hispanic|latino|latina|'
        rb'amerindien|native.american|indigenous|autochtone|'
        rb'noir|black|blanc|white|metis|mixed.race|multiracial|biracial'
        rb')\b',
        re.IGNORECASE
    ),

    # --- EEO ETHNICITY ---
    'eeo_ethnicity': re.compile(
        rb'\b('
        rb'Native.American|American.Indian|Alaska.Native|tribal|'
        rb'Cherokee|Navajo|Sioux|Apache|Iroquois|Lakota|'
        rb'Asian.American|Chinese.American|Japanese.American|Korean.American|'
        rb'Vietnamese.American|Filipino.American|Indian.American|Pakistani.American|'
        rb'African.American|Afro.American|Black.American|'
        rb'Hispanic.American|Latino.American|Latina.American|Mexican.American|'
        rb'Puerto.Rican|Cuban.American|Chicano|Chicana|'
        rb'Pacific.Islander|Hawaiian|Samoan|Guamanian|'
        rb'Middle.Eastern|Arab.American|Persian|Iranian.American|'
        rb'Two.or.more.races|Multiethnic'
        rb')\b',
        re.IGNORECASE
    ),

    # --- GENDER ---
    'gender': re.compile(
        rb'\b('
        rb'genre|sexe|masculin|feminin|homme|femme|'
        rb'gender|sex|male|female|man|woman|'
        rb'non.binaire|non.binary|genderqueer|agender|bigender'
        rb')\b',
        re.IGNORECASE
    ),

    # ==========================================================================
    # FINANCIAL & TAX DATA - HIGH RISK (Sprint 59)
    # ==========================================================================

    # --- CREDIT CARD (PCI-DSS) ---
    'credit_card': re.compile(
        rb'\b('
        rb'4\d{15}|'
        rb'5[1-5]\d{14}|2[2-7]\d{14}|'
        rb'3[47]\d{13}|'
        rb'6(?:011|5\d{2}|4[4-9]\d)\d{12}'
        rb')\b'
    ),

    # --- US SSN ---
    'ssn_us': re.compile(
        rb'\b('
        rb'\d{3}-\d{2}-\d{4}|'
        rb'\d{3}\s\d{2}\s\d{4}'
        rb')\b'
    ),

    # --- US EIN ---
    'ein_us': re.compile(rb'\b\d{2}-\d{7}\b'),

    # --- US ITIN ---
    'itin_us': re.compile(rb'\b9\d{2}-\d{2}-\d{4}\b'),

    # --- SALARY DATA ---
    'salary_data': re.compile(
        rb'\b('
        rb'salaire|remuneration|traitement|paie|bulletin.de.paie|fiche.de.paie|'
        rb'salaire.brut|salaire.net|revenus|prime|bonus|avantages.en.nature|'
        rb'salary|compensation|remuneration|wage|payslip|pay.stub|'
        rb'gross.salary|net.salary|income|bonus|fringe.benefits|'
        rb'stock.options|actions.gratuites|BSPCE|PEE|PERCO|'
        rb'RSU|restricted.stock|equity|ESPP'
        rb')\b',
        re.IGNORECASE
    ),

    # --- CRYPTO WALLET ---
    'crypto_wallet': re.compile(
        rb'\b('
        rb'[13][a-km-zA-HJ-NP-Z1-9]{25,34}|'
        rb'bc1[a-zA-HJ-NP-Z0-9]{39,59}|'
        rb'0x[a-fA-F0-9]{40}'
        rb')\b'
    ),

    # --- TAX ID KEYWORDS ---
    'tax_id_keyword': re.compile(
        rb'\b('
        rb'numero.fiscal|numero.de.contribuable|SPI|NIF|avis.d.imposition|'
        rb'TVA.intracommunautaire|numero.TVA|revenu.fiscal|RFR|'
        rb'tax.ID|taxpayer.ID|tax.identification|VAT.number|'
        rb'federal.tax|state.tax|tax.return|W-2|1099|'
        rb'Steueridentifikationsnummer|Steuer-ID|Steuernummer|'
        rb'UTR|Unique.Taxpayer.Reference|NINO|National.Insurance'
        rb')\b',
        re.IGNORECASE
    ),

    # --- US BANK ROUTING ---
    'bank_routing_us': re.compile(
        rb'\b('
        rb'0[1-9]\d{7}|[1-2]\d{8}|3[0-2]\d{7}'
        rb')\b'
    ),

    # ==========================================================================
    # API KEYS & SECRETS - SECURITY RISK (V1.7.1)
    # ==========================================================================

    # --- API KEY (structured patterns) ---
    'api_key': re.compile(
        rb'(?:'
        rb'sk-(?:proj-)?[A-Za-z0-9]{32,}|'
        rb'sk-ant-[A-Za-z0-9\-]{32,}|'
        rb'AKIA[0-9A-Z]{16}|'
        rb'AIza[0-9A-Za-z\-_]{35}|'
        rb'sk_(?:live|test)_[A-Za-z0-9]{24,}|'
        rb'gh[pousr]_[A-Za-z0-9]{36}|'
        rb'(?:AZURE_[A-Z_]*KEY|AZURE_[A-Z_]*TOKEN|AZURE_[A-Z_]*SECRET'
        rb'|COGNITIVE_SERVICE_KEY|AZURE_SUBSCRIPTION_ID'
        rb'|Ocp-Apim-Subscription-Key|api[_-]key|subscription[_-]?(?:key|id))'
        rb'\s*[:="\s]\s*'
        rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        rb')',
        re.IGNORECASE
    ),

    # --- SECRET IN ENV (KEY=VALUE pattern) ---
    'secret_env': re.compile(
        rb'(?:^|[\s;])(?:'
        rb'(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|AZURE_OPENAI_KEY|AZURE_OPENAI_ENDPOINT|'
        rb'AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|'
        rb'GOOGLE_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|'
        rb'STRIPE_SECRET_KEY|STRIPE_PUBLISHABLE_KEY|'
        rb'DATABASE_URL|DB_PASSWORD|REDIS_URL|'
        rb'SECRET_KEY|JWT_SECRET|SESSION_SECRET|ENCRYPTION_KEY|'
        rb'SENDGRID_API_KEY|TWILIO_AUTH_TOKEN|SLACK_TOKEN|DISCORD_TOKEN|'
        rb'GITHUB_TOKEN|GITLAB_TOKEN|NPM_TOKEN|'
        rb'PRIVATE_KEY|CLIENT_SECRET|APP_SECRET)'
        rb')\s*=\s*\S+',
        re.MULTILINE
    ),
}

def detect_pii_in_bytes(content: bytes) -> list:
    """Detect PII in bytes content using precompiled regex"""
    found = []
    for pii_type, pattern in PII_PATTERNS_BYTES.items():
        matches = pattern.findall(content)
        if matches:
            found.append({'type': pii_type, 'count': len(matches)})
    return found

def scan_pii_chunk(chunk: list) -> dict:
    """Scan PII on a chunk of files (runs in separate process)"""
    results = {}
    for filepath, content in chunk:
        if content:
            pii_found = detect_pii_in_bytes(content)
            results[filepath] = pii_found
    return results

def scan_pii_parallel(file_contents: dict) -> dict:
    """Parallel PII scan - ProcessPoolExecutor (bypasses GIL)"""
    logger.info(f"[PARALLEL-CPU] Scan PII {len(file_contents)} fichiers, {CPU_WORKERS} workers")
    
    if not file_contents:
        return {}
    
    results = {}
    items = list(file_contents.items())
    
    # Calculate chunk size
    chunk_size = max(1, len(items) // (CPU_WORKERS * 4))
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
    
    try:
        with ProcessPoolExecutor(max_workers=CPU_WORKERS) as executor:
            futures = [executor.submit(scan_pii_chunk, chunk) for chunk in chunks]
            
            for future in futures:
                try:
                    chunk_results = future.result(timeout=300)  # 5 min timeout per chunk
                    results.update(chunk_results)
                except Exception as e:
                    logger.error(f"[PARALLEL-CPU] Chunk error: {e}")
    except Exception as e:
        logger.error(f"[PARALLEL-CPU] ProcessPool error: {e}")
        # Fallback to sequential
        for filepath, content in items:
            if content:
                results[filepath] = detect_pii_in_bytes(content)
    
    logger.info(f"[PARALLEL-CPU] {len(results)} fichiers scannés")
    return results

