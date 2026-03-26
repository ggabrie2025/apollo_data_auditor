"""
MongoDB Database Connector
Implementation for MongoDB document databases
"""

import re
from typing import Dict, Any, List, Optional
from motor import motor_asyncio
from .base import DatabaseConnector, ConnectorCapabilities
from .registry import register_connector
import logging

logger = logging.getLogger(__name__)


@register_connector
class MongoDBConnector(DatabaseConnector):
    """
    Connecteur MongoDB avec motor (async driver)

    Note: MongoDB is NoSQL, so concept of schemas/tables differs
    - "Schemas" → Databases
    - "Tables" → Collections
    - No formal columns, but we can infer from documents
    """

    METADATA = {
        "db_type": "mongodb",
        "name": "MongoDB",
        "default_port": 27017,
        "ports_to_scan": [27017, 27018],
        "requires": ["motor"]
    }

    CAPABILITIES = (
        ConnectorCapabilities.CAN_LIST |
        ConnectorCapabilities.CAN_READ |
        ConnectorCapabilities.CAN_SAMPLE |
        ConnectorCapabilities.CAN_SCAN_PII
    )

    async def test_connection(self) -> Dict[str, Any]:
        """Test connexion MongoDB"""
        try:
            # Build connection string
            username = self.config.get("username")
            password = self.config.get("password")
            host = self.config.get("host")
            port = self.config.get("port", 27017)
            database = self.config.get("database", "admin")

            # Get authSource (default to 'admin' for root users)
            auth_source = self.config.get("auth_source", "admin")

            if username and password:
                connection_string = f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource={auth_source}"
            else:
                connection_string = f"mongodb://{host}:{port}/{database}"

            # Establish connection
            self.connection = motor_asyncio.AsyncIOMotorClient(
                connection_string,
                serverSelectionTimeoutMS=self.timeout * 1000
            )

            # Test connection with ping
            await self.connection.admin.command('ping')

            # Count collections in database
            db = self.connection[database]
            collections = await db.list_collection_names()
            collections_count = len(collections)

            logger.info(f"MongoDB connection successful: {collections_count} collections detected")

            return {
                "success": True,
                "tables_count": collections_count,
                "message": f"Connected to MongoDB. {collections_count} collections detected.",
                "database_type": "mongodb"
            }

        except Exception as e:
            logger.error(f"MongoDB connection error: {e}")
            return {
                "success": False,
                "tables_count": 0,
                "message": "Connection failed",
                "error": str(e),
                "database_type": "mongodb"
            }

    async def is_read_only(self) -> bool:
        """
        Check if connection is read-only

        MongoDB: Check user roles
        """
        try:
            db = self.connection[self.config.get("database", "admin")]
            user_info = await db.command("usersInfo", {"user": self.config.get("username"), "db": db.name})

            if user_info and "users" in user_info and len(user_info["users"]) > 0:
                roles = user_info["users"][0].get("roles", [])
                write_roles = ["readWrite", "dbOwner", "root"]

                for role in roles:
                    if isinstance(role, dict):
                        if role.get("role") in write_roles:
                            return False
                    elif role in write_roles:
                        return False

                return True

            return False

        except Exception:
            return False

    async def _get_user_permissions(self) -> List[str]:
        """Get user permissions (MongoDB roles)"""
        try:
            db = self.connection[self.config.get("database", "admin")]
            user_info = await db.command("usersInfo", {"user": self.config.get("username"), "db": db.name})

            if user_info and "users" in user_info and len(user_info["users"]) > 0:
                roles = user_info["users"][0].get("roles", [])
                role_names = []
                for role in roles:
                    if isinstance(role, dict):
                        role_names.append(role.get("role", ""))
                    else:
                        role_names.append(str(role))
                return role_names

            return []

        except Exception:
            return []

    async def validate_permissions(self) -> Dict[str, Any]:
        """
        Validate MongoDB user permissions (read-only check)

        Returns:
            {
                "status": "ok|warning",
                "message": str,
                "forbidden_permissions": List[str]
            }
        """
        try:
            roles = await self._get_user_permissions()

            # Check for write roles
            write_roles = ["readWrite", "dbOwner", "root", "dbAdmin"]
            forbidden = []

            for role in roles:
                if role in write_roles:
                    forbidden.append(role)

            if forbidden:
                return {
                    "status": "warning",
                    "message": f"User has write permissions: {', '.join(forbidden)}",
                    "forbidden_permissions": forbidden
                }

            return {
                "status": "ok",
                "message": "User has read-only permissions",
                "forbidden_permissions": []
            }

        except Exception as e:
            logger.error(f"Error validating permissions: {e}")
            return {
                "status": "warning",
                "message": f"Could not validate permissions: {str(e)}",
                "forbidden_permissions": []
            }

    async def get_schemas(self) -> List[str]:
        """Liste tous les databases (MongoDB equivalent of schemas)"""
        try:
            db_list = await self.connection.list_database_names()
            # Exclude system databases
            return [db for db in db_list if db not in ['admin', 'local', 'config']]
        except Exception as e:
            logger.error(f"Error listing databases: {e}")
            return []

    async def get_tables(self, schema: str) -> List[str]:
        """Liste toutes les collections d'un database"""
        try:
            db = self.connection[schema]
            collections = await db.list_collection_names()
            # Exclude system collections
            return [c for c in collections if not c.startswith('system.')]
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            return []

    async def get_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Infer schema from documents (MongoDB has no formal schema)

        Sample first 100 documents to infer field structure
        """
        try:
            db = self.connection[schema]
            collection = db[table]

            # Sample documents
            cursor = collection.find().limit(100)
            documents = await cursor.to_list(length=100)

            if not documents:
                return []

            # Infer fields from sample
            all_fields = set()
            field_types = {}

            for doc in documents:
                for key, value in doc.items():
                    all_fields.add(key)
                    if key not in field_types:
                        field_types[key] = type(value).__name__

            columns = []
            for field in sorted(all_fields):
                columns.append({
                    "name": field,
                    "type": field_types.get(field, "unknown"),
                    "nullable": True,  # MongoDB fields are always optional
                    "default": None,
                    "primary_key": field == "_id"
                })

            return columns

        except Exception as e:
            logger.error(f"Error inferring schema: {e}")
            return []

    async def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """MongoDB always has _id as primary key"""
        return ["_id"]

    async def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """MongoDB has no formal foreign keys"""
        return []

    async def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Récupération indexes MongoDB"""
        try:
            db = self.connection[schema]
            collection = db[table]

            indexes_info = await collection.index_information()

            indexes = []
            for index_name, index_data in indexes_info.items():
                # Skip default _id_ index
                if index_name == "_id_":
                    continue

                columns = [key for key, _ in index_data.get("key", [])]
                unique = index_data.get("unique", False)

                indexes.append({
                    "name": index_name,
                    "columns": columns,
                    "unique": unique
                })

            return indexes

        except Exception as e:
            logger.error(f"Error getting indexes: {e}")
            return []

    async def get_table_size(self, schema: str, collection: str) -> Optional[int]:
        """
        Get total storage size of a collection in bytes.

        Sprint 86B Niveau 2: Populate TableMetadata.size_bytes.
        Uses collStats command storageSize (includes data + indexes).

        Args:
            schema: Database name (MongoDB uses database as schema)
            collection: Collection name

        Returns:
            Size in bytes, or None if unavailable
        """
        try:
            db = self.connection[schema]
            stats = await db.command('collStats', collection)
            return int(stats.get('storageSize', 0))
        except Exception as e:
            logger.warning(f"Could not get collection size for {schema}.{collection}: {e}")
            return None

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute query on MongoDB (limited SQL-to-MongoDB translation)

        MongoDB doesn't use SQL, so this method provides basic translation
        for common profiling queries (COUNT, SELECT).

        Args:
            query: SQL-like query string (limited support)
            *args: Query parameters (not used for MongoDB)

        Returns:
            List of result dicts

        Note: This is a simplified implementation for profiling compatibility.
              Complex SQL queries are not supported.
        """
        try:
            query_upper = query.strip().upper()

            # Security: Block write operations
            # Use word boundaries to avoid false positives (e.g., "update_events" contains "UPDATE")
            forbidden_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'GRANT', 'REVOKE']
            for keyword in forbidden_keywords:
                if re.search(r'\b' + keyword + r'\b', query_upper):
                    raise ValueError(f"Forbidden operation detected: {keyword}")

            # Extract collection name from query
            # Pattern: "FROM collection_name" or "FROM database.collection"
            from_match = re.search(r'FROM\s+(?:`?(\w+)`?\.)?`?(\w+)`?', query, re.IGNORECASE)
            if not from_match:
                logger.warning(f"Cannot parse collection name from query: {query}")
                return []

            database_name = from_match.group(1) or self.config.get("database")
            collection_name = from_match.group(2)

            db = self.connection[database_name]
            collection = db[collection_name]

            # Handle COUNT queries: "SELECT COUNT(*) as count FROM ..."
            if 'COUNT(' in query_upper:
                count = await collection.count_documents({})
                return [{"count": count}]

            # Handle simple SELECT with WHERE
            # Pattern: "SELECT * FROM collection WHERE field = value"
            where_match = re.search(r'WHERE\s+(\w+)\s*=\s*[\'"]?([^\'"]+)[\'"]?', query, re.IGNORECASE)
            filter_query = {}
            if where_match:
                field = where_match.group(1)
                value = where_match.group(2)
                # Try to convert value to appropriate type
                try:
                    if value.isdigit():
                        filter_query[field] = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        filter_query[field] = float(value)
                    else:
                        filter_query[field] = value
                except Exception:
                    filter_query[field] = value

            # Handle LIMIT
            limit = 1000  # Default limit
            limit_match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
            if limit_match:
                limit = int(limit_match.group(1))

            # Execute find query
            cursor = collection.find(filter_query).limit(limit)
            documents = await cursor.to_list(length=limit)

            # Convert MongoDB documents to dict format
            results = []
            for doc in documents:
                # Convert ObjectId to string
                doc_dict = {}
                for key, value in doc.items():
                    if key == '_id':
                        doc_dict[key] = str(value)
                    else:
                        doc_dict[key] = value
                results.append(doc_dict)

            return results

        except Exception as e:
            logger.error(f"MongoDB query execution error: {e}")
            logger.error(f"Query was: {query}")
            raise Exception(f"MongoDB query failed: {str(e)}")

    async def _close_connection(self):
        """Fermeture connexion MongoDB"""
        if self.connection:
            self.connection.close()

    async def close(self):
        """Libère la connexion MongoDB (interface DatabaseConnector)"""
        await self._close_connection()

    async def get_governance_metrics(self) -> Dict[str, float]:
        """Governance metrics for MongoDB — MongoDB-native equivalent of SQL get_governance_metrics().

        Returns 6 KPIs matching the cross-connector interface:
        - documentation_coverage : % collections with a JSON Schema validator
        - security_compliance    : % users without root-level roles (root, __system)
        - access_control         : % users with only read roles (no write/admin roles)
        - change_tracking        : 1.0 if replica set (change streams possible), 0.0 if standalone
        - table_size_distribution: 1 - CV(storageSize per collection), clamped [0, 1]
        - ai_act_article11       : ML collection name heuristic (same logic as PostgreSQL)
        """
        database = self.config.get("database", "admin")
        db = self.connection[database]

        # 1. documentation_coverage — % collections with $jsonSchema validator
        try:
            col_cursor = await db.list_collections()
            all_cols = await col_cursor.to_list(length=None)
            total = len(all_cols)
            documented = sum(
                1 for c in all_cols
                if c.get("options", {}).get("validator", {}).get("$jsonSchema")
            )
            documentation_coverage = (documented / total) if total > 0 else 0.0
        except Exception:
            documentation_coverage = 0.0

        # 2. security_compliance — % users without root-level roles
        try:
            user_info = await self.connection.admin.command("usersInfo", 1)
            users = user_info.get("users", [])
            root_roles = {"root", "__system", "clusterAdmin"}
            total = len(users)
            safe = sum(
                1 for u in users
                if not any(
                    (r.get("role") if isinstance(r, dict) else r) in root_roles
                    for r in u.get("roles", [])
                )
            )
            security_compliance = (safe / total) if total > 0 else 0.5
        except Exception:
            security_compliance = 0.5

        # 3. access_control — % users with only read-level roles
        try:
            user_info = await self.connection.admin.command("usersInfo", 1)
            users = user_info.get("users", [])
            write_roles = {"readWrite", "dbOwner", "dbAdmin", "root", "clusterAdmin", "__system"}
            total = len(users)
            read_only = sum(
                1 for u in users
                if not any(
                    (r.get("role") if isinstance(r, dict) else r) in write_roles
                    for r in u.get("roles", [])
                )
            )
            access_control = (read_only / total) if total > 0 else 0.5
        except Exception:
            access_control = 0.5

        # 4. change_tracking — 1.0 if replica set member (change streams enabled), 0.0 if standalone
        try:
            hello = await self.connection.admin.command("hello")
            change_tracking = 1.0 if hello.get("setName") else 0.0
        except Exception:
            change_tracking = 0.0

        # 5. table_size_distribution — 1 - CV(storageSize), clamped [0, 1]
        try:
            col_names = await db.list_collection_names()
            col_names = [c for c in col_names if not c.startswith("system.")]
            sizes = []
            for col_name in col_names:
                size = await self.get_table_size(database, col_name)
                if size is not None:
                    sizes.append(float(size))
            if len(sizes) >= 2:
                mean = sum(sizes) / len(sizes)
                std = (sum((x - mean) ** 2 for x in sizes) / len(sizes)) ** 0.5
                cv = (std / mean) if mean > 0 else 0.0
                table_size_distribution = max(0.0, min(1.0, 1.0 - cv))
            else:
                table_size_distribution = 1.0
        except Exception:
            table_size_distribution = 0.5

        # 6. ai_act_article11 — ML collection name heuristic (mirrors PostgreSQL)
        try:
            col_names = await db.list_collection_names()
            ML_TABLE_KEYWORDS = {"model", "prediction", "training", "feature", "ml_", "ai_", "inference"}
            VERSION_KEYWORDS = {"version", "registry", "run", "experiment"}
            LOG_TABLE_KEYWORDS = {"log", "audit", "history", "tracking"}
            names_lower = [c.lower() for c in col_names]
            score = 0.0
            ml_cols = [n for n in names_lower if any(kw in n for kw in ML_TABLE_KEYWORDS)]
            if ml_cols:
                score += 0.40
                versioned = [n for n in ml_cols if any(kw in n for kw in VERSION_KEYWORDS)]
                if versioned:
                    score += 0.30 * (len(versioned) / len(ml_cols))
            log_cols = [n for n in names_lower if any(kw in n for kw in LOG_TABLE_KEYWORDS)]
            if log_cols:
                score += 0.30
            ai_act_article11 = min(score, 1.0)
        except Exception:
            ai_act_article11 = 0.0

        return {
            "documentation_coverage": round(documentation_coverage, 4),
            "security_compliance": round(security_compliance, 4),
            "access_control": round(access_control, 4),
            "change_tracking": round(change_tracking, 4),
            "table_size_distribution": round(table_size_distribution, 4),
            "ai_act_article11": round(ai_act_article11, 4),
        }
