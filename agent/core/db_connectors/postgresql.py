"""
PostgreSQL Database Connector
Implementation for PostgreSQL databases
"""

from typing import Dict, Any, List, Optional
import asyncpg
import re
from .base import DatabaseConnector, ConnectorCapabilities
from .registry import register_connector
import logging

# Import DBSmartSampler for intelligent sampling (standalone - no backend dependency)
from ..db_sampler import DBSmartSampler

logger = logging.getLogger(__name__)

# Hub system tables to exclude from scans (avoid circular reference)
HUB_SYSTEM_TABLES = [
    'agent_reports', 'agent_report_files', 'agent_report_files_summary',
    'agent_report_db_summary', 'clients', 'db_connections', 'reports'
]


@register_connector
class PostgreSQLConnector(DatabaseConnector):
    """
    Connecteur PostgreSQL avec asyncpg

    Supports:
    - Auto-discovery schemas/tables/columns
    - Read-only validation
    - Introspection metadata (PKs, FKs, indexes)
    """

    METADATA = {
        "db_type": "postgresql",
        "name": "PostgreSQL",
        "default_port": 5432,
        "ports_to_scan": [5432, 5433, 5434],
        "requires": ["asyncpg"]
    }

    CAPABILITIES = (
        ConnectorCapabilities.CAN_LIST |
        ConnectorCapabilities.CAN_READ |
        ConnectorCapabilities.CAN_SAMPLE |
        ConnectorCapabilities.CAN_SCAN_PII |
        ConnectorCapabilities.CAN_EXECUTE_QUERY |
        ConnectorCapabilities.CAN_DETECT_SCHEMA
    )

    async def test_connection(self) -> Dict[str, Any]:
        """Test connexion PostgreSQL"""
        try:
            # Establish connection
            # Prepare connection parameters
            ssl_mode = self.config.get("ssl", False)

            # Build connection args
            conn_args = {
                "host": self.config.get("host"),
                "port": self.config.get("port", 5432),
                "database": self.config.get("database"),
                "user": self.config.get("username"),
                "password": self.config.get("password"),
                "timeout": self.timeout
            }

            # Explicitly set SSL parameter
            # asyncpg defaults to ssl='prefer' if omitted, which fails on non-SSL servers
            # We must explicitly pass 'disable' when ssl_mode is False
            if ssl_mode:
                conn_args["ssl"] = True  # Boolean True enables SSL with verification
            else:
                conn_args["ssl"] = 'disable'  # String 'disable' prevents SSL negotiation

            self.connection = await asyncpg.connect(**conn_args)

            # Count tables
            query = """
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """
            result = await self.connection.fetchrow(query)
            tables_count = result['count']

            logger.info(f"PostgreSQL connection successful: {tables_count} tables detected")

            return {
                "success": True,
                "tables_count": tables_count,
                "message": f"Connected to PostgreSQL. {tables_count} tables detected.",
                "database_type": "postgresql"
            }

        except asyncpg.PostgresConnectionError as e:
            logger.error(f"PostgreSQL connection error: {e}")
            return {
                "success": False,
                "tables_count": 0,
                "message": "Connection failed",
                "error": str(e),
                "database_type": "postgresql"
            }

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                "success": False,
                "tables_count": 0,
                "message": "Unexpected error",
                "error": str(e),
                "database_type": "postgresql"
            }

    async def is_read_only(self) -> bool:
        """
        Check if connection is read-only

        Returns:
            True if read-only, False otherwise
        """
        try:
            # Try to check transaction_read_only setting
            result = await self.connection.fetchrow("SHOW transaction_read_only")
            return result['transaction_read_only'] == 'on'
        except Exception:
            # If check fails, assume not read-only
            return False

    async def _get_user_permissions(self) -> List[str]:
        """Get user permissions"""
        try:
            query = """
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = current_user
            """
            results = await self.connection.fetch(query)
            return [row['privilege_type'] for row in results]
        except Exception as e:
            logger.warning(f"Could not fetch permissions: {e}")
            return []

    async def get_schemas(self) -> List[str]:
        """Liste tous les schemas (excluding system schemas)"""
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
        """
        results = await self.connection.fetch(query)
        return [row['schema_name'] for row in results]

    async def get_tables(self, schema: str) -> List[str]:
        """Liste toutes les tables d'un schema (excluding Hub system tables)"""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        results = await self.connection.fetch(query, schema)
        # Filter out Hub system tables to avoid circular reference
        tables = [row['table_name'] for row in results if row['table_name'] not in HUB_SYSTEM_TABLES]
        if len(tables) < len(results):
            excluded = len(results) - len(tables)
            logger.info(f"[PostgreSQL] Excluded {excluded} Hub system tables from {schema}")
        return tables

    async def get_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Description colonnes d'une table"""
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = $1
            AND table_name = $2
            ORDER BY ordinal_position
        """
        results = await self.connection.fetch(query, schema, table)

        # Get primary keys
        pks = await self.get_primary_keys(schema, table)

        columns = []
        for row in results:
            columns.append({
                "name": row['column_name'],
                "type": row['data_type'],
                "nullable": row['is_nullable'] == 'YES',
                "default": row['column_default'],
                "primary_key": row['column_name'] in pks
            })

        return columns

    async def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """Récupération clés primaires"""
        query = """
            SELECT a.attname as column_name
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = ($1 || '.' || $2)::regclass
            AND i.indisprimary
        """
        try:
            results = await self.connection.fetch(query, schema, table)
            return [row['column_name'] for row in results]
        except Exception:
            return []

    async def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Récupération clés étrangères"""
        query = """
            SELECT
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = $1
            AND tc.table_name = $2
        """
        try:
            results = await self.connection.fetch(query, schema, table)
            return [
                {
                    "column": row['column_name'],
                    "referenced_table": f"{row['foreign_table_schema']}.{row['foreign_table_name']}",
                    "referenced_column": row['foreign_column_name']
                }
                for row in results
            ]
        except Exception:
            return []

    async def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Récupération indexes"""
        query = """
            SELECT
                i.relname as index_name,
                array_agg(a.attname) as column_names,
                ix.indisunique as is_unique
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relkind = 'r'
            AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $1)
            AND t.relname = $2
            GROUP BY i.relname, ix.indisunique
        """
        try:
            results = await self.connection.fetch(query, schema, table)
            return [
                {
                    "name": row['index_name'],
                    "columns": row['column_names'],
                    "unique": row['is_unique']
                }
                for row in results
            ]
        except Exception:
            return []

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute arbitrary SELECT query

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            List of row dicts

        Raises:
            ValueError: If query contains non-SELECT operations
            Exception: If query execution fails
        """
        # Security: Only allow SELECT queries
        # Use word boundaries to avoid false positives (e.g., "created_at" contains "CREATE")
        query_upper = query.strip().upper()
        forbidden_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'GRANT', 'REVOKE']

        for keyword in forbidden_keywords:
            # Match whole words only using regex word boundaries
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, query_upper):
                raise ValueError(f"Forbidden operation detected: {keyword}")

        if not query_upper.startswith('SELECT'):
            raise ValueError("Only SELECT queries are allowed")

        try:
            results = await self.connection.fetch(query, *args)
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    async def get_last_updated(self, schema: str, table: str) -> str:
        """
        Get last update timestamp for table.

        Strategy:
        1. Try pg_stat_user_tables.last_analyze (most recent analyze)
        2. Fallback to pg_stat_user_tables.last_autoanalyze
        3. Return NULL if unavailable

        Returns:
            ISO 8601 timestamp string or None
        """
        query = """
            SELECT
                GREATEST(
                    last_analyze,
                    last_autoanalyze,
                    last_vacuum,
                    last_autovacuum
                ) as last_updated
            FROM pg_stat_user_tables
            WHERE schemaname = $1
            AND relname = $2
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            if result and result['last_updated']:
                return result['last_updated'].isoformat()
            return None
        except Exception as e:
            logger.warning(f"Could not get last_updated for {schema}.{table}: {e}")
            return None

    async def get_table_size(self, schema: str, table: str) -> Optional[int]:
        """
        Get total size of a table in bytes (data + indexes + TOAST).

        Sprint 86B Niveau 2: Populate TableMetadata.size_bytes.
        Uses pg_total_relation_size which includes indexes and TOAST data.

        Returns:
            Size in bytes, or None if unavailable
        """
        query = """
            SELECT pg_total_relation_size(
                quote_ident($1) || '.' || quote_ident($2)
            ) as size_bytes
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            if result and result['size_bytes'] is not None:
                return int(result['size_bytes'])
            return None
        except Exception as e:
            logger.warning(f"Could not get table size for {schema}.{table}: {e}")
            return None

    async def get_pg_table_stats(self, schema: str, table: str) -> Dict[str, Any]:
        """
        Get PostgreSQL-specific table stats from pg_stat_user_tables.

        Sprint 86B Niveau 2: 4 stats in 1 query.
        - n_dead_tup: dead tuples (bloat indicator, VACUUM needed)
        - n_live_tup: live tuples (row estimate without COUNT)
        - seq_scan: sequential scans (missing index indicator)
        - last_vacuum: last manual or auto vacuum timestamp

        Returns:
            Dict with keys: n_dead_tup, n_live_tup, seq_scan_count, last_vacuum
        """
        query = """
            SELECT
                n_dead_tup,
                n_live_tup,
                seq_scan,
                GREATEST(last_vacuum, last_autovacuum) as last_vacuum
            FROM pg_stat_user_tables
            WHERE schemaname = $1 AND relname = $2
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            if result:
                last_vac = result['last_vacuum']
                return {
                    'n_dead_tup': result['n_dead_tup'],
                    'n_live_tup': result['n_live_tup'],
                    'seq_scan_count': result['seq_scan'],
                    'last_vacuum': last_vac.isoformat() if last_vac else None
                }
            return {'n_dead_tup': None, 'n_live_tup': None, 'seq_scan_count': None, 'last_vacuum': None}
        except Exception as e:
            logger.warning(f"Could not get pg stats for {schema}.{table}: {e}")
            return {'n_dead_tup': None, 'n_live_tup': None, 'seq_scan_count': None, 'last_vacuum': None}

    async def get_null_fractions(self, schema: str, table: str) -> Dict[str, float]:
        """
        Get null fraction per column from pg_stats (pre-computed by ANALYZE).

        Sprint 86B Niveau 2: Replace null_percentage stub.
        Zero cost — reads pre-computed statistics, no data scanning.

        Returns:
            Dict {column_name: null_percentage} (only columns with nulls > 0)
        """
        query = """
            SELECT attname, null_frac
            FROM pg_stats
            WHERE schemaname = $1 AND tablename = $2
            AND null_frac > 0
        """
        try:
            results = await self.connection.fetch(query, schema, table)
            return {
                row['attname']: round(float(row['null_frac']) * 100, 2)
                for row in results
            }
        except Exception as e:
            logger.warning(f"Could not get null fractions for {schema}.{table}: {e}")
            return {}

    async def get_orphan_count(self, schema: str, table: str, foreign_keys: List[Dict[str, Any]]) -> int:
        """
        Count orphan rows (FK pointing to non-existent parent).

        For each FK in table:
        - SELECT COUNT(*) WHERE fk_column NOT IN (SELECT pk FROM parent_table)
        - Sum all orphans

        Args:
            schema: Table schema
            table: Table name
            foreign_keys: List of FK definitions from get_foreign_keys()

        Returns:
            Total orphan count (0 if no FKs)
        """
        if not foreign_keys:
            return 0

        total_orphans = 0

        for fk in foreign_keys:
            try:
                # Parse referenced_table (format: "schema.table")
                ref_table_parts = fk['referenced_table'].split('.')
                if len(ref_table_parts) == 2:
                    ref_schema, ref_table = ref_table_parts
                else:
                    ref_schema = schema
                    ref_table = fk['referenced_table']

                # Query to count orphans
                query = f"""
                    SELECT COUNT(*) as orphan_count
                    FROM "{schema}"."{table}" t
                    WHERE t."{fk['column']}" IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM "{ref_schema}"."{ref_table}" p
                        WHERE p."{fk['referenced_column']}" = t."{fk['column']}"
                    )
                """

                result = await self.connection.fetchrow(query)
                if result:
                    total_orphans += result['orphan_count']

            except Exception as e:
                logger.warning(f"Could not count orphans for FK {fk['column']}: {e}")
                continue

        return total_orphans

    async def get_index_stats(self, schema: str, table: str) -> int:
        """
        Get total index scan count for table.

        Sums idx_scan from pg_stat_user_indexes for all indexes on table.

        Returns:
            Total index scans (0 if no indexes or stats unavailable)
        """
        query = """
            SELECT COALESCE(SUM(idx_scan), 0) as total_scans
            FROM pg_stat_user_indexes
            WHERE schemaname = $1
            AND relname = $2
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            return result['total_scans'] if result else 0
        except Exception as e:
            logger.warning(f"Could not get index stats for {schema}.{table}: {e}")
            return 0

    async def get_type_validity(self, schema: str, table: str, columns: List[Dict[str, Any]], row_count: int) -> int:
        """
        Count invalid values based on declared column types.

        Uses DBSmartSampler for zone-aware intelligent sampling:
        - SENSITIVE tables (users, finance): 100% sampling
        - NORMAL tables: 30% sampling
        - ARCHIVE tables (logs, backups): 5% sampling

        Validates:
        - email columns: must contain @
        - phone columns: must match phone pattern
        - numeric columns: must be valid numbers

        Args:
            schema: Table schema
            table: Table name
            columns: Column definitions from get_columns()
            row_count: Total rows in table

        Returns:
            Count of invalid values (0 if validation not applicable)
        """
        invalid_count = 0

        # Early exit if empty table
        if row_count == 0:
            return 0

        # Use DBSmartSampler for intelligent sampling
        sampler = DBSmartSampler(min_sample=1000, max_sample=100_000)
        sample_size = sampler.get_sample_size(table, schema, row_count)

        logger.debug(
            f"[Type Validity] Table {schema}.{table}: "
            f"row_count={row_count}, sample_size={sample_size} "
            f"({(sample_size/row_count*100):.1f}%)"
        )

        # Check specific column types
        for col in columns:
            col_name = col['name']
            col_type = col['type'].lower()
            col_name_lower = col_name.lower()

            try:
                # Email validation (column name or type)
                if 'email' in col_name_lower or 'mail' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM "{schema}"."{table}"
                        WHERE "{col_name}" IS NOT NULL
                        AND "{col_name}" !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{{2,}}$'
                        LIMIT {sample_size}
                    """
                    result = await self.connection.fetchrow(query)
                    if result:
                        invalid_count += result['invalid']

                # Phone validation
                elif 'phone' in col_name_lower or 'tel' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM "{schema}"."{table}"
                        WHERE "{col_name}" IS NOT NULL
                        AND "{col_name}" !~ '^[+]?[0-9\\s\\-\\(\\)]{{8,}}$'
                        LIMIT {sample_size}
                    """
                    result = await self.connection.fetchrow(query)
                    if result:
                        invalid_count += result['invalid']

                # Numeric types (if stored as text but should be numeric)
                elif 'character' in col_type or 'text' in col_type:
                    if any(num_hint in col_name_lower for num_hint in ['amount', 'price', 'quantity', 'count']):
                        query = f"""
                            SELECT COUNT(*) as invalid
                            FROM "{schema}"."{table}"
                            WHERE "{col_name}" IS NOT NULL
                            AND "{col_name}" !~ '^-?[0-9]+(\\.[0-9]+)?$'
                            LIMIT {sample_size}
                        """
                        result = await self.connection.fetchrow(query)
                        if result:
                            invalid_count += result['invalid']

            except Exception as e:
                logger.warning(f"Type validation failed for {col_name}: {e}")
                continue

        return invalid_count

    async def _get_documentation_coverage(self) -> float:
        """Calculate documentation coverage score (KPI #2).

        Formula: (tables_documented/total_tables * 0.4) + (columns_documented/total_columns * 0.6)
        Based on pg_description catalog.

        Returns:
            float: Score 0.0-1.0, or 0.0 if query fails
        """
        try:
            query = """
            SELECT
                (SELECT COUNT(*) FROM pg_description d
                 JOIN pg_class c ON d.objoid = c.oid
                 WHERE c.relkind = 'r' AND d.objsubid = 0) as doc_tables,
                (SELECT COUNT(*) FROM information_schema.tables
                 WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')) as total_tables,
                (SELECT COUNT(*) FROM pg_description d
                 JOIN pg_attribute a ON d.objoid = a.attrelid AND d.objsubid = a.attnum
                 WHERE a.attnum > 0) as doc_columns,
                (SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) as total_columns;
            """
            result = await self.connection.fetchrow(query)

            doc_tables = result['doc_tables'] or 0
            total_tables = result['total_tables'] or 1
            doc_columns = result['doc_columns'] or 0
            total_columns = result['total_columns'] or 1

            t_cov = doc_tables / max(total_tables, 1)
            c_cov = doc_columns / max(total_columns, 1)

            return t_cov * 0.4 + c_cov * 0.6

        except Exception as e:
            logger.warning(f"Failed to calculate documentation coverage: {e}")
            return 0.0

    async def _get_security_compliance(self) -> float:
        """Calculate security compliance score (KPI #3).

        6 criteria:
        - c1: SSL/TLS active (20%)
        - c2: Not superuser (25%)
        - c3: Least privilege (<= 3 privilege types) (20%)
        - c4: Read-only role exists (20%)
        - c5: PUBLIC grants minimal (<= 5) (10%)
        - c6: Multiple roles (>= 3) (10%)

        Returns:
            float: Score 0.0-1.0, or 0.0 if query fails
        """
        try:
            score = 0.0

            # c1: SSL/TLS
            try:
                result = await self.connection.fetchrow("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid();")
                if result and result['ssl']:
                    score += 0.20
            except Exception:
                pass

            # c2: Not superuser
            result = await self.connection.fetchrow("SELECT rolsuper FROM pg_roles WHERE rolname = current_user;")
            if result and not result['rolsuper']:
                score += 0.25

            # c3: Least privilege
            result = await self.connection.fetchrow("""
                SELECT COUNT(DISTINCT privilege_type)
                FROM information_schema.role_table_grants
                WHERE grantee = current_user;
            """)
            if result:
                priv_count = result['count'] or 0
                if priv_count <= 1:
                    score += 0.20
                elif priv_count <= 3:
                    score += 0.10

            # c4: Read-only mode
            is_ro = await self.is_read_only()
            if is_ro:
                score += 0.20

            # c5: PUBLIC grants minimal
            result = await self.connection.fetchrow("""
                SELECT COUNT(*) as public_grants
                FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC';
            """)
            if result and (result['public_grants'] or 0) <= 5:
                score += 0.10

            # c6: Multiple roles
            result = await self.connection.fetchrow("""
                SELECT COUNT(*) as role_count
                FROM pg_roles WHERE rolcanlogin = true;
            """)
            if result and (result['role_count'] or 0) >= 3:
                score += 0.10

            return score

        except Exception as e:
            logger.warning(f"Failed to calculate security compliance: {e}")
            return 0.0

    async def _get_access_control(self) -> float:
        """Calculate access control score (KPI #5).

        5 criteria:
        - a1: RBAC present (roles defined) (20%)
        - a2: PUBLIC grants minimal (<= 5) (25%)
        - a3: Role separation (>= 2 privilege types) (25%)
        - a4: Avg privileges per role reasonable (<= 100) (20%)
        - a5: Table-level grants defined (10%)

        Returns:
            float: Score 0.0-1.0, or 0.0 if query fails
        """
        try:
            score = 0.0

            # a1: RBAC present
            result = await self.connection.fetchrow("""
                SELECT COUNT(*) as role_count
                FROM pg_roles WHERE rolcanlogin = false;
            """)
            if result and (result['role_count'] or 0) >= 3:
                score += 0.20

            # a2: PUBLIC grants minimal
            result = await self.connection.fetchrow("""
                SELECT COUNT(*) as public_grants
                FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC';
            """)
            public_grants = result['public_grants'] or 0 if result else 0
            if public_grants == 0:
                score += 0.25
            elif public_grants <= 5:
                score += 0.10

            # a3: Role separation
            result = await self.connection.fetchrow("""
                SELECT COUNT(DISTINCT privilege_type) as priv_types
                FROM information_schema.role_table_grants
                WHERE grantee != 'PUBLIC';
            """)
            if result and (result['priv_types'] or 0) >= 2:
                score += 0.25

            # a4: Avg privileges per role
            result = await self.connection.fetchrow("""
                SELECT AVG(priv_count) as avg_privs FROM (
                    SELECT grantee, COUNT(*) as priv_count
                    FROM information_schema.role_table_grants
                    WHERE grantee != 'PUBLIC'
                    GROUP BY grantee
                ) sub;
            """)
            if result and result['avg_privs']:
                p_avg = float(result['avg_privs'])
                if p_avg <= 100:
                    score += 0.20

            # a5: Table-level grants
            result = await self.connection.fetchrow("""
                SELECT COUNT(DISTINCT table_name) as tables_with_grants
                FROM information_schema.role_table_grants
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema');
            """)
            if result and (result['tables_with_grants'] or 0) > 0:
                score += 0.10

            return score

        except Exception as e:
            logger.warning(f"Failed to calculate access control: {e}")
            return 0.0

    async def has_table_documentation(self, schema: str, table: str) -> bool:
        """Check if table has a pg_description comment (per-table documentation).

        Different from _get_documentation_coverage() which is an aggregate metric.
        This is per-table: does THIS specific table have a COMMENT?

        Query: pg_description WHERE objoid = table OID AND objsubid = 0
        (objsubid = 0 means table-level comment, not column-level)

        Returns:
            True if table has a documentation comment
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM pg_description d
                JOIN pg_class c ON d.objoid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = $1
                AND c.relname = $2
                AND d.objsubid = 0
            ) as has_doc
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            return result['has_doc'] if result else False
        except Exception as e:
            logger.warning(f"Could not check documentation for {schema}.{table}: {e}")
            return False

    async def get_table_encrypted(self, schema: str, table: str) -> bool:
        """Check if table has encryption (TDE or column-level via pgcrypto).

        Detection strategies:
        1. Columns with bytea type + encryption-related names (pgcrypto pattern)
        2. Columns using pgcrypto functions (from pg_depend)

        Note: PostgreSQL native TDE requires Enterprise or external solutions.
        This detects application-level encryption patterns.

        Returns:
            True if encryption indicators found
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                AND (
                    (data_type = 'bytea' AND (
                        column_name LIKE '%encrypted%' OR
                        column_name LIKE '%cipher%' OR
                        column_name LIKE '%_enc' OR
                        column_name LIKE 'enc_%'
                    ))
                    OR column_name LIKE '%_encrypted'
                    OR column_name LIKE '%_hash'
                )
            ) as has_encryption
        """
        try:
            result = await self.connection.fetchrow(query, schema, table)
            return result['has_encryption'] if result else False
        except Exception as e:
            logger.warning(f"Could not check encryption for {schema}.{table}: {e}")
            return False

    async def get_table_grants(self, schema: str, table: str) -> list:
        """Get table permissions from role_table_grants.

        Returns list of grants (excluding system users postgres, PUBLIC).
        Format: [{"grantee": "user", "privilege": "SELECT", "is_grantable": false}]

        Returns:
            List of grant dicts
        """
        query = """
            SELECT grantee, privilege_type, is_grantable
            FROM information_schema.role_table_grants
            WHERE table_schema = $1 AND table_name = $2
            AND grantee NOT IN ('postgres', 'PUBLIC')
            ORDER BY grantee, privilege_type
        """
        try:
            rows = await self.connection.fetch(query, schema, table)
            return [
                {
                    "grantee": row['grantee'],
                    "privilege": row['privilege_type'],
                    "is_grantable": row['is_grantable'] == 'YES'
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Could not get grants for {schema}.{table}: {e}")
            return []

    async def _get_change_tracking(self) -> float:
        """Calculate change tracking score (KPI #4).

        Measures: % of tables that have at least one trigger
        (triggers = automated change tracking mechanism).

        Returns:
            float: Score 0.0-1.0 (ratio tables_with_triggers / total_tables)
        """
        query = """
            SELECT
                (SELECT COUNT(DISTINCT c.relname)
                 FROM pg_trigger t
                 JOIN pg_class c ON t.tgrelid = c.oid
                 JOIN pg_namespace n ON c.relnamespace = n.oid
                 WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                 AND NOT t.tgisinternal
                ) as tables_with_triggers,
                (SELECT COUNT(*)
                 FROM information_schema.tables
                 WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                 AND table_type = 'BASE TABLE'
                ) as total_tables
        """
        try:
            result = await self.connection.fetchrow(query)
            total = result['total_tables'] or 1
            with_triggers = result['tables_with_triggers'] or 0
            return with_triggers / max(total, 1)
        except Exception as e:
            logger.warning(f"Failed to calculate change tracking: {e}")
            return 0.0

    async def _get_table_size_distribution(self) -> float:
        """Calculate table size distribution score (KPI #5).

        Measures: how balanced table sizes are.
        Score 1.0 if no single table > 50% of total size.
        Score degrades linearly: 0.0 if one table = 100%.

        Returns:
            float: Score 0.0-1.0
        """
        query = """
            SELECT
                c.relname as table_name,
                pg_total_relation_size(c.oid) as size_bytes
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            AND c.relkind = 'r'
            ORDER BY size_bytes DESC
        """
        try:
            results = await self.connection.fetch(query)
            if not results:
                return 1.0

            total_size = sum(r['size_bytes'] for r in results)
            if total_size == 0:
                return 1.0

            max_size = results[0]['size_bytes']
            max_ratio = max_size / total_size

            # Score: 1.0 if max_ratio <= 0.5, linear decay to 0.0 at max_ratio = 1.0
            if max_ratio <= 0.5:
                return 1.0
            return max(0.0, 2.0 * (1.0 - max_ratio))

        except Exception as e:
            logger.warning(f"Failed to calculate table size distribution: {e}")
            return 0.0

    async def _get_ai_act_article11(self) -> float:
        """Calculate AI Act Article 11 compliance score (KPI #6).

        Article 11 requires: technical documentation for ML systems,
        including data lineage, model versioning, training logs.

        Heuristic: search for tables/columns with ML-related names.
        Score based on presence of:
        - ML tables (model, prediction, training, feature) -> 40%
        - Versioning columns on ML tables (version, created_at) -> 30%
        - Audit trail (log tables referencing ML tables) -> 30%

        Returns:
            float: Score 0.0-1.0
        """
        query = """
            SELECT
                table_name,
                column_name
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        """
        try:
            results = await self.connection.fetch(query)

            ML_TABLE_KEYWORDS = {'model', 'prediction', 'training', 'feature', 'ml_', 'ai_', 'inference'}
            VERSION_COLUMNS = {'version', 'model_version', 'created_at', 'updated_at', 'trained_at', 'run_id'}
            LOG_TABLE_KEYWORDS = {'log', 'audit', 'history', 'tracking'}

            # Build table -> columns map
            table_columns = {}
            for row in results:
                tname = row['table_name'].lower()
                cname = row['column_name'].lower()
                if tname not in table_columns:
                    table_columns[tname] = set()
                table_columns[tname].add(cname)

            score = 0.0

            # Check 1: ML tables exist (40%)
            ml_tables = [t for t in table_columns if any(kw in t for kw in ML_TABLE_KEYWORDS)]
            if ml_tables:
                score += 0.40

            # Check 2: ML tables have versioning columns (30%)
            if ml_tables:
                ml_with_version = [t for t in ml_tables if table_columns[t] & VERSION_COLUMNS]
                if ml_with_version:
                    score += 0.30 * (len(ml_with_version) / len(ml_tables))

            # Check 3: Log/audit tables exist (30%)
            log_tables = [t for t in table_columns if any(kw in t for kw in LOG_TABLE_KEYWORDS)]
            if log_tables:
                score += 0.30

            return min(score, 1.0)

        except Exception as e:
            logger.warning(f"Failed to calculate AI Act Article 11 compliance: {e}")
            return 0.0

    async def get_governance_metrics(self) -> Dict[str, float]:
        """Collect all governance metrics for scoring.

        Returns 6 KPIs (3 existing + 3 new V1.7):
        - documentation_coverage: pg_description coverage (tables + columns)
        - security_compliance: SSL, superuser, privileges, read-only
        - access_control: RBAC, PUBLIC grants, role separation
        - change_tracking: % tables with triggers (V1.7)
        - table_size_distribution: balanced table sizes (V1.7)
        - ai_act_article11: ML data traceability (V1.7)
        """
        return {
            "documentation_coverage": await self._get_documentation_coverage(),
            "security_compliance": await self._get_security_compliance(),
            "access_control": await self._get_access_control(),
            "change_tracking": await self._get_change_tracking(),
            "table_size_distribution": await self._get_table_size_distribution(),
            "ai_act_article11": await self._get_ai_act_article11(),
        }

    # =========================================================================
    # LINEAGE METADATA (Sprint 21)
    # =========================================================================

    async def get_views(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve SQL views metadata from PostgreSQL (Sprint 21 Lineage).

        Args:
            schema: Schema name to query

        Returns:
            List of view dicts with name, definition, referenced_tables
        """
        query = """
            SELECT
                table_name as view_name,
                view_definition
            FROM information_schema.views
            WHERE table_schema = $1
            ORDER BY table_name
        """
        try:
            results = await self.connection.fetch(query, schema)
            views = []
            for row in results:
                view_def = row['view_definition'] or ''
                # Extract referenced tables from FROM clause
                referenced_tables = re.findall(
                    r'\bFROM\s+(?:"?(\w+)"?\.)?(?:"?(\w+)"?)',
                    view_def,
                    re.IGNORECASE
                )
                # Flatten and deduplicate
                tables = list(set(
                    t[1] if t[1] else t[0]
                    for t in referenced_tables
                    if t[0] or t[1]
                ))

                views.append({
                    "name": row['view_name'],
                    "schema": schema,
                    "definition": view_def,
                    "referenced_tables": tables
                })

            logger.info(f"[PostgreSQL] Found {len(views)} views in schema {schema}")
            return views

        except Exception as e:
            logger.warning(f"Could not retrieve views for {schema}: {e}")
            return []

    async def get_triggers(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve triggers metadata from PostgreSQL (Sprint 21 Lineage).

        Args:
            schema: Schema name to query

        Returns:
            List of trigger dicts with table_name, trigger_name, event, function_call
        """
        query = """
            SELECT
                event_object_table as table_name,
                trigger_name,
                event_manipulation as event,
                action_statement as function_call
            FROM information_schema.triggers
            WHERE trigger_schema = $1
            ORDER BY event_object_table, trigger_name
        """
        try:
            results = await self.connection.fetch(query, schema)
            triggers = []
            for row in results:
                triggers.append({
                    "table_name": row['table_name'],
                    "trigger_name": row['trigger_name'],
                    "event": row['event'],
                    "function_call": row['function_call'],
                    "schema": schema
                })

            logger.info(f"[PostgreSQL] Found {len(triggers)} triggers in schema {schema}")
            return triggers

        except Exception as e:
            logger.warning(f"Could not retrieve triggers for {schema}: {e}")
            return []

    async def get_functions(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve stored procedures/functions metadata from PostgreSQL (Sprint 21 Lineage).

        Args:
            schema: Schema name to query

        Returns:
            List of procedure/function dicts with name, type, definition
        """
        query = """
            SELECT
                routine_name as name,
                routine_type as type,
                routine_definition as definition
            FROM information_schema.routines
            WHERE routine_schema = $1
            AND routine_type IN ('FUNCTION', 'PROCEDURE')
            ORDER BY routine_name
        """
        try:
            results = await self.connection.fetch(query, schema)
            functions = []
            for row in results:
                functions.append({
                    "name": row['name'],
                    "type": row['type'],
                    "definition": row['definition'] or '',
                    "schema": schema
                })

            logger.info(f"[PostgreSQL] Found {len(functions)} functions/procedures in schema {schema}")
            return functions

        except Exception as e:
            logger.warning(f"Could not retrieve functions for {schema}: {e}")
            return []

    async def get_materialized_views(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve materialized views from PostgreSQL (Sprint 21 Lineage).
        PostgreSQL-specific feature.

        Args:
            schema: Schema name to query

        Returns:
            List of matview dicts with name, definition
        """
        query = """
            SELECT
                matviewname as view_name,
                definition
            FROM pg_matviews
            WHERE schemaname = $1
            ORDER BY matviewname
        """
        try:
            results = await self.connection.fetch(query, schema)
            matviews = []
            for row in results:
                view_def = row['definition'] or ''
                # Extract referenced tables
                referenced_tables = re.findall(
                    r'\bFROM\s+(?:"?(\w+)"?\.)?(?:"?(\w+)"?)',
                    view_def,
                    re.IGNORECASE
                )
                tables = list(set(
                    t[1] if t[1] else t[0]
                    for t in referenced_tables
                    if t[0] or t[1]
                ))

                matviews.append({
                    "name": row['view_name'],
                    "schema": schema,
                    "definition": view_def,
                    "referenced_tables": tables,
                    "is_materialized": True
                })

            logger.info(f"[PostgreSQL] Found {len(matviews)} materialized views in schema {schema}")
            return matviews

        except Exception as e:
            logger.warning(f"Could not retrieve materialized views for {schema}: {e}")
            return []

    async def close(self):
        """Fermeture connexion PostgreSQL"""
        if self.connection:
            await self.connection.close()

    async def _close_connection(self):
        """Alias pour compatibilité"""
        await self.close()
