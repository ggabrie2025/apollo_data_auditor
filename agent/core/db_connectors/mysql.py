"""
MySQL Database Connector
Implementation for MySQL/MariaDB databases
"""

from typing import Dict, Any, List, Optional
import aiomysql
from .base import DatabaseConnector, ConnectorCapabilities
from .registry import register_connector
import logging
import re  # For query validation in execute_query()

logger = logging.getLogger(__name__)


@register_connector
class MySQLConnector(DatabaseConnector):
    """
    Connecteur MySQL/MariaDB avec aiomysql

    Supports:
    - Auto-discovery schemas/tables/columns
    - Read-only validation
    - Introspection metadata (PKs, FKs, indexes)
    """

    METADATA = {
        "db_type": "mysql",
        "name": "MySQL",
        "default_port": 3306,
        "ports_to_scan": [3306, 3307],
        "requires": ["aiomysql"]
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
        """Test connexion MySQL"""
        try:
            # Establish connection pool
            self.connection = await aiomysql.connect(
                host=self.config.get("host"),
                port=self.config.get("port", 3306),
                user=self.config.get("username"),
                password=self.config.get("password"),
                db=self.config.get("database"),
                connect_timeout=self.timeout
            )

            # Count tables
            async with self.connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    AND table_type = 'BASE TABLE'
                """)
                result = await cursor.fetchone()
                tables_count = result[0]

            logger.info(f"MySQL connection successful: {tables_count} tables detected")

            return {
                "success": True,
                "tables_count": tables_count,
                "message": f"Connected to MySQL. {tables_count} tables detected.",
                "database_type": "mysql"
            }

        except Exception as e:
            logger.error(f"MySQL connection error: {e}")
            return {
                "success": False,
                "tables_count": 0,
                "message": "Connection failed",
                "error": str(e),
                "database_type": "mysql"
            }

    async def is_read_only(self) -> bool:
        """Check if connection is read-only"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("SELECT @@read_only")
                result = await cursor.fetchone()
                return result[0] == 1
        except Exception:
            return False

    async def _get_user_permissions(self) -> List[str]:
        """Get user permissions"""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
                results = await cursor.fetchall()
                permissions = []
                for row in results:
                    grant = row[0].upper()
                    if 'INSERT' in grant:
                        permissions.append('INSERT')
                    if 'UPDATE' in grant:
                        permissions.append('UPDATE')
                    if 'DELETE' in grant:
                        permissions.append('DELETE')
                return list(set(permissions))
        except Exception:
            return []

    async def get_schemas(self) -> List[str]:
        """Liste tous les schemas (databases)"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
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
                WHERE table_schema = %s
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """, (schema,))
            results = await cursor.fetchall()
            return [row[0] for row in results]

    async def get_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Description colonnes d'une table"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    column_key
                FROM information_schema.columns
                WHERE table_schema = %s
                AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table))
            results = await cursor.fetchall()

            return [
                {
                    "name": row.get('column_name') or row.get('COLUMN_NAME'),
                    "type": row.get('data_type') or row.get('DATA_TYPE'),
                    "nullable": (row.get('is_nullable') or row.get('IS_NULLABLE')) == 'YES',
                    "default": row.get('column_default') or row.get('COLUMN_DEFAULT'),
                    "primary_key": (row.get('column_key') or row.get('COLUMN_KEY')) == 'PRI'
                }
                for row in results
            ]

    async def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """Récupération clés primaires"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s
                AND table_name = %s
                AND constraint_name = 'PRIMARY'
            """, (schema, table))
            results = await cursor.fetchall()
            return [row[0] for row in results]

    async def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Récupération clés étrangères"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT
                    column_name,
                    referenced_table_name,
                    referenced_column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s
                AND table_name = %s
                AND referenced_table_name IS NOT NULL
            """, (schema, table))
            results = await cursor.fetchall()
            return [
                {
                    "column": row.get('column_name') or row.get('COLUMN_NAME'),
                    "referenced_table": f"{schema}.{row.get('referenced_table_name') or row.get('REFERENCED_TABLE_NAME')}",
                    "referenced_column": row.get('referenced_column_name') or row.get('REFERENCED_COLUMN_NAME')
                }
                for row in results
            ]

    async def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Récupération indexes"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT
                    index_name,
                    GROUP_CONCAT(column_name ORDER BY seq_in_index) as columns,
                    MAX(non_unique) as non_unique
                FROM information_schema.statistics
                WHERE table_schema = %s
                AND table_name = %s
                GROUP BY index_name
            """, (schema, table))
            results = await cursor.fetchall()
            return [
                {
                    "name": row.get('index_name') or row.get('INDEX_NAME'),
                    "columns": (row.get('columns') or row.get('COLUMNS') or '').split(','),
                    "unique": (row.get('non_unique') or row.get('NON_UNIQUE')) == 0
                }
                for row in results
            ]

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute arbitrary SELECT query (read-only)

        Args:
            query: SQL query string
            *args: Query parameters (for parameterized queries)

        Returns:
            List of row dicts: [{"col1": val1, "col2": val2}, ...]

        Raises:
            ValueError: If query contains forbidden operations
            Exception: If query execution fails
        """
        # Security: Only allow SELECT queries
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
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args if args else None)
                results = await cursor.fetchall()
                return results  # DictCursor returns list of dicts directly
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    # =========================================================================
    # LINEAGE METADATA (Sprint 21)
    # =========================================================================

    async def get_views(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve SQL views metadata from MySQL (Sprint 21 Lineage).

        Args:
            schema: Schema/database name to query

        Returns:
            List of view dicts with name, definition, referenced_tables
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT
                        TABLE_NAME as view_name,
                        VIEW_DEFINITION as definition
                    FROM information_schema.VIEWS
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME
                """, (schema,))
                results = await cursor.fetchall()

                views = []
                for row in results:
                    view_def = row.get('definition') or row.get('VIEW_DEFINITION') or ''
                    # Extract referenced tables from FROM clause
                    referenced_tables = re.findall(
                        r'\bFROM\s+`?(\w+)`?',
                        view_def,
                        re.IGNORECASE
                    )
                    # Deduplicate
                    tables = list(set(referenced_tables))

                    views.append({
                        "name": row.get('view_name') or row.get('TABLE_NAME'),
                        "schema": schema,
                        "definition": view_def,
                        "referenced_tables": tables
                    })

                logger.info(f"[MySQL] Found {len(views)} views in schema {schema}")
                return views

        except Exception as e:
            logger.warning(f"Could not retrieve views for {schema}: {e}")
            return []

    async def get_triggers(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve triggers metadata from MySQL (Sprint 21 Lineage).

        Args:
            schema: Schema/database name to query

        Returns:
            List of trigger dicts with table_name, trigger_name, event, function_call
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT
                        EVENT_OBJECT_TABLE as table_name,
                        TRIGGER_NAME as trigger_name,
                        EVENT_MANIPULATION as event,
                        ACTION_STATEMENT as function_call
                    FROM information_schema.TRIGGERS
                    WHERE TRIGGER_SCHEMA = %s
                    ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME
                """, (schema,))
                results = await cursor.fetchall()

                triggers = []
                for row in results:
                    triggers.append({
                        "table_name": row.get('table_name') or row.get('EVENT_OBJECT_TABLE'),
                        "trigger_name": row.get('trigger_name') or row.get('TRIGGER_NAME'),
                        "event": row.get('event') or row.get('EVENT_MANIPULATION'),
                        "function_call": row.get('function_call') or row.get('ACTION_STATEMENT'),
                        "schema": schema
                    })

                logger.info(f"[MySQL] Found {len(triggers)} triggers in schema {schema}")
                return triggers

        except Exception as e:
            logger.warning(f"Could not retrieve triggers for {schema}: {e}")
            return []

    async def get_functions(self, schema: str) -> List[Dict[str, Any]]:
        """
        Retrieve stored procedures/functions metadata from MySQL (Sprint 21 Lineage).

        Args:
            schema: Schema/database name to query

        Returns:
            List of procedure/function dicts with name, type, definition
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT
                        ROUTINE_NAME as name,
                        ROUTINE_TYPE as type,
                        ROUTINE_DEFINITION as definition
                    FROM information_schema.ROUTINES
                    WHERE ROUTINE_SCHEMA = %s
                    AND ROUTINE_TYPE IN ('FUNCTION', 'PROCEDURE')
                    ORDER BY ROUTINE_NAME
                """, (schema,))
                results = await cursor.fetchall()

                functions = []
                for row in results:
                    functions.append({
                        "name": row.get('name') or row.get('ROUTINE_NAME'),
                        "type": row.get('type') or row.get('ROUTINE_TYPE'),
                        "definition": row.get('definition') or row.get('ROUTINE_DEFINITION') or '',
                        "schema": schema
                    })

                logger.info(f"[MySQL] Found {len(functions)} functions/procedures in schema {schema}")
                return functions

        except Exception as e:
            logger.warning(f"Could not retrieve functions for {schema}: {e}")
            return []

    # =========================================================================
    # V1.4 ENHANCED METRICS (Sprint 30 - MySQL support)
    # =========================================================================

    async def get_last_updated(self, schema: str, table: str) -> str:
        """
        Get last update timestamp for table.

        MySQL Strategy: Use information_schema.tables UPDATE_TIME

        Returns:
            ISO 8601 timestamp string or None
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT UPDATE_TIME
                    FROM information_schema.tables
                    WHERE TABLE_SCHEMA = %s
                    AND TABLE_NAME = %s
                """, (schema, table))
                result = await cursor.fetchone()
                if result and result.get('UPDATE_TIME'):
                    return result['UPDATE_TIME'].isoformat()
                return None
        except Exception as e:
            logger.warning(f"Could not get last_updated for {schema}.{table}: {e}")
            return None

    async def get_table_size(self, schema: str, table: str) -> Optional[int]:
        """
        Get total size of a table in bytes (data + indexes).

        Sprint 86B Niveau 2: Populate TableMetadata.size_bytes.
        Uses information_schema.TABLES DATA_LENGTH + INDEX_LENGTH.

        Returns:
            Size in bytes, or None if unavailable
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT DATA_LENGTH + INDEX_LENGTH as size_bytes
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """, (schema, table))
                result = await cursor.fetchone()
                if result and result.get('size_bytes') is not None:
                    return int(result['size_bytes'])
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
                # Parse referenced_table (format: "schema.table")
                ref_table_parts = fk['referenced_table'].split('.')
                if len(ref_table_parts) == 2:
                    ref_schema, ref_table = ref_table_parts
                else:
                    ref_schema = schema
                    ref_table = fk['referenced_table']

                # Query to count orphans (MySQL backtick syntax)
                query = f"""
                    SELECT COUNT(*) as orphan_count
                    FROM `{schema}`.`{table}` t
                    WHERE t.`{fk['column']}` IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM `{ref_schema}`.`{ref_table}` p
                        WHERE p.`{fk['ref_column']}` = t.`{fk['column']}`
                    )
                """

                async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(query)
                    result = await cursor.fetchone()
                    if result:
                        total_orphans += result.get('orphan_count', 0)

            except Exception as e:
                logger.warning(f"Could not count orphans for FK {fk.get('column')}: {e}")
                continue

        return total_orphans

    async def get_index_stats(self, schema: str, table: str) -> int:
        """
        Get index usage stats for table.

        MySQL: Use information_schema.statistics (index count as proxy)
        Note: MySQL doesn't track idx_scan like PostgreSQL

        Returns:
            Index count (as proxy for stats, 0 if no indexes)
        """
        try:
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT COUNT(DISTINCT INDEX_NAME) as index_count
                    FROM information_schema.statistics
                    WHERE TABLE_SCHEMA = %s
                    AND TABLE_NAME = %s
                """, (schema, table))
                result = await cursor.fetchone()
                return result.get('index_count', 0) if result else 0
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
            Count of invalid values (0 if validation not applicable)
        """
        invalid_count = 0

        # Early exit if empty table
        if row_count == 0:
            return 0

        # Sample size (max 10000 for performance)
        sample_size = min(row_count, 10000)

        for col in columns:
            col_name = col.get('name', '')
            col_name_lower = col_name.lower()

            try:
                # Email validation
                if 'email' in col_name_lower or 'mail' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM `{schema}`.`{table}`
                        WHERE `{col_name}` IS NOT NULL
                        AND `{col_name}` NOT REGEXP '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{{2,}}$'
                        LIMIT {sample_size}
                    """
                    async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query)
                        result = await cursor.fetchone()
                        if result:
                            invalid_count += result.get('invalid', 0)

                # Phone validation
                elif 'phone' in col_name_lower or 'tel' in col_name_lower:
                    query = f"""
                        SELECT COUNT(*) as invalid
                        FROM `{schema}`.`{table}`
                        WHERE `{col_name}` IS NOT NULL
                        AND `{col_name}` NOT REGEXP '^[+]?[0-9 \\\\-\\\\(\\\\)]{{8,}}$'
                        LIMIT {sample_size}
                    """
                    async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query)
                        result = await cursor.fetchone()
                        if result:
                            invalid_count += result.get('invalid', 0)

            except Exception as e:
                logger.warning(f"Type validation failed for {col_name}: {e}")
                continue

        return invalid_count

    async def close(self):
        """Fermeture connexion MySQL"""
        if self.connection:
            self.connection.close()

    async def _close_connection(self):
        """Alias pour compatibilité"""
        await self.close()
