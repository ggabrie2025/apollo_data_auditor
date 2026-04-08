"""
Apollo Agent V1.4 - Database Scanner (Simplified)
Scan local databases and export JSON brut (NO SCORING - IP Protected).

Architecture IP Protection:
- Agent: Scan + PII detection basique + JSON brut
- Hub: Scoring engine (IP protégée) + Dashboard

Workflow:
1. Connect to database (PostgreSQL/MySQL/MongoDB)
2. Extract schema (tables, columns, types)
3. Extract stats (row counts, sizes)
4. Detect PII basique (regex on column names/data)
5. Export JSON brut
6. ❌ NO SCORING (done by Hub)
7. ❌ NO cloud snapshot

Date: 2025-12-13
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime

from .db_connectors import PostgreSQLConnector, MySQLConnector, MongoDBConnector, SQLServerConnector
from .pii_scanner import PII_PATTERNS, PII_VALIDATORS
from .db_snapshot import load_snapshot_from_hub, create_snapshot_data, get_source_id
from .db_differential import get_tables_to_scan, should_scan_table
from .db_sampler import DBSmartSampler  # V1.5: Zone-aware sampling

logger = logging.getLogger(__name__)

DatabaseType = Literal["postgresql", "mysql", "mongodb", "sqlserver"]


@dataclass
class DBScanConfig:
    """Configuration for database scan."""
    db_type: DatabaseType
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl: bool = False
    timeout: int = 60

    # Hub API (for cloud snapshot)
    hub_url: Optional[str] = None
    api_key: Optional[str] = None

    # PII detection
    enable_pii: bool = True
    sample_rows: int = 100  # Sample rows for PII detection

    # V1.5: Smart sampling (zone-aware)
    enable_smart_sampling: bool = True  # Apply DBSmartSampler
    min_sample: int = 1000  # Min rows for statistical validity
    max_sample: int = 100_000  # Max rows cap for huge tables


@dataclass
class TableMetadata:
    """Metadata for a single table/collection."""
    name: str
    schema: Optional[str] = None  # PostgreSQL/MySQL only
    row_count: int = 0
    columns: List[Dict[str, str]] = field(default_factory=list)  # [{name, type}]
    size_bytes: Optional[int] = None

    # PII detection results
    pii_detected: bool = False
    pii_types: List[str] = field(default_factory=list)
    pii_columns: List[str] = field(default_factory=list)

    # NEW: Structure metadata (Infrastructure scoring)
    primary_keys: List[str] = field(default_factory=list)
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)

    # NEW: Quality metrics (Quality scoring)
    null_percentage: Dict[str, float] = field(default_factory=dict)
    duplicate_count: int = 0
    completeness_score: float = 0.0

    # NEW: V1.4 Enhanced metrics (4 nouveaux champs)
    last_updated: Optional[str] = None  # TIMESTAMP ISO 8601 (NULL si indisponible)
    orphan_rows: Optional[int] = None   # Nombre FK orphelines (NULL si pas de FK)
    idx_scan_count: Optional[int] = None  # Stats query indexes (NULL si indisponible)
    invalid_type_count: Optional[int] = None  # Valeurs invalides (NULL si non calculé)

    # V1.5: Smart sampling metadata
    zone: Optional[str] = None  # SENSITIVE | NORMAL | ARCHIVE
    sample_rate: Optional[float] = None  # 1.0 | 0.30 | 0.05
    sample_size: Optional[int] = None  # Actual rows sampled

    # V1.7: Audit datapath gaps
    schema_doc: bool = False            # Table has pg_description comment
    has_audit_columns: bool = False     # Table has created_at/updated_at/deleted_at

    # V1.8: Permissions & Encryption (DB equivalent of files migration 027/028)
    encrypted: bool = False             # TDE or column-level encryption detected
    grants: List[Dict[str, Any]] = field(default_factory=list)  # Role permissions

    # Sprint 86B Niveau 2: PG stats (PostgreSQL only, NULL for other DBs)
    n_dead_tup: Optional[int] = None     # Dead tuples (bloat indicator)
    n_live_tup: Optional[int] = None     # Live tuples (row estimate)
    seq_scan_count: Optional[int] = None # Sequential scans (missing index indicator)
    last_vacuum: Optional[str] = None    # Last vacuum timestamp ISO 8601


@dataclass
class DBScanResult:
    """Result of database scan (JSON brut)."""

    # Connection info (REQUIRED - no defaults)
    db_type: str
    host: str
    database: str

    # Scan metadata (REQUIRED - no defaults)
    scan_id: str
    scan_timestamp: str

    # Source type (REQUIRED by Hub V1.4.1)
    source_type: str = "databases"
    agent_version: str = "1.4.0"

    # Schema extraction
    tables_count: int = 0
    total_rows: int = 0
    total_size_bytes: Optional[int] = None

    # Tables metadata
    tables: List[TableMetadata] = field(default_factory=list)

    # PII summary
    tables_with_pii: int = 0
    pii_types_found: List[str] = field(default_factory=list)

    # Differential stats
    differential_mode: bool = False
    tables_scanned: int = 0  # Actually scanned (new + modified)
    tables_skipped: int = 0  # Skipped (unchanged)
    reduction_percent: float = 0.0

    # Snapshot for Hub
    snapshot: Optional[Dict[str, Any]] = None

    # Timing
    duration_seconds: float = 0.0

    # Governance metrics (Sprint 18 - PostgreSQL, MongoDB, MySQL)
    governance_metrics: Optional[Dict[str, float]] = None

    # Lineage metadata (Sprint 21)
    views: List[Dict[str, Any]] = field(default_factory=list)
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    procedures: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    status: str = "success"  # success, partial, error
    error: Optional[str] = None


class DBScanner:
    """
    Database scanner for Agent V1.5.

    V1.5 Features:
    - Smart sampling (DBSmartSampler): Zone-aware sampling (SENSITIVE 100%, NORMAL 30%, ARCHIVE 5%)
    - Differential + Snapshot: Carryover flow for unchanged tables (Hub reuses scores)
    - IP Protection: NO SCORING in agent (Hub only)
    """

    def __init__(self, config: DBScanConfig):
        self.config = config
        self.connector = None
        self.pii_patterns = PII_PATTERNS if config.enable_pii else None

        # V1.5: Initialize DBSmartSampler
        self.smart_sampler = None
        if config.enable_smart_sampling:
            self.smart_sampler = DBSmartSampler(
                min_sample=config.min_sample,
                max_sample=config.max_sample
            )

    async def scan(self) -> DBScanResult:
        """
        Scan database and return JSON brut.

        Workflow:
        1. GET snapshot from Hub (if configured)
        2. Connect to database
        3. Extract schema + stats
        4. Differential (compare with snapshot)
        5. Detect PII (only new/modified tables)
        6. Create new snapshot for Hub
        7. Return JSON brut (NO SCORING)
        """
        start_time = datetime.now()
        scan_id = str(uuid.uuid4())  # Generate valid UUID for Hub compatibility

        result = DBScanResult(
            db_type=self.config.db_type,
            host=self.config.host,
            database=self.config.database,
            scan_id=scan_id,
            scan_timestamp=start_time.isoformat(),
        )

        try:
            # Step 1: Load snapshot from Hub (if configured)
            previous_snapshot = None
            if self.config.hub_url and self.config.api_key:
                source_id = get_source_id(self.config.db_type, self.config.host, self.config.database)
                logger.info(f"[DB-Scanner] Loading snapshot from Hub (source_id: {source_id})...")
                previous_snapshot = load_snapshot_from_hub(
                    self.config.hub_url,
                    self.config.api_key,
                    source_id
                )
                if previous_snapshot:
                    logger.info(f"[DB-Scanner] ✅ Snapshot loaded: {previous_snapshot.get('tables_count', 0)} tables")
                else:
                    logger.info(f"[DB-Scanner] No previous snapshot (first scan)")

            # Step 2: Connect
            logger.info(f"[DB-Scanner] Connecting to {self.config.db_type}://{self.config.host}/{self.config.database}")
            await self._connect()

            # Step 3: Extract schema + stats
            logger.info(f"[DB-Scanner] Extracting schema...")
            tables, schemas = await self._extract_schema()
            result.tables = tables
            result.tables_count = len(tables)
            result.total_rows = sum(t.row_count for t in tables)
            size_values = [t.size_bytes for t in tables if t.size_bytes is not None]
            result.total_size_bytes = sum(size_values) if size_values else None
            result.tables_scanned = len(tables)  # Default: full scan (overridden below if differential)

            # Step 4: Differential (if snapshot exists)
            diff_result = None
            if previous_snapshot:
                logger.info(f"[DB-Scanner] Running differential analysis...")
                diff_result = get_tables_to_scan(tables, previous_snapshot)
                result.differential_mode = True
                result.tables_scanned = diff_result.tables_to_scan
                result.tables_skipped = len(diff_result.unchanged_tables)
                result.reduction_percent = diff_result.reduction_percent

                logger.info(
                    f"[DB-Scanner] Differential: {diff_result.new_tables.__len__()} new, "
                    f"{diff_result.modified_tables.__len__()} modified, "
                    f"{diff_result.unchanged_tables.__len__()} unchanged "
                    f"({diff_result.reduction_percent:.1f}% reduction)"
                )

            # Step 5: Detect PII (only new/modified if differential)
            if self.config.enable_pii:
                tables_to_scan = tables
                if diff_result:
                    # Only scan new/modified tables
                    tables_to_scan = [
                        t for t in tables
                        if should_scan_table(t.name, diff_result)
                    ]

                logger.info(f"[DB-Scanner] Detecting PII in {len(tables_to_scan)} tables...")
                await self._detect_pii(tables_to_scan)

                # Summary
                tables_with_pii = [t for t in tables if t.pii_detected]
                result.tables_with_pii = len(tables_with_pii)

                all_pii_types = set()
                for t in tables_with_pii:
                    all_pii_types.update(t.pii_types)
                result.pii_types_found = sorted(list(all_pii_types))

            # Step 6: Create snapshot for Hub
            if self.config.hub_url:
                logger.info(f"[DB-Scanner] Creating snapshot for Hub...")
                result.snapshot = create_snapshot_data(
                    self.config.db_type,
                    self.config.host,
                    self.config.database,
                    tables
                )

            # Step 7: Collect governance metrics (PostgreSQL + MySQL)
            if hasattr(self.connector, 'get_governance_metrics'):
                try:
                    logger.info(f"[DB-Scanner] Collecting governance metrics...")
                    result.governance_metrics = await self.connector.get_governance_metrics()
                    logger.info(f"[DB-Scanner] ✅ Governance metrics collected: {result.governance_metrics}")
                except Exception as e:
                    logger.warning(f"[DB-Scanner] Failed to collect governance metrics: {e}")
                    result.governance_metrics = None

            # Step 8: Collect lineage metadata (Sprint 21)
            if self.config.db_type in ["postgresql", "mysql", "sqlserver"]:
                await self._collect_lineage(result, schemas)

            result.status = "success"

        except Exception as e:
            logger.error(f"[DB-Scanner] Scan failed: {e}")
            result.status = "error"
            result.error = str(e)

        finally:
            # Close connection
            if self.connector:
                await self._close()

        # Duration
        end_time = datetime.now()
        result.duration_seconds = (end_time - start_time).total_seconds()

        logger.info(
            f"[DB-Scanner] Scan complete: {result.tables_count} tables, "
            f"{result.tables_with_pii} with PII, "
            f"{result.tables_scanned} scanned, "
            f"{result.tables_skipped} skipped"
        )

        return result

    async def _connect(self):
        """Connect to database."""
        db_config = {
            "type": self.config.db_type,
            "host": self.config.host,
            "port": self.config.port,
            "database": self.config.database,
            "username": self.config.username,
            "password": self.config.password,
            "ssl": self.config.ssl,
            "timeout": self.config.timeout,
        }

        if self.config.db_type == "postgresql":
            self.connector = PostgreSQLConnector(db_config)
        elif self.config.db_type == "mysql":
            self.connector = MySQLConnector(db_config)
        elif self.config.db_type == "mongodb":
            self.connector = MongoDBConnector(db_config)
        elif self.config.db_type == "sqlserver":
            self.connector = SQLServerConnector(db_config)
        else:
            raise ValueError(f"Unsupported database type: {self.config.db_type}")

        # Test connection
        test_result = await self.connector.test_connection()
        if not test_result.get("success"):
            raise Exception(f"Connection failed: {test_result.get('error')}")

    async def _extract_schema(self) -> tuple:
        """Extract schema + stats from database.

        Returns:
            tuple: (tables_list, schemas_list)
        """
        tables = []
        schemas_found = []

        if self.config.db_type in ["postgresql", "mysql", "sqlserver"]:
            # SQL databases
            schemas = await self.connector.get_schemas()
            schemas_found = schemas.copy()

            for schema in schemas:
                # Skip system schemas
                if schema in ['information_schema', 'pg_catalog', 'pg_toast', 'sys', 'mysql', 'performance_schema']:
                    continue

                schema_tables = await self.connector.get_tables(schema)

                for table_name in schema_tables:
                    # Get columns
                    columns = await self.connector.get_columns(schema, table_name)
                    columns_list = [{"name": col["name"], "type": col["type"]} for col in columns]

                    # Get row count via SQL
                    row_count = await self._get_row_count(schema, table_name)

                    # NEW: Enrichment (using existing connector methods)
                    primary_keys = await self.connector.get_primary_keys(schema, table_name)

                    # Foreign keys: adapt format (connector → schema expected)
                    fks_raw = await self.connector.get_foreign_keys(schema, table_name)
                    foreign_keys = [
                        {
                            "column": fk["column"],
                            "ref_table": fk["referenced_table"],
                            "ref_column": fk["referenced_column"]
                        }
                        for fk in fks_raw
                    ]

                    indexes = await self.connector.get_indexes(schema, table_name)

                    # Sprint 86B Niveau 2: Real quality metrics (replace stubs)
                    quality = await self._compute_quality_metrics(
                        schema, table_name, columns_list, row_count
                    )

                    # NEW V1.4: Enhanced metrics (4 nouveaux champs)
                    last_updated = await self.connector.get_last_updated(schema, table_name)
                    orphan_rows = await self.connector.get_orphan_count(schema, table_name, fks_raw)
                    idx_scan_count = await self.connector.get_index_stats(schema, table_name)
                    invalid_type_count = await self.connector.get_type_validity(schema, table_name, columns, row_count)

                    # V1.7: Per-table documentation check
                    schema_doc = False
                    if self.config.db_type == "postgresql" and hasattr(self.connector, 'has_table_documentation'):
                        schema_doc = await self.connector.has_table_documentation(schema, table_name)

                    # V1.8: Encryption and permissions (DB equivalent of files migration 027/028)
                    encrypted = False
                    grants = []
                    if self.config.db_type == "postgresql":
                        if hasattr(self.connector, 'get_table_encrypted'):
                            encrypted = await self.connector.get_table_encrypted(schema, table_name)
                        if hasattr(self.connector, 'get_table_grants'):
                            grants = await self.connector.get_table_grants(schema, table_name)

                    # Sprint 86B Niveau 2: Get table size in bytes
                    size_bytes = None
                    if hasattr(self.connector, 'get_table_size'):
                        size_bytes = await self.connector.get_table_size(schema, table_name)

                    table_meta = TableMetadata(
                        name=table_name,
                        schema=schema,
                        row_count=row_count,
                        columns=columns_list,
                        size_bytes=size_bytes,
                    )

                    # V1.7: Audit datapath fields
                    table_meta.schema_doc = schema_doc

                    # V1.7: Audit columns detection (zero additional query)
                    AUDIT_COLUMN_PATTERNS = {
                        'created_at', 'updated_at', 'deleted_at',
                        'created_date', 'updated_date', 'deleted_date',
                        'creation_date', 'modification_date',
                        'date_created', 'date_modified', 'date_deleted',
                        'insert_timestamp', 'update_timestamp',
                    }
                    column_names_lower = {col["name"].lower() for col in columns_list}
                    has_create = bool(column_names_lower & {'created_at', 'created_date', 'creation_date', 'date_created', 'insert_timestamp'})
                    has_update = bool(column_names_lower & {'updated_at', 'updated_date', 'modification_date', 'date_modified', 'update_timestamp'})
                    has_delete = bool(column_names_lower & {'deleted_at', 'deleted_date', 'date_deleted'})
                    table_meta.has_audit_columns = sum([has_create, has_update, has_delete]) >= 2

                    # Attach enriched metadata to table_meta
                    table_meta.primary_keys = primary_keys
                    table_meta.foreign_keys = foreign_keys
                    table_meta.indexes = indexes
                    table_meta.null_percentage = quality["null_percentage"]
                    table_meta.duplicate_count = quality["duplicate_count"]
                    table_meta.completeness_score = quality["completeness_score"]

                    # V1.5: Apply smart sampling (zone-aware)
                    if self.smart_sampler and row_count > 0:
                        sample_size, zone, rate = self.smart_sampler.get_sample_info(
                            table_name, schema, row_count
                        )
                        table_meta.zone = zone
                        table_meta.sample_rate = rate
                        table_meta.sample_size = sample_size

                    # Attach V1.4 enhanced metrics
                    table_meta.last_updated = last_updated
                    table_meta.orphan_rows = orphan_rows
                    table_meta.idx_scan_count = idx_scan_count
                    table_meta.invalid_type_count = invalid_type_count

                    # Attach V1.8: Encryption and permissions
                    table_meta.encrypted = encrypted
                    table_meta.grants = grants

                    # Sprint 86B Niveau 2: PG stats (PostgreSQL only)
                    if self.config.db_type == "postgresql" and hasattr(self.connector, 'get_pg_table_stats'):
                        pg_stats = await self.connector.get_pg_table_stats(schema, table_name)
                        table_meta.n_dead_tup = pg_stats.get('n_dead_tup')
                        table_meta.n_live_tup = pg_stats.get('n_live_tup')
                        table_meta.seq_scan_count = pg_stats.get('seq_scan_count')
                        table_meta.last_vacuum = pg_stats.get('last_vacuum')

                    tables.append(table_meta)

        elif self.config.db_type == "mongodb":
            # MongoDB collections - use get_tables() method (not execute_query)
            database_name = self.config.database
            collections = await self.connector.get_tables(database_name)

            for collection_name in collections:
                # Get document count via SQL-style query
                try:
                    count_result = await self.connector.execute_query(
                        f"SELECT COUNT(*) as count FROM {database_name}.{collection_name}"
                    )
                    doc_count = count_result[0].get("count", 0) if count_result else 0
                except Exception:
                    doc_count = 0

                # Get columns from connector's schema inference
                columns_info = await self.connector.get_columns(database_name, collection_name)
                columns_list = [{"name": col["name"], "type": col["type"]} for col in columns_info]

                # Sprint 86B Niveau 2: Get collection size in bytes
                coll_size = None
                if hasattr(self.connector, 'get_table_size'):
                    coll_size = await self.connector.get_table_size(database_name, collection_name)

                table_meta = TableMetadata(
                    name=collection_name,
                    schema=database_name,
                    row_count=doc_count,
                    columns=columns_list,
                    size_bytes=coll_size,
                )

                # KI-118: quality metrics (mirrors SQL branch lines 409-469)
                quality = await self._compute_quality_metrics(
                    database_name, collection_name, columns_list, doc_count
                )
                table_meta.null_percentage = quality["null_percentage"]
                table_meta.duplicate_count = quality["duplicate_count"]
                table_meta.completeness_score = quality["completeness_score"]

                # KI-118: smart sampling zone (mirrors SQL branch lines 472-478)
                if self.smart_sampler and doc_count > 0:
                    sample_size, zone, rate = self.smart_sampler.get_sample_info(
                        collection_name, database_name, doc_count
                    )
                    table_meta.zone = zone
                    table_meta.sample_rate = rate
                    table_meta.sample_size = sample_size

                tables.append(table_meta)

        return tables, schemas_found

    async def _compute_quality_metrics(
        self, schema: str, table: str, columns: List[Dict], row_count: int
    ) -> Dict[str, Any]:
        """
        Compute real quality metrics (replace hardcoded stubs).

        Sprint 86B Niveau 2:
        - null_percentage: per-column null % (PG: pg_stats free, others: COUNT query)
        - completeness_score: 100 - avg(null percentages)
        - duplicate_count: 0 (full-table dedup too expensive for production)

        Returns:
            Dict with null_percentage, duplicate_count, completeness_score
        """
        defaults = {"null_percentage": {}, "duplicate_count": 0, "completeness_score": 100.0}

        if row_count == 0 or not columns:
            return defaults

        null_pcts = {}

        # PostgreSQL: use pg_stats (zero cost, pre-computed by ANALYZE)
        if self.config.db_type == "postgresql" and hasattr(self.connector, 'get_null_fractions'):
            null_pcts = await self.connector.get_null_fractions(schema, table)

        # MySQL / SQL Server: COUNT-based query (only for tables < 100K rows)
        elif self.config.db_type in ("mysql", "sqlserver") and row_count <= 100_000:
            try:
                col_names = [c['name'] for c in columns[:30]]  # Cap at 30 columns

                if self.config.db_type == "mysql":
                    q = lambda s: f'`{s}`'
                else:
                    q = lambda s: f'[{s}]'

                count_parts = ", ".join(
                    f'COUNT({q(c)}) as c{i}' for i, c in enumerate(col_names)
                )
                query = f'SELECT COUNT(*) as total, {count_parts} FROM {q(schema)}.{q(table)}'

                result = await self.connector.execute_query(query)
                if result:
                    row = result[0]
                    total = row.get('total', 0)
                    if total > 0:
                        for i, c in enumerate(col_names):
                            non_null = row.get(f'c{i}', total)
                            null_pct = round((1 - non_null / total) * 100, 2)
                            if null_pct > 0:
                                null_pcts[c] = null_pct
            except Exception as e:
                logger.warning(f"[DB-Scanner] Quality metrics query failed for {schema}.{table}: {e}")

        # MongoDB: aggregate-based null count (only for collections < 100K documents)
        elif self.config.db_type == "mongodb" and row_count <= 100_000:
            try:
                col_names = [c['name'] for c in columns[:30]]  # Cap at 30 fields
                db_conn = self.connector.connection[schema]
                collection = db_conn[table]
                group_fields = {
                    f"c{i}": {"$sum": {"$cond": [{"$ifNull": [f"${c}", False]}, 0, 1]}}
                    for i, c in enumerate(col_names)
                }
                group_fields["total"] = {"$sum": 1}
                pipeline = [{"$group": {"_id": None, **group_fields}}]
                cursor = collection.aggregate(pipeline)
                results = await cursor.to_list(length=1)
                if results:
                    row = results[0]
                    total = row.get("total", 0)
                    if total > 0:
                        for i, c in enumerate(col_names):
                            non_null = row.get(f"c{i}", total)
                            null_pct = round((1 - non_null / total) * 100, 2)
                            if null_pct > 0:
                                null_pcts[c] = null_pct
            except Exception as e:
                logger.warning(f"[DB-Scanner] MongoDB quality metrics failed for {schema}.{table}: {e}")

        # Compute completeness score from null percentages
        if null_pcts:
            total_cols = len(columns)
            avg_null = sum(null_pcts.values()) / total_cols
            completeness = round(100 - avg_null, 2)
        else:
            completeness = 100.0

        return {
            "null_percentage": null_pcts,
            "duplicate_count": 0,
            "completeness_score": completeness
        }

    async def _get_row_count(self, schema: str, table: str) -> int:
        """Get row count for a table."""
        try:
            # MySQL uses backticks, PostgreSQL uses double quotes, SQL Server uses brackets
            if self.config.db_type == "mysql":
                query = f'SELECT COUNT(*) as count FROM `{schema}`.`{table}`'
            elif self.config.db_type == "sqlserver":
                query = f'SELECT COUNT(*) as count FROM [{schema}].[{table}]'
            else:
                query = f'SELECT COUNT(*) as count FROM "{schema}"."{table}"'
            result = await self.connector.execute_query(query)
            if result and len(result) > 0:
                return result[0].get("count", 0)
        except Exception as e:
            logger.warning(f"[DB-Scanner] Failed to get row count for {schema}.{table}: {e}")
        return 0

    async def _detect_pii(self, tables: List[TableMetadata]):
        """Detect PII basique in tables (column names + sample data)."""
        for table in tables:
            pii_types = set()
            pii_columns = []

            # 1. Check column names for PII patterns
            for col in table.columns:
                col_name_lower = col["name"].lower()

                # Common PII column names
                if any(pattern in col_name_lower for pattern in ["email", "mail"]):
                    pii_types.add("email")
                    pii_columns.append(col["name"])
                elif any(pattern in col_name_lower for pattern in ["phone", "tel", "mobile"]):
                    pii_types.add("phone")
                    pii_columns.append(col["name"])
                elif any(pattern in col_name_lower for pattern in ["ssn", "social", "secu"]):
                    pii_types.add("ssn")
                    pii_columns.append(col["name"])
                elif any(pattern in col_name_lower for pattern in ["iban", "account", "card"]):
                    pii_types.add("iban")
                    pii_columns.append(col["name"])
                elif any(pattern in col_name_lower for pattern in ["address", "street", "city"]):
                    pii_types.add("address")
                    pii_columns.append(col["name"])

            # 2. Sample data scanning (if configured)
            if self.config.sample_rows > 0 and self.pii_patterns:
                sample_data = await self._get_sample_data(table)

                for row in sample_data:
                    for col_name, value in row.items():
                        if isinstance(value, str):
                            # Use PII regex patterns (same as FILES)
                            for pii_type, pattern in self.pii_patterns.items():
                                if pattern.search(value):
                                    validator = PII_VALIDATORS.get(pii_type)
                                    if validator is not None and not validator(value):
                                        continue
                                    pii_types.add(pii_type)
                                    if col_name not in pii_columns:
                                        pii_columns.append(col_name)
                                    break  # One type per cell value (KI-103)

            # Update table metadata
            if pii_types:
                table.pii_detected = True
                table.pii_types = sorted(list(pii_types))
                table.pii_columns = pii_columns

    async def _get_sample_data(self, table: TableMetadata) -> List[Dict[str, Any]]:
        """Get sample rows from table for PII detection."""
        try:
            if self.config.db_type == "mysql":
                query = f'SELECT * FROM `{table.schema}`.`{table.name}` LIMIT {self.config.sample_rows}'
                rows = await self.connector.execute_query(query)
                return rows or []
            elif self.config.db_type == "postgresql":
                query = f'SELECT * FROM "{table.schema}"."{table.name}" LIMIT {self.config.sample_rows}'
                rows = await self.connector.execute_query(query)
                return rows or []
            elif self.config.db_type == "sqlserver":
                # SQL Server uses TOP instead of LIMIT
                query = f'SELECT TOP {self.config.sample_rows} * FROM [{table.schema}].[{table.name}]'
                rows = await self.connector.execute_query(query)
                return rows or []
            elif self.config.db_type == "mongodb":
                query = f"db.{table.name}.find().limit({self.config.sample_rows})"
                docs = await self.connector.execute_query(query)
                return docs or []
        except Exception as e:
            logger.warning(f"[DB-Scanner] Failed to sample {table.name}: {e}")
            return []

    async def _close(self):
        """Close database connection."""
        if self.connector:
            try:
                await self.connector.close()
            except Exception as e:
                logger.warning(f"[DB-Scanner] Close connection warning: {e}")

    async def _collect_lineage(self, result: DBScanResult, schemas: List[str]):
        """
        Collect lineage metadata (views, triggers, procedures) from database.
        Sprint 21 Data Lineage feature.

        Args:
            result: DBScanResult to populate
            schemas: List of schema names to query
        """
        logger.info(f"[DB-Scanner] Collecting lineage metadata (Sprint 21)...")

        all_views = []
        all_triggers = []
        all_procedures = []

        for schema in schemas:
            # Skip system schemas
            if schema in ['information_schema', 'pg_catalog', 'pg_toast', 'sys', 'mysql', 'performance_schema']:
                continue

            try:
                # Collect views
                if hasattr(self.connector, 'get_views'):
                    views = await self.connector.get_views(schema)
                    all_views.extend(views)

                # Collect triggers
                if hasattr(self.connector, 'get_triggers'):
                    triggers = await self.connector.get_triggers(schema)
                    all_triggers.extend(triggers)

                # Collect functions/procedures
                if hasattr(self.connector, 'get_functions'):
                    functions = await self.connector.get_functions(schema)
                    all_procedures.extend(functions)

                # PostgreSQL only: Materialized views (count as views)
                if self.config.db_type == "postgresql" and hasattr(self.connector, 'get_materialized_views'):
                    matviews = await self.connector.get_materialized_views(schema)
                    all_views.extend(matviews)

            except Exception as e:
                logger.warning(f"[DB-Scanner] Failed to collect lineage for schema {schema}: {e}")
                continue

        # Attach to result
        result.views = all_views
        result.triggers = all_triggers
        result.procedures = all_procedures

        total_lineage = len(all_views) + len(all_triggers) + len(all_procedures)
        if total_lineage > 0:
            logger.info(
                f"[DB-Scanner] ✅ Lineage collected: "
                f"{len(all_views)} views, "
                f"{len(all_triggers)} triggers, "
                f"{len(all_procedures)} procedures"
            )
        else:
            logger.info(f"[DB-Scanner] No lineage metadata found")


# Helper function for CLI usage
async def scan_database(config: DBScanConfig) -> DBScanResult:
    """
    Scan database and return JSON brut.

    Usage:
        config = DBScanConfig(
            db_type="postgresql",
            host="localhost",
            port=5433,
            database="apollo_test",
            username="apollo_user",
            password="apollo_pass_2025"
        )
        result = await scan_database(config)
    """
    scanner = DBScanner(config)
    return await scanner.scan()
