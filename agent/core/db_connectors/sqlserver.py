"""
SQL Server Database Connector
Implementation for Microsoft SQL Server databases
"""

from typing import Dict, Any, List, Optional
import aioodbc
from .base import DatabaseConnector, ConnectorCapabilities
from .registry import register_connector
import logging
import re

logger = logging.getLogger(__name__)


@register_connector
class SQLServerConnector(DatabaseConnector):
    """
    Connecteur SQL Server avec aioodbc

    Supports:
    - Auto-discovery schemas/tables/columns
    - Read-only validation
    - Introspection metadata (PKs, FKs, indexes)
    - V1.4 Enhanced Metrics (Sprint 30)
    - Lineage metadata (Sprint 21)
    """

    METADATA = {
        "db_type": "sqlserver",
        "name": "SQL Server",
        "default_port": 1433,
        "ports_to_scan": [1433, 1434],
        "requires": ["aioodbc", "ODBC Driver 18"]
    }

    CAPABILITIES = (
        ConnectorCapabilities.CAN_LIST |
        ConnectorCapabilities.CAN_READ |
        ConnectorCapabilities.CAN_SAMPLE |
        ConnectorCapabilities.CAN_SCAN_PII |
        ConnectorCapabilities.CAN_EXECUTE_QUERY |
        ConnectorCapabilities.CAN_DETECT_SCHEMA
    )

    def _detect_odbc_driver(self) -> str:
        """Detect best available ODBC driver (18 > 17 > generic)"""
        try:
            import pyodbc
            drivers = pyodbc.drivers()
            for name in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
                if name in drivers:
                    logger.info(f"[SQLServer] Using ODBC driver: {name}")
                    return name
        except Exception:
            pass
        return "ODBC Driver 18 for SQL Server"

    async def test_connection(self) -> Dict[str, Any]:
        """Test connexion SQL Server"""
        try:
            driver = self._detect_odbc_driver()
            # Build connection string
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={self.config.get('host')},{self.config.get('port', 1433)};"
                f"DATABASE={self.config.get('database')};"
                f"UID={self.config.get('username')};"
                f"PWD={self.config.get('password')};"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout={self.timeout};"
            )

            # Establish connection
            self.connection = await aioodbc.connect(dsn=conn_str)

            # Count tables
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM sys.tables
                    WHERE type = 'U'
                """)
                result = await cursor.fetchone()
                tables_count = result[0]

            logger.info(f"SQL Server connection successful: {tables_count} tables detected")

            return {
                "success": True,
                "tables_count": tables_count,
                "message": f"Connected to SQL Server. {tables_count} tables detected.",
                "database_type": "sqlserver"
            }

        except Exception as e:
            logger.error(f"SQL Server connection error: {e}")
            return {
                "success": False,
                "tables_count": 0,
                "message": "Connection failed",
                "error": str(e),
                "database_type": "sqlserver"
            }

    async def is_read_only(self) -> bool:
        """Check if database is read-only"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT is_read_only
                    FROM sys.databases
                    WHERE name = DB_NAME()
                """)
                result = await cursor.fetchone()
                return result[0] == 1 if result else False
        except Exception:
            return False

    async def _get_user_permissions(self) -> List[str]:
        """Get user permissions"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT permission_name
                    FROM fn_my_permissions(NULL, 'DATABASE')
                    WHERE permission_name IN ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP')
                """)
                results = await cursor.fetchall()
                return [row[0] for row in results]
        except Exception:
            return []

    async def get_schemas(self) -> List[str]:
        """Liste tous les schemas"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT DISTINCT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')
                ORDER BY schema_name
            """)
            results = await cursor.fetchall()
            return [row[0] for row in results]

    async def get_tables(self, schema: str) -> List[str]:
        """Liste toutes les tables d'un schema"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = ?
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """, (schema,))
            results = await cursor.fetchall()
            return [row[0] for row in results]

    async def get_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Description colonnes d'une table"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    CASE WHEN pk.column_name IS NOT NULL THEN 'PRI' ELSE '' END as column_key
                FROM information_schema.columns c
                LEFT JOIN (
                    SELECT ku.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku
                        ON tc.constraint_name = ku.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = ?
                    AND tc.table_name = ?
                ) pk ON c.column_name = pk.column_name
                WHERE c.table_schema = ?
                AND c.table_name = ?
                ORDER BY c.ordinal_position
            """, (schema, table, schema, table))
            results = await cursor.fetchall()

            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == 'YES',
                    "default": row[3],
                    "primary_key": row[4] == 'PRI'
                }
                for row in results
            ]

    async def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """Recuperation cles primaires"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = ?
                AND tc.table_name = ?
            """, (schema, table))
            results = await cursor.fetchall()
            return [row[0] for row in results]

    async def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Recuperation cles etrangeres"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT
                    cu.column_name,
                    pk.table_schema + '.' + pk.table_name as referenced_table,
                    pt.column_name as referenced_column
                FROM information_schema.referential_constraints c
                JOIN information_schema.table_constraints fk
                    ON c.constraint_name = fk.constraint_name
                JOIN information_schema.table_constraints pk
                    ON c.unique_constraint_name = pk.constraint_name
                JOIN information_schema.key_column_usage cu
                    ON c.constraint_name = cu.constraint_name
                JOIN information_schema.key_column_usage pt
                    ON c.unique_constraint_name = pt.constraint_name
                WHERE fk.table_schema = ?
                AND fk.table_name = ?
            """, (schema, table))
            results = await cursor.fetchall()
            return [
                {
                    "column": row[0],
                    "referenced_table": row[1],
                    "referenced_column": row[2]
                }
                for row in results
            ]

    async def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Recuperation indexes"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT
                    i.name as index_name,
                    STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) as columns,
                    i.is_unique
                FROM sys.indexes i
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                JOIN sys.tables t ON i.object_id = t.object_id
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE s.name = ?
                AND t.name = ?
                AND i.name IS NOT NULL
                GROUP BY i.name, i.is_unique
            """, (schema, table))
            results = await cursor.fetchall()
            return [
                {
                    "name": row[0],
                    "columns": row[1].split(',') if row[1] else [],
                    "unique": row[2] == 1
                }
                for row in results
            ]

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute arbitrary SELECT query (read-only)

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            List of row dicts

        Raises:
            ValueError: If query contains forbidden operations
        """
        # Security: Only allow SELECT queries
        query_upper = query.strip().upper()
        forbidden_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'GRANT', 'REVOKE']

        for keyword in forbidden_keywords:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, query_upper):
                raise ValueError(f"Forbidden operation detected: {keyword}")

        if not query_upper.startswith('SELECT'):
            raise ValueError("Only SELECT queries are allowed")

        try:
            async with self.connection.cursor() as cursor:
                # pyodbc: Don't pass args parameter if no arguments
                if args:
                    await cursor.execute(query, args)
                else:
                    await cursor.execute(query)
                columns = [desc[0] for desc in cursor.description]
                results = await cursor.fetchall()
                return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    # =========================================================================
    # LINEAGE METADATA (Sprint 21)
    # =========================================================================

    async def get_views(self, schema: str) -> List[Dict[str, Any]]:
        """Retrieve SQL views metadata"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT
                        v.name as view_name,
                        m.definition
                    FROM sys.views v
                    JOIN sys.schemas s ON v.schema_id = s.schema_id
                    JOIN sys.sql_modules m ON v.object_id = m.object_id
                    WHERE s.name = ?
                    ORDER BY v.name
                """, (schema,))
                results = await cursor.fetchall()

                views = []
                for row in results:
                    view_def = row[1] or ''
                    referenced_tables = re.findall(
                        r'\bFROM\s+\[?(\w+)\]?',
                        view_def,
                        re.IGNORECASE
                    )
                    tables = list(set(referenced_tables))

                    views.append({
                        "name": row[0],
                        "schema": schema,
                        "definition": view_def,
                        "referenced_tables": tables
                    })

                logger.info(f"[SQLServer] Found {len(views)} views in schema {schema}")
                return views

        except Exception as e:
            logger.warning(f"Could not retrieve views for {schema}: {e}")
            return []

    async def get_triggers(self, schema: str) -> List[Dict[str, Any]]:
        """Retrieve triggers metadata"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT
                        OBJECT_NAME(t.parent_id) as table_name,
                        t.name as trigger_name,
                        CASE
                            WHEN t.is_instead_of_trigger = 1 THEN 'INSTEAD OF'
                            ELSE 'AFTER'
                        END as event,
                        m.definition as function_call
                    FROM sys.triggers t
                    JOIN sys.sql_modules m ON t.object_id = m.object_id
                    JOIN sys.tables tb ON t.parent_id = tb.object_id
                    JOIN sys.schemas s ON tb.schema_id = s.schema_id
                    WHERE s.name = ?
                    ORDER BY table_name, trigger_name
                """, (schema,))
                results = await cursor.fetchall()

                triggers = []
                for row in results:
                    triggers.append({
                        "table_name": row[0],
                        "trigger_name": row[1],
                        "event": row[2],
                        "function_call": row[3],
                        "schema": schema
                    })

                logger.info(f"[SQLServer] Found {len(triggers)} triggers in schema {schema}")
                return triggers

        except Exception as e:
            logger.warning(f"Could not retrieve triggers for {schema}: {e}")
            return []

    async def get_functions(self, schema: str) -> List[Dict[str, Any]]:
        """Retrieve stored procedures/functions metadata"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT
                        o.name,
                        o.type_desc as type,
                        m.definition
                    FROM sys.objects o
                    JOIN sys.schemas s ON o.schema_id = s.schema_id
                    JOIN sys.sql_modules m ON o.object_id = m.object_id
                    WHERE s.name = ?
                    AND o.type IN ('P', 'FN', 'IF', 'TF')
                    ORDER BY o.name
                """, (schema,))
                results = await cursor.fetchall()

                functions = []
                for row in results:
                    functions.append({
                        "name": row[0],
                        "type": row[1],
                        "definition": row[2] or '',
                        "schema": schema
                    })

                logger.info(f"[SQLServer] Found {len(functions)} functions/procedures in schema {schema}")
                return functions

        except Exception as e:
            logger.warning(f"Could not retrieve functions for {schema}: {e}")
            return []

    # =========================================================================
    # V1.4 ENHANCED METRICS (Sprint 30)
    # =========================================================================

    async def get_last_updated(self, schema: str, table: str) -> str:
        """
        Get last update timestamp for table.

        SQL Server Strategy: Use sys.tables.modify_date (accessible to all users)
        Fallback: sys.dm_db_index_usage_stats (requires VIEW SERVER PERFORMANCE STATE)

        Returns:
            ISO 8601 timestamp string or None
        """
        try:
            async with self.connection.cursor() as cursor:
                # Use sys.tables.modify_date (no special permissions required)
                await cursor.execute("""
                    SELECT modify_date
                    FROM sys.tables t
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    WHERE s.name = ?
                    AND t.name = ?
                """, (schema, table))
                result = await cursor.fetchone()
                if result and result[0]:
                    return result[0].isoformat()
                return None
        except Exception as e:
            logger.warning(f"Could not get last_updated for {schema}.{table}: {e}")
            return None

    async def get_table_size(self, schema: str, table: str) -> Optional[int]:
        """
        Get total size of a table in bytes (data + indexes).

        Sprint 86B Niveau 2: Populate TableMetadata.size_bytes.
        Uses sys.allocation_units via sys.partitions.

        Returns:
            Size in bytes, or None if unavailable
        """
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT SUM(a.total_pages) * 8192 as size_bytes
                    FROM sys.tables t
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    JOIN sys.indexes i ON t.object_id = i.object_id
                    JOIN sys.partitions p ON i.object_id = p.object_id
                        AND i.index_id = p.index_id
                    JOIN sys.allocation_units a ON p.partition_id = a.container_id
                    WHERE s.name = ? AND t.name = ?
                """, (schema, table))
                result = await cursor.fetchone()
                if result and result[0] is not None:
                    return int(result[0])
                return None
        except Exception as e:
            logger.warning(f"Could not get table size for {schema}.{table}: {e}")
            return None

    async def get_orphan_count(self, schema: str, table: str, foreign_keys: list) -> int:
        """
        Count orphan rows (FK pointing to non-existent parent).

        Returns:
            Total orphan count (0 if no FKs)
        """
        if not foreign_keys:
            return 0

        total_orphans = 0

        for fk in foreign_keys:
            try:
                ref_table_parts = fk['referenced_table'].split('.')
                if len(ref_table_parts) == 2:
                    ref_schema, ref_table = ref_table_parts
                else:
                    ref_schema = schema
                    ref_table = fk['referenced_table']

                # SQL Server bracket syntax for identifiers
                query = f"""
                    SELECT COUNT(*) as orphan_count
                    FROM [{schema}].[{table}] t
                    WHERE t.[{fk['column']}] IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM [{ref_schema}].[{ref_table}] p
                        WHERE p.[{fk['ref_column']}] = t.[{fk['column']}]
                    )
                """

                async with self.connection.cursor() as cursor:
                    await cursor.execute(query)
                    result = await cursor.fetchone()
                    if result:
                        total_orphans += result[0]

            except Exception as e:
                logger.warning(f"Could not count orphans for FK {fk.get('column')}: {e}")
                continue

        return total_orphans

    async def get_index_stats(self, schema: str, table: str) -> int:
        """
        Get index count for table.

        SQL Server: Count indexes from sys.indexes (no special permissions required)

        Returns:
            Total index count for the table
        """
        try:
            async with self.connection.cursor() as cursor:
                # Count indexes (accessible without special permissions)
                await cursor.execute("""
                    SELECT COUNT(*) as idx_count
                    FROM sys.indexes i
                    JOIN sys.tables t ON i.object_id = t.object_id
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    WHERE s.name = ?
                    AND t.name = ?
                    AND i.name IS NOT NULL
                """, (schema, table))
                result = await cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.warning(f"Could not get index stats for {schema}.{table}: {e}")
            return 0

    async def get_type_validity(self, schema: str, table: str, columns: list, row_count: int) -> int:
        """
        Count invalid values based on declared column types.

        Validates:
        - email columns: must contain @
        - phone columns: must match phone pattern

        Returns:
            Count of invalid values
        """
        invalid_count = 0

        if row_count == 0:
            return 0

        sample_size = min(row_count, 10000)

        for col in columns:
            col_name = col.get('name', '')
            col_name_lower = col_name.lower()

            try:
                # Email validation (SQL Server uses LIKE instead of REGEXP)
                if 'email' in col_name_lower or 'mail' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM (SELECT TOP {sample_size} [{col_name}] FROM [{schema}].[{table}]) t
                        WHERE [{col_name}] IS NOT NULL
                        AND [{col_name}] NOT LIKE '%_@_%._%'
                    """
                    async with self.connection.cursor() as cursor:
                        await cursor.execute(query)
                        result = await cursor.fetchone()
                        if result:
                            invalid_count += result[0]

                # Phone validation
                elif 'phone' in col_name_lower or 'tel' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM (SELECT TOP {sample_size} [{col_name}] FROM [{schema}].[{table}]) t
                        WHERE [{col_name}] IS NOT NULL
                        AND LEN([{col_name}]) < 8
                    """
                    async with self.connection.cursor() as cursor:
                        await cursor.execute(query)
                        result = await cursor.fetchone()
                        if result:
                            invalid_count += result[0]

            except Exception as e:
                logger.warning(f"Type validation failed for {col_name}: {e}")
                continue

        return invalid_count

    async def close(self):
        """Fermeture connexion SQL Server"""
        if self.connection:
            await self.connection.close()

    async def _close_connection(self):
        """Alias pour compatibilite"""
        await self.close()
