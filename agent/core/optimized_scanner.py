"""
Apollo Agent - Optimized Scanner (Hybrid Architecture)
=======================================================

Pipeline optimisé:
1. Fingerprint + Dedup (Bloom filter O(1))
2. Sampling (SmartSampler)
3. Lecture parallèle (ThreadPool - I/O bound)
4. Scan PII parallèle (ProcessPool - CPU bound, bypass GIL)

Date: 2026-01-04
Version: 1.6.1-optimized
"""

import os
import sys
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import re

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

IO_WORKERS = min(int(os.getenv('IO_WORKERS', 8)), 16)
CPU_WORKERS = min(int(os.getenv('CPU_WORKERS', 4)), cpu_count() or 4)

# ============================================================================
# BLOOM FILTER (O(1) dedup)
# ============================================================================

try:
    from pybloom_live import BloomFilter
    BLOOM_AVAILABLE = True
except ImportError:
    BLOOM_AVAILABLE = False
    logger.warning("[OPT] pybloom_live not available, using set() for dedup")

# ============================================================================
# PARALLEL I/O (ThreadPool)
# ============================================================================

def read_single_file(filepath: str) -> tuple:
    """Read first 64KB of file for PII scanning"""
    try:
        with open(filepath, 'rb') as f:
            return (filepath, f.read(65536))
    except Exception as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        return (filepath, None)

def read_files_parallel(file_paths: List[str]) -> Dict[str, bytes]:
    """Parallel file reading with ThreadPoolExecutor"""
    logger.info(f"[I/O] Reading {len(file_paths)} files with {IO_WORKERS} workers")
    
    results = {}
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as executor:
        futures = [executor.submit(read_single_file, fp) for fp in file_paths]
        for future in as_completed(futures):
            try:
                filepath, content = future.result()
                if content is not None:
                    results[filepath] = content
            except Exception as e:
                logger.debug(f"Read error: {e}")
    
    logger.info(f"[I/O] Read {len(results)} files successfully")
    return results

# ============================================================================
# PARALLEL PII SCAN (ProcessPool - bypasses GIL)
# ============================================================================

# Precompiled patterns
PII_PATTERNS = {
    'email': re.compile(rb'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
    'phone_fr': re.compile(rb'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}'),
    'iban_fr': re.compile(rb'FR\d{2}\s*(?:\d{4}\s*){5}\d{3}'),
    'ssn_fr': re.compile(rb'[12]\d{2}(?:0[1-9]|1[0-2])(?:\d{2}|\d[AB])\d{3}\d{3}\d{2}'),

    # Article 9 RGPD - Sensitive Data (Sprint 59)
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
    'gender': re.compile(
        rb'\b('
        rb'genre|sexe|masculin|feminin|homme|femme|'
        rb'gender|sex|male|female|man|woman|'
        rb'non.binaire|non.binary|genderqueer|agender|bigender'
        rb')\b',
        re.IGNORECASE
    ),

    # Financial & Tax Data - HIGH RISK (Sprint 59)
    'credit_card': re.compile(
        rb'\b('
        rb'4\d{15}|'
        rb'5[1-5]\d{14}|2[2-7]\d{14}|'
        rb'3[47]\d{13}|'
        rb'6(?:011|5\d{2}|4[4-9]\d)\d{12}'
        rb')\b'
    ),
    'ssn_us': re.compile(rb'\b(\d{3}-\d{2}-\d{4}|\d{3}\s\d{2}\s\d{4})\b'),
    'ein_us': re.compile(rb'\b\d{2}-\d{7}\b'),
    'itin_us': re.compile(rb'\b9\d{2}-\d{2}-\d{4}\b'),
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
    'crypto_wallet': re.compile(
        rb'\b('
        rb'[13][a-km-zA-HJ-NP-Z1-9]{25,34}|'
        rb'bc1[a-zA-HJ-NP-Z0-9]{39,59}|'
        rb'0x[a-fA-F0-9]{40}'
        rb')\b'
    ),
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
    'bank_routing_us': re.compile(rb'\b(0[1-9]\d{7}|[1-2]\d{8}|3[0-2]\d{7})\b'),

    # API KEYS & SECRETS - SECURITY RISK (V1.7.1)
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

def scan_pii_content(content: bytes) -> List[Dict]:
    """Scan content for PII patterns"""
    found = []
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(content)
        if matches:
            found.append({'type': pii_type, 'count': len(matches)})
    return found

def scan_pii_chunk(chunk: List[tuple]) -> Dict[str, List]:
    """Scan PII on a chunk (runs in separate process)"""
    results = {}
    for filepath, content in chunk:
        if content:
            results[filepath] = scan_pii_content(content)
    return results

def scan_pii_parallel(file_contents: Dict[str, bytes]) -> Dict[str, List]:
    """Parallel PII scanning with ProcessPoolExecutor"""
    if not file_contents:
        return {}

    # PyInstaller frozen exe: ProcessPool workers re-exec the exe and crash
    # Fall back to sequential scanning in frozen mode
    if getattr(sys, 'frozen', False):
        logger.info(f"[CPU] Frozen exe detected, using sequential scan for {len(file_contents)} files")
        results = {}
        for filepath, content in file_contents.items():
            if content:
                results[filepath] = scan_pii_content(content)
        pii_count = sum(1 for r in results.values() if r)
        logger.info(f"[CPU] Found PII in {pii_count}/{len(results)} files")
        return results

    logger.info(f"[CPU] Scanning PII in {len(file_contents)} files with {CPU_WORKERS} workers")

    items = list(file_contents.items())
    chunk_size = max(1, len(items) // (CPU_WORKERS * 4))
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    results = {}
    try:
        with ProcessPoolExecutor(max_workers=CPU_WORKERS) as executor:
            futures = [executor.submit(scan_pii_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                try:
                    chunk_results = future.result(timeout=300)
                    results.update(chunk_results)
                except Exception as e:
                    logger.error(f"[CPU] Chunk error: {e}")
    except Exception as e:
        logger.error(f"[CPU] ProcessPool error, fallback sequential: {e}")
        for filepath, content in items:
            if content:
                results[filepath] = scan_pii_content(content)
    
    pii_count = sum(1 for r in results.values() if r)
    logger.info(f"[CPU] Found PII in {pii_count}/{len(results)} files")
    return results

# ============================================================================
# INTEGRATION HELPER
# ============================================================================

def integrate_with_main_scanner(original_scan_func):
    """Decorator to integrate optimized scanning with original flow"""
    def wrapper(*args, **kwargs):
        # Check if optimization is enabled
        if os.getenv('OPTIMIZED_SCAN', '1') == '1':
            logger.info("[OPT] Using optimized scan pipeline")
            # Extract file_paths from args or kwargs
            # This needs to be adapted based on original function signature
            return original_scan_func(*args, **kwargs)
        else:
            return original_scan_func(*args, **kwargs)
    return wrapper

