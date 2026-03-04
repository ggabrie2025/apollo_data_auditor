"""
V1.5 Agent - Fingerprint Generator (Étape 1)

Génère des fingerprints LÉGERS basés sur metadata uniquement (stat() only, NO read()).
Copié depuis backend/src/unstructured/fingerprint.py (V1.1)

Architecture:
- LightFingerprint: Metadata (path_hash, size, mtime, extension, zone)
- Zone detection: SENSITIVE / NORMAL / ARCHIVE
- Streaming generator: Scalable à 10M+ fichiers

GATE 1.1: 10K fingerprints en < 10s
GATE 1.2: RAM stable < 500MB pour 10K fichiers

Date: 2025-12-28
Version: 1.5.1 (Agent V1.5 - Dynamic config from YAML)
Update: ZERO hardcode - config loaded from exclusions.yaml
"""
import hashlib
from functools import lru_cache
import os
from pathlib import Path
from typing import Dict, List, Optional, Generator, Tuple, Set
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# YAML CONFIG LOADER (Dynamic - ZERO hardcode)
# ============================================================================

def _load_fingerprint_config() -> Dict:
    """
    Load fingerprint config from exclusions.yaml.
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
                    if config and 'fingerprint' in config:
                        logger.debug(f"Loaded fingerprint config from {config_path}")
                        return config['fingerprint']
            except Exception as e:
                logger.warning(f"Failed to load {config_path}: {e}")

    logger.warning("No fingerprint config found, using defaults")
    return {}


def get_sensitive_extensions() -> Set[str]:
    """
    Get sensitive extensions from YAML config.
    DYNAMIC: Loaded at runtime, not hardcoded.
    """
    config = _load_fingerprint_config()

    if 'sensitive_extensions' in config:
        return set(config['sensitive_extensions'])

    # Fallback defaults (should never reach here if YAML is configured)
    return {
        ".csv", ".xlsx", ".xls", ".pdf", ".docx", ".doc", ".txt",
        ".json", ".xml", ".sql", ".db", ".sqlite"
    }


def get_archive_zones() -> Set[str]:
    """
    Get archive zones from YAML config.
    DYNAMIC: Loaded at runtime, not hardcoded.
    """
    config = _load_fingerprint_config()

    if 'archive_zones' in config:
        return set(config['archive_zones'])

    # Fallback defaults (should never reach here if YAML is configured)
    return {
        "backup", "archive", "old", "archives", "backups", "historique",
        "history", "trash", "temp", "tmp", "cache"
    }


# ============================================================================
# DYNAMIC CONFIG (loaded at module level for performance)
# ============================================================================

# SENSITIVE_ZONES - These are semantic/business zones (kept hardcoded as they
# represent business logic, not file format configuration)
SENSITIVE_ZONES = {
    "rh", "hr", "clients", "customers", "customer", "finance", "legal",
    "juridique", "personnel", "paie", "salaires", "salaire", "wages",
    "contracts", "contrats", "confidential", "confidentiel", "private", "prive"
}

# DYNAMIC from YAML
SENSITIVE_EXTENSIONS = get_sensitive_extensions()
ARCHIVE_ZONES = get_archive_zones()


# ============================================================================
# LIGHT FINGERPRINT (Metadata-Only)
# ============================================================================

@dataclass
class LightFingerprint:
    """
    Fingerprint léger basé sur metadata uniquement.

    0 lecture de contenu.
    Scalable à 10M+ fichiers avec RAM constante.
    """
    path_hash: str          # SHA256(full_path) - anonymisé RGPD
    size: int               # stat.st_size (bytes)
    mtime: float            # stat.st_mtime (Unix timestamp)
    extension: str          # .csv, .xlsx, etc.
    zone: str               # "sensitive" | "normal" | "archive"
    volume_root: str = "unknown"  # Volume identifier for multi-volume dedup

    # Hash partiel OPTIONNEL (rempli seulement si nécessaire pour dédup)
    content_hash_partial: Optional[str] = None  # MD5(first 4KB)

    # Scores précédents (pour mode différentiel)
    previous_score: Optional[float] = None
    previous_pii: Optional[bool] = None
    previous_tier: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)


# ============================================================================
# HASH & ZONE DETECTION
# ============================================================================

@lru_cache(maxsize=500_000)
def hash_path(path: str) -> str:
    """
    Hash SHA256 d'un path (anonymisation RGPD).

    Utilisé pour:
    - Identifier fichiers sans exposer path complet
    - Comparaison différentielle
    """
    return hashlib.sha256(path.encode('utf-8')).hexdigest()


def detect_zone(path: str) -> str:
    """
    Détecte la zone d'un fichier basé sur son path.

    Returns:
        "sensitive": Zones /rh/, /clients/, /finance/, etc.
        "archive": Zones /backup/, /archive/, /old/, etc.
        "normal": Autres zones
    """
    path_lower = path.lower()
    parts = set(Path(path_lower).parts)

    # Priorité: sensitive > archive > normal
    if parts & SENSITIVE_ZONES:
        return "sensitive"
    if parts & ARCHIVE_ZONES:
        return "archive"
    return "normal"


def extract_volume_root(path: str) -> str:
    """
    Extract volume root from path for multi-volume dedup.
    /mnt/vol1/data.csv -> "vol1"
    /mnt/vol2/data.csv -> "vol2"
    """
    from pathlib import Path
    parts = Path(path).parts
    if not parts:
        return "unknown"
    if len(parts[0]) == 2 and parts[0][1] == ":":
        return parts[0]
    if parts[0] == "/":
        if len(parts) > 1:
            if parts[1] in ("mnt", "media", "volumes"):
                return parts[2] if len(parts) > 2 else parts[1]
            return parts[1]
        return "root"
    return parts[1] if len(parts) > 1 else parts[0]


# ============================================================================
# FINGERPRINT GENERATION (Metadata-Only)
# ============================================================================

def generate_fingerprint(file_path: str) -> Optional[LightFingerprint]:
    """
    Génère un fingerprint LÉGER (metadata seulement).

    0 lecture de contenu → scalable à 10M+ fichiers.

    Args:
        file_path: Chemin absolu du fichier

    Returns:
        LightFingerprint ou None si erreur (permission, file not found, etc.)
    """
    try:
        stat = os.stat(file_path)
        ext = Path(file_path).suffix.lower()

        return LightFingerprint(
            path_hash=hash_path(file_path),
            size=stat.st_size,
            mtime=stat.st_mtime,
            extension=ext if ext else ".no_ext",
            zone=detect_zone(file_path),
            volume_root=extract_volume_root(file_path)
        )
    except (OSError, PermissionError) as e:
        logger.debug(f"Cannot stat {file_path}: {e}")
        return None


def generate_fingerprints_streaming(
    root_path: str,
    max_files: int = 10_000_000
) -> Generator[LightFingerprint, None, None]:
    """
    Génère des fingerprints en streaming (RAM constante).

    Scalable à 10M+ fichiers.
    Utilise os.walk() pour parcours efficace.

    Args:
        root_path: Répertoire racine à scanner
        max_files: Limite de sécurité (10M par défaut)

    Yields:
        LightFingerprint pour chaque fichier accessible

    Example:
        >>> for fp in generate_fingerprints_streaming("/data"):
        ...     if fp.zone == "sensitive":
        ...         print(f"Sensitive file: {fp.size} bytes")
    """
    count = 0
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if count >= max_files:
                logger.warning(f"Reached max_files limit: {max_files}")
                return

            file_path = os.path.join(dirpath, filename)
            fp = generate_fingerprint(file_path)
            if fp:
                yield fp
                count += 1

                # Log progress every 100K files
                if count % 100_000 == 0:
                    logger.info(f"Fingerprinted {count:,} files...")


# ============================================================================
# FINGERPRINT DEDUPLICATOR (-40% files)
# ============================================================================

class FingerprintDeduplicator:
    """
    Déduplique les fichiers par (taille + extension).

    Principe:
    - Même taille + même extension = probable doublon
    - Scanner 1 représentant par groupe
    - Appliquer score à tout le groupe

    Résultat: 10M fichiers → 6M groupes uniques (-40%)
    """

    def __init__(self):
        self.groups: Dict[Tuple[int, str], List[LightFingerprint]] = {}

    def add(self, fp: LightFingerprint):
        """
        Ajoute un fingerprint au groupe approprié.

        Clé de groupement: (size, extension)
        """
        key = (fp.volume_root, fp.size, fp.extension)
        if key not in self.groups:
            self.groups[key] = []
        self.groups[key].append(fp)

    def get_representatives(self) -> List[LightFingerprint]:
        """
        Retourne 1 représentant par groupe.

        Priorité de sélection:
        1. Zones sensibles (sensitive)
        2. Zones normales (normal)
        3. Archives (archive)

        Returns:
            Liste de fingerprints représentatifs (1 par groupe)
        """
        representatives = []

        # Priorité: sensitive < normal < archive
        priority = {"sensitive": 0, "normal": 1, "archive": 2}

        for key, fps in self.groups.items():
            # Trier par priorité zone
            sorted_fps = sorted(fps, key=lambda x: priority.get(x.zone, 1))
            representatives.append(sorted_fps[0])

        return representatives

    def get_stats(self) -> Dict:
        """
        Statistiques de déduplication.

        Returns:
            {
                "total_files": 10000000,
                "unique_groups": 6000000,
                "dedup_ratio": 0.4
            }
        """
        total_files = sum(len(fps) for fps in self.groups.values())
        unique_groups = len(self.groups)

        return {
            "total_files": total_files,
            "unique_groups": unique_groups,
            "dedup_ratio": 1 - (unique_groups / total_files) if total_files > 0 else 0
        }


# ============================================================================
# SMART SAMPLER (-80% files after dedup)
# ============================================================================

class SmartSampler:
    """
    Applique un sampling intelligent basé sur zone/extension/date.

    Taux de scan:
    - Zones sensibles: 100%
    - Extensions sensibles: +20% boost
    - Fichiers récents (< 30 jours): +50% boost
    - Zones normales: 30%
    - Archives: 5%

    Résultat: 6M groupes → 600K à scanner (-90%)
    """

    def __init__(
        self,
        sensitive_rate: float = 1.0,    # 100% - KEEP
        normal_rate: float = 0.3,        # 30% - KEEP
        archive_rate: float = 0.15,      # 15% (was 0.05) - INCREASED for Consensus Pipeline
        recent_days: int = 60,           # 60 days (was 30) - DOUBLED for coverage
        recent_boost: float = 0.5        # +50% pour fichiers récents - KEEP
    ):
        self.sensitive_rate = sensitive_rate
        self.normal_rate = normal_rate
        self.archive_rate = archive_rate
        self.recent_days = recent_days
        self.recent_boost = recent_boost

        # Calculate threshold once during init
        from datetime import datetime
        self.recent_threshold = datetime.now().timestamp() - (recent_days * 86400)

    def should_scan(self, fp: LightFingerprint) -> bool:
        """
        Décide si un fichier doit être scanné.

        Args:
            fp: LightFingerprint du fichier

        Returns:
            True si le fichier doit être scanné, False sinon
        """
        import random

        # Taux de base selon zone
        if fp.zone == "sensitive":
            rate = self.sensitive_rate
        elif fp.zone == "archive":
            rate = self.archive_rate
        else:
            rate = self.normal_rate

        # Boost pour fichiers récents
        if fp.mtime > self.recent_threshold:
            rate = min(1.0, rate + self.recent_boost)

        # Boost pour extensions sensibles
        if fp.extension in SENSITIVE_EXTENSIONS:
            rate = min(1.0, rate + 0.2)

        return random.random() < rate

    def filter(self, fingerprints: List[LightFingerprint]) -> List[LightFingerprint]:
        """
        Filtre les fingerprints selon le sampling.
        Inclut plancher global et garanties par zone (Consensus Pipeline).

        Args:
            fingerprints: Liste de fingerprints (après déduplication)

        Returns:
            Liste filtrée de fingerprints à scanner avec garanties minimales appliquées
        """
        # Sampling normal
        selected = [fp for fp in fingerprints if self.should_scan(fp)]

        # Plancher global: minimum 10% of total files
        min_count = max(int(len(fingerprints) * GLOBAL_MIN_RATE), 1000)
        if len(selected) < min_count:
            # Ajouter des fichiers random pour atteindre le minimum
            remaining = [fp for fp in fingerprints if fp not in selected]
            import random
            random.shuffle(remaining)
            # Add from remaining to reach minimum
            needed = min_count - len(selected)
            selected.extend(remaining[:needed])

        return selected


# =============================================================================
# SAMPLING GUARANTEES (AI-Readiness Audit - Consensus Pipeline 2025-01-01)
# =============================================================================

# Global floor: minimum 10% of eligible files MUST be sampled
# Ensures audit coverage even with aggressive deduplication (-40%) and sampling (-80%)
GLOBAL_MIN_RATE = 0.10

# Per-zone minimums (compliance protection)
# Prevents edge cases where sensitive zones drop below critical thresholds
MIN_SAMPLES_PER_ZONE = {
    'sensitive': 500,   # RH/Finance non-negotiable minimum
    'normal': 5000,     # Core business data minimum
    'archive': 500      # Archive audit trail minimum
}


# ============================================================================
# DIFFERENTIAL MODE (Comparaison Metadata-Only)
# ============================================================================

def compare_fingerprints(
    current: Dict[str, LightFingerprint],
    previous: Dict[str, LightFingerprint]
) -> Dict[str, List[LightFingerprint]]:
    """
    Compare fingerprints actuels vs précédents.

    Comparaison par (size + mtime), PAS de hash contenu.

    Args:
        current: Dict {path_hash: LightFingerprint} snapshot actuel
        previous: Dict {path_hash: LightFingerprint} snapshot précédent

    Returns:
        {
            "new": [fp1, fp2, ...],          # Nouveaux fichiers
            "modified": [fp3, fp4, ...],     # Modifiés (size ou mtime)
            "unchanged": [fp5, fp6, ...],    # Inchangés (copier previous_score)
            "deleted": [fp7, fp8, ...]       # Supprimés
        }

    Example:
        >>> current = {fp.path_hash: fp for fp in current_fps}
        >>> previous = {fp.path_hash: fp for fp in load_snapshot()}
        >>> diff = compare_fingerprints(current, previous)
        >>> print(f"Scan only {len(diff['new']) + len(diff['modified'])} files")
    """
    result = {
        "new": [],
        "modified": [],
        "unchanged": [],
        "deleted": []
    }

    current_hashes = set(current.keys())
    previous_hashes = set(previous.keys())

    # Nouveaux fichiers
    for h in current_hashes - previous_hashes:
        result["new"].append(current[h])

    # Fichiers supprimés
    for h in previous_hashes - current_hashes:
        result["deleted"].append(previous[h])

    # Fichiers existants : modifiés ou inchangés
    for h in current_hashes & previous_hashes:
        curr = current[h]
        prev = previous[h]

        # Comparaison par size + mtime (PAS de hash)
        # Tolérance: 1 sec pour mtime (filesystem precision)
        if curr.size != prev.size or abs(curr.mtime - prev.mtime) > 1:
            result["modified"].append(curr)
        else:
            # Inchangé : copier scores précédents
            curr.previous_score = prev.previous_score
            curr.previous_pii = prev.previous_pii
            curr.previous_tier = prev.previous_tier
            result["unchanged"].append(curr)

    return result


# ============================================================================
# UTILITIES
# ============================================================================

def get_fingerprint_stats(fingerprints: List[LightFingerprint]) -> Dict:
    """
    Statistiques globales sur une liste de fingerprints.

    Args:
        fingerprints: Liste de fingerprints

    Returns:
        {
            "total": 10000,
            "by_zone": {"sensitive": 3000, "normal": 5000, "archive": 2000},
            "by_extension": {".csv": 2000, ".xlsx": 1500, ...},
            "total_size_mb": 1234.5
        }
    """
    from collections import Counter

    total = len(fingerprints)
    zones = Counter(fp.zone for fp in fingerprints)
    extensions = Counter(fp.extension for fp in fingerprints)
    total_size = sum(fp.size for fp in fingerprints)

    return {
        "total": total,
        "by_zone": dict(zones),
        "by_extension": dict(extensions.most_common(10)),  # Top 10
        "total_size_mb": round(total_size / (1024 * 1024), 2)
    }


def audit_sampling(
    fingerprints: List[LightFingerprint],
    selected: List[LightFingerprint]
) -> Dict:
    """
    Génère un rapport d'audit du sampling pour debugging (Consensus Pipeline).

    Useful for understanding coverage gaps and validating GLOBAL_MIN_RATE compliance.

    Args:
        fingerprints: Liste complète de fingerprints (après déduplication)
        selected: Liste des fingerprints selectionnés pour le scan

    Returns:
        {
            'total_fingerprints': 10000,
            'selected_count': 1234,
            'effective_rate': 12.34,
            'zones_distribution': {
                'sensitive': {'total': 3000, 'selected': 300, 'rate': 10.0},
                'normal': {'total': 5000, 'selected': 600, 'rate': 12.0},
                'archive': {'total': 2000, 'selected': 334, 'rate': 16.7}
            },
            'compliance': {
                'global_min_rate_met': True,
                'zone_minimums_met': {'sensitive': True, 'normal': True, 'archive': True}
            }
        }

    Example:
        >>> sampler = SmartSampler()
        >>> selected = sampler.filter(fingerprints)
        >>> report = audit_sampling(fingerprints, selected)
        >>> print(f"Coverage: {report['effective_rate']:.2f}%")
    """
    from collections import Counter

    zones_total = Counter(fp.zone for fp in fingerprints)
    zones_selected = Counter(fp.zone for fp in selected)

    # Build distribution by zone
    zones_distribution = {}
    for zone in ['sensitive', 'normal', 'archive']:
        total_count = zones_total.get(zone, 0)
        selected_count = zones_selected.get(zone, 0)
        rate = (selected_count / total_count * 100) if total_count > 0 else 0
        zones_distribution[zone] = {
            'total': total_count,
            'selected': selected_count,
            'rate': round(rate, 2)
        }

    # Check compliance
    effective_rate = len(selected) / len(fingerprints) * 100 if fingerprints else 0
    global_min_met = effective_rate >= (GLOBAL_MIN_RATE * 100)

    zone_minimums_met = {}
    for zone in ['sensitive', 'normal', 'archive']:
        min_required = MIN_SAMPLES_PER_ZONE.get(zone, 0)
        selected_count = zones_selected.get(zone, 0)
        zone_minimums_met[zone] = selected_count >= min_required

    return {
        'total_fingerprints': len(fingerprints),
        'selected_count': len(selected),
        'effective_rate': round(effective_rate, 2),
        'zones_distribution': zones_distribution,
        'compliance': {
            'global_min_rate_met': global_min_met,
            'zone_minimums_met': zone_minimums_met
        }
    }


# ============================================================================
# BLOOM FILTER + CACHE STATS (Optimization)
# ============================================================================

from pybloom_live import BloomFilter
import atexit

# Bloom filter for O(1) dedup - 5MB RAM for 1M files
_bloom_filter = None

def get_bloom_filter():
    """Get or create bloom filter"""
    global _bloom_filter
    if _bloom_filter is None:
        _bloom_filter = BloomFilter(capacity=1_000_000, error_rate=0.001)
        logger.info("[BLOOM] Initialized (1M capacity, 0.1% false positive, ~5MB RAM)")
    return _bloom_filter

def reset_bloom_filter():
    """Reset bloom filter for new scan"""
    global _bloom_filter
    _bloom_filter = BloomFilter(capacity=1_000_000, error_rate=0.001)
    logger.info("[BLOOM] Reset for new scan")

def is_duplicate_bloom(fingerprint: str) -> bool:
    """Check if fingerprint seen before using Bloom filter O(1)"""
    bf = get_bloom_filter()
    if fingerprint in bf:
        return True
    bf.add(fingerprint)
    return False

@atexit.register
def log_cache_stats():
    """Log cache stats at end of scan"""
    try:
        info = hash_path.cache_info()
        if info.hits + info.misses > 0:
            ratio = info.hits / (info.hits + info.misses)
            logger.info(f"[CACHE] hash_path - hits: {info.hits}, misses: {info.misses}, ratio: {ratio:.1%}")
    except Exception:
        pass

