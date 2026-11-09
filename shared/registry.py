import os
import psycopg2
import yaml
from pathlib import Path
from psycopg2.extras import RealDictCursor
from typing import Optional, List, Dict, Any
import logging
import time
import json
import re
import fnmatch
import pandas as pd

class ExampleRegistry:
    """
    Registry for Markdown-based examples.
    Scans docs/examples/ for .md files with YAML front-matter.
    """
    FRONTMATTER_RE = re.compile(r'^---\s*(.*?)\s*---\s*(.*)$', re.DOTALL | re.MULTILINE)

    def __init__(self, examples_dir: str = "docs/examples"):
        self.examples_dir = examples_dir
        self.logger = logging.getLogger(__name__)

    def _parse_yaml_simple(self, yaml_str: str) -> Dict[str, Any]:
        """Simple YAML parser for front-matter."""
        metadata = {}
        for line in yaml_str.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value.startswith('[') and value.endswith(']'):
                    value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(',')]
                metadata[key] = value
        return metadata

    def get_all_examples(self) -> List[Dict[str, Any]]:
        """Scans the examples directory and returns metadata for all valid examples."""
        examples = []
        if not os.path.exists(self.examples_dir):
            return examples
        for filename in os.listdir(self.examples_dir):
            if filename.endswith(".md"):
                doc = self.get_example_by_path(os.path.join(self.examples_dir, filename))
                if doc:
                    examples.append(doc)
        return examples

    def get_example_by_id(self, example_id: str) -> Optional[Dict[str, Any]]:
        for ex in self.get_all_examples():
            if ex.get('id') == example_id:
                return ex
        return None

    def get_example_by_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = self.FRONTMATTER_RE.match(content)
            if not match: return None
            yaml_str, markdown_content = match.groups()
            metadata = self._parse_yaml_simple(yaml_str)
            if 'id' not in metadata: return None
            metadata['content'] = markdown_content.strip()
            metadata['file_path'] = file_path
            return metadata
        except Exception as e:
            self.logger.error(f"Error parsing example {file_path}: {e}")
            return None

class DocumentationRegistry:
    """
    Registry for all system documentation.
    Scans docs/ and categorizes content recursively.
    """
    FRONTMATTER_RE = re.compile(r'^---\s*(.*?)\s*---\s*(.*)$', re.DOTALL | re.MULTILINE)

    def __init__(self, docs_root: str = "docs"):
        self.docs_root = Path(docs_root).resolve()
        self.logger = logging.getLogger(__name__)
        self.exclude_patterns = self._load_config()

    def _load_config(self) -> List[str]:
        """Loads exclusion patterns from workspace.yaml."""
        workspace_file = Path("workspace.yaml")
        if workspace_file.exists():
            try:
                with open(workspace_file, "r") as f:
                    config = yaml.safe_load(f) or {}
                    return config.get("documentation", {}).get("exclude", [])
            except Exception as e:
                self.logger.warning(f"Failed to load workspace.yaml: {e}")
        return []

    def _should_include(self, path: Path) -> bool:
        """Determines if a file or directory should be included in the registry."""
        name = path.name
        # Skip hidden and internal files/folders
        if name.startswith(".") or name.startswith("_"):
            return False
        
        # Apply custom exclusion patterns
        rel_path = str(path.relative_to(self.docs_root))
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
                return False
        
        return True

    def _parse_yaml_simple(self, yaml_str: str) -> Dict[str, Any]:
        """Simple YAML parser for front-matter."""
        metadata = {}
        for line in yaml_str.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value.startswith('[') and value.endswith(']'):
                    value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(',')]
                metadata[key] = value
        return metadata

    def get_doc_tree(self) -> List[Dict[str, Any]]:
        """Returns a nested structure representing the documentation filesystem."""
        return self._build_nested_tree(self.docs_root)

    def get_sitemap(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns a flattened view of all documentation grouped by top-level pillars.
        """
        tree = self.get_doc_tree()
        sitemap = {}
        
        # Mapping of top-level folder names to human-readable Pillar names
        pillar_map = {
            "guides": "Operational Playbooks",
            "technical": "Service Architecture",
            "features": "System Evolution",
            "adapters": "Data Adapters",
            "examples": "Research Examples",
            "inventory": "Data Inventory"
        }

        for node in tree:
            if node["type"] == "directory":
                pillar_name = pillar_map.get(node["name"], node["name"].replace("-", " ").title())
                sitemap[pillar_name] = self._flatten_node(node)
            elif node["type"] == "file":
                # Handle top-level files like index.md
                pillar_name = "General"
                if pillar_name not in sitemap:
                    sitemap[pillar_name] = []
                sitemap[pillar_name].append(node)
        
        return sitemap

    def _flatten_node(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Helper to flatten a nested node structure into a list of files."""
        files = []
        if node["type"] == "file":
            files.append(node)
        elif "children" in node:
            for child in node["children"]:
                files.extend(self._flatten_node(child))
        return sorted(files, key=lambda x: x["title"])

    def _build_nested_tree(self, current_dir: Path) -> List[Dict[str, Any]]:
        """Recursively builds a tree of documentation nodes."""
        nodes = []
        if not current_dir.exists():
            return nodes

        for item in sorted(current_dir.iterdir()):
            if not self._should_include(item):
                continue

            if item.is_dir():
                children = self._build_nested_tree(item)
                if children:  # Only add directories that have docs
                    nodes.append({
                        "name": item.name,
                        "type": "directory",
                        "children": children
                    })
            elif item.suffix == ".md":
                doc = self.get_doc_by_path(str(item))
                if doc:
                    doc.pop('content', None)
                    nodes.append({
                        "name": item.name,
                        "type": "file",
                        "path_id": str(item.relative_to(self.docs_root)).replace(".md", "").replace("\\", "/"),
                        "title": doc.get("title", item.stem.replace("-", " ").title())
                    })
        return nodes

    def get_doc_by_id(self, category: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Deprecated: Use get_doc_by_path directly."""
        path = f"{category}/{doc_id}"
        return self.get_doc_by_path(path)

    def get_doc_by_path(self, rel_path: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document by its relative path from docs_root."""
        # Sanitize and validate path
        if not rel_path.endswith(".md"):
            file_path = self.docs_root / f"{rel_path}.md"
        else:
            file_path = self.docs_root / rel_path
        
        file_path = file_path.resolve()

        # Security check: Ensure path is within docs_root
        if not str(file_path).startswith(str(self.docs_root)):
            self.logger.warning(f"Blocked potential traversal attack: {file_path}")
            return None

        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = self.FRONTMATTER_RE.match(content)
            if not match:
                return {
                    "id": file_path.stem,
                    "title": file_path.stem.replace("-", " ").title(),
                    "content": content.strip(),
                    "file_path": str(file_path),
                    "path_id": str(file_path.relative_to(self.docs_root)).replace(".md", "").replace("\\", "/")
                }
            yaml_str, markdown_content = match.groups()
            metadata = self._parse_yaml_simple(yaml_str)
            if 'id' not in metadata: metadata['id'] = file_path.stem
            if 'title' not in metadata: metadata['title'] = metadata['id'].replace("-", " ").title()
            metadata['content'] = markdown_content.strip()
            metadata['file_path'] = str(file_path)
            metadata['path_id'] = str(file_path.relative_to(self.docs_root)).replace(".md", "").replace("\\", "/")
            return metadata
        except Exception as e:
            self.logger.error(f"Error parsing doc {file_path}: {e}")
            return None

    def search_docs(self, query: str) -> List[Dict[str, Any]]:
        """Recursively searches all documentation."""
        results = []
        query = query.lower()
        
        for item in self.docs_root.rglob("*.md"):
            if not self._should_include(item):
                continue
                
            doc = self.get_doc_by_path(str(item))
            if doc and (query in doc.get('title', '').lower() or 
                       query in doc.get('id', '').lower() or
                       query in doc.get('content', '').lower()):
                doc.pop('content', None)
                results.append(doc)
        return results

class MetadataRegistry:
    """
    Interface for the PostgreSQL Metadata Registry.
    Handles asset registration, lineage tracking, and column semantics.
    """

    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "postgres")
        self.port = os.getenv("POSTGRES_PORT", "5432")
        self.user = os.getenv("POSTGRES_USER", "admin")
        self.password = os.getenv("POSTGRES_PASSWORD", "admin_password")
        self.dbname = os.getenv("POSTGRES_DB", "metadata")
        self.logger = logging.getLogger(__name__)

    def _get_connection(self, max_retries: int = 5, initial_delay: float = 1.0):
        retries = 0
        delay = initial_delay
        while retries < max_retries:
            try:
                return psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    dbname=self.dbname
                )
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                retries += 1
                if retries == max_retries:
                    self.logger.error(f"Failed to connect to database after {max_retries} attempts: {e}")
                    raise
                self.logger.warning(f"Database connection failed: {e}. Retrying in {delay}s... ({retries}/{max_retries})")
                time.sleep(delay)
                delay *= 2

    def _sanitize_label(self, label: Optional[str], max_length: int = 100) -> str:
        """Sanitizes label for safety, ensuring it conforms to PostgreSQL VARCHAR(100) bounds."""
        if not label:
            return "main"
        sanitized = re.sub(r'[^a-z0-9_]', '_', str(label).lower()).strip('_')
        sanitized = re.sub(r'_+', '_', sanitized)
        if not sanitized:
            return "main"
        return sanitized[:max_length].rstrip('_')

    def register_asset(self, symbol: str, library: str, label: str = "main", description: Optional[str] = None, frequency: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Ensures an asset is registered in the registry. Returns the asset ID.
        """
        import json
        label = self._sanitize_label(label)
        metadata_json = json.dumps(metadata) if metadata else '{}'
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO assets (symbol, library, label, description, frequency, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (symbol, library, label) DO UPDATE
                    SET description = EXCLUDED.description, 
                        frequency = COALESCE(EXCLUDED.frequency, assets.frequency),
                        metadata = COALESCE(assets.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id;
                    """,
                    (symbol, library, label, description, frequency, metadata_json)
                )
                return cur.fetchone()[0]

    def start_lineage(self, asset_id: int, dagster_run_id: str, batch_id: Optional[str] = None) -> int:
        """
        Creates a 'pending' lineage record. Returns the lineage log ID.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lineage_log (asset_id, dagster_run_id, batch_id, status)
                    VALUES (%s, %s, %s, 'pending')
                    RETURNING id;
                    """,
                    (asset_id, dagster_run_id, batch_id)
                )
                return cur.fetchone()[0]

    def commit_lineage(self, lineage_id: int, version_id: Optional[int] = None, batch_id: Optional[str] = None):
        """
        Marks a lineage record as 'committed' and associates it with a version/batch.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Update lineage log
                if batch_id:
                    cur.execute(
                        """
                        UPDATE lineage_log
                        SET version_id = COALESCE(%s, version_id), 
                            batch_id = %s,
                            status = 'committed', 
                            created_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
                        """,
                        (version_id, batch_id, lineage_id)
                    )
                else:
                    cur.execute(
                        """
                        UPDATE lineage_log
                        SET version_id = %s, status = 'committed', created_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
                        """,
                        (version_id, lineage_id)
                    )
                
                # Update current_version in assets if provided
                if version_id:
                    cur.execute(
                        """
                        UPDATE assets
                        SET current_version = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = (SELECT asset_id FROM lineage_log WHERE id = %s);
                        """,
                        (version_id, lineage_id)
                    )

    def get_batches_for_version(self, symbol: str, library: str, version_id: Optional[int] = None, label: str = "main") -> List[str]:
        """
        Resolves a symbol/version into a list of valid batch_ids for PIT reconstruction.
        If version_id is None, returns batches for the latest committed version.
        """
        label = self._sanitize_label(label)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if version_id is None:
                    # Get latest version_id first
                    cur.execute(
                        "SELECT current_version FROM assets WHERE symbol = %s AND library = %s AND label = %s",
                        (symbol, library, label)
                    )
                    res = cur.fetchone()
                    if not res or res[0] is None:
                        return []
                    version_id = res[0]

                # Fetch all unique batch_ids committed up to this version for this asset
                cur.execute(
                    """
                    SELECT DISTINCT batch_id FROM lineage_log
                    WHERE asset_id = (SELECT id FROM assets WHERE symbol = %s AND library = %s AND label = %s)
                    AND version_id <= %s
                    AND status = 'committed'
                    AND batch_id IS NOT NULL;
                    """,
                    (symbol, library, label, version_id)
                )
                return [str(row[0]) for row in cur.fetchall()]

    def fail_lineage(self, lineage_id: int, error_message: str):
        """
        Marks a lineage record as 'failed'.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE lineage_log
                    SET status = 'failed', metadata = jsonb_set(metadata, '{error}', %s)
                    WHERE id = %s;
                    """,
                    (f'"{error_message}"', lineage_id)
                )

    def register_columns(self, asset_id: int, columns: List[Dict[str, Any]]):
        """
        Registers or updates column metadata for an asset.
        columns should be a list of dicts: {'name': str, 'description': str, 'unit': str, 'semantic_type': str}
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for col in columns:
                    cur.execute(
                        """
                        INSERT INTO asset_columns (asset_id, name, description, unit, semantic_type)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (asset_id, name) DO NOTHING;
                        """,
                        (asset_id, col['name'], col.get('description'), col.get('unit'), col.get('semantic_type'))
                    )

    def get_asset_lineage(self, symbol: str, library: str) -> List[Dict[str, Any]]:
        """
        Retrieves the full lineage history for an asset.
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT l.* FROM lineage_log l
                    JOIN assets a ON l.asset_id = a.id
                    WHERE a.symbol = %s AND a.library = %s
                    ORDER BY l.created_at DESC;
                    """,
                    (symbol, library)
                )
                return cur.fetchall()

    def search_assets(self, query: str) -> List[Dict[str, Any]]:
        """Search assets by symbol or description."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, symbol, library, description 
                    FROM assets 
                    WHERE symbol ILIKE %s OR description ILIKE %s
                    LIMIT 20;
                    """,
                    (f'%{query}%', f'%{query}%')
                )
                return cur.fetchall()

    def get_asset_manifest(self, symbol: str, lineage_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get storage coordinates and column metadata for an asset."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Fetch asset and lineage info
                if lineage_id:
                    cur.execute(
                        """
                        SELECT a.id as asset_id, a.symbol, a.library, l.version_id, l.id as lineage_id, l.dagster_run_id
                        FROM assets a
                        JOIN lineage_log l ON a.id = l.asset_id
                        WHERE a.symbol = %s AND l.id = %s AND l.status = 'committed';
                        """,
                        (symbol, lineage_id)
                    )
                else:
                    cur.execute(
                        """
                        SELECT a.id as asset_id, a.symbol, a.library, l.version_id, l.id as lineage_id, l.dagster_run_id
                        FROM assets a
                        JOIN lineage_log l ON a.id = l.asset_id
                        WHERE a.symbol = %s AND l.status = 'committed'
                        ORDER BY l.created_at DESC LIMIT 1;
                        """,
                        (symbol,)
                    )
                
                manifest = cur.fetchone()
                if not manifest:
                    return None
                
                # 2. Fetch columns
                cur.execute(
                    "SELECT name, description, unit, semantic_type FROM asset_columns WHERE asset_id = %s",
                    (manifest['asset_id'],)
                )
                manifest['columns'] = {col['name']: col for col in cur.fetchall()}
                return manifest

    def add_source(
        self,
        adapter_type: str,
        identifier: str,
        label: str = "main",
        config: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ):
        """Registers a new data source in the inventory."""
        label = self._sanitize_label(label)
        payload = dict(config or {})
        if description:
            payload["description"] = description
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_inventory (adapter_type, identifier, label, config)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (adapter_type, identifier, label) DO UPDATE
                    SET config = EXCLUDED.config, is_active = TRUE;
                    """,
                    (adapter_type, identifier, label, json.dumps(payload))
                )

    def get_active_sources(self) -> List[Dict[str, Any]]:
        """Retrieves all active data sources from the inventory."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT adapter_type, identifier, label, config FROM source_inventory WHERE is_active = TRUE")
                return cur.fetchall()

    def deactivate_all_sources(self):
        """Marks all sources as inactive. Called before YAML sync to ensure
        declarative behavior: only sources present in sources.yaml remain active."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE source_inventory SET is_active = FALSE")

    def sync_sources_declarative(self, sources_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Declarative synchronization of sources into PostgreSQL source_inventory protected
        by a PostgreSQL non-blocking session advisory lock (lock key 742918).
        If another process is already synchronizing, returns {'status': 'skipped', 'synced': 0, 'reason': 'locked'}.
        Otherwise deactivates all sources and upserts the provided entries within a single atomic transaction.
        """
        advisory_lock_id = 742918
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s);", (advisory_lock_id,))
                locked = cur.fetchone()[0]
                if not locked:
                    self.logger.info("Source synchronization already in progress by another process. Skipping.")
                    return {"status": "skipped", "synced": 0, "reason": "locked"}

                try:
                    cur.execute("UPDATE source_inventory SET is_active = FALSE;")
                    synced = 0
                    for entry in sources_entries:
                        adapter_type = entry.get("adapter_type")
                        identifier = entry.get("identifier")
                        label = self._sanitize_label(entry.get("label", "main"))
                        config = dict(entry.get("config") or {})
                        description = entry.get("description")
                        if description:
                            config["description"] = description

                        cur.execute(
                            """
                            INSERT INTO source_inventory (adapter_type, identifier, label, config)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (adapter_type, identifier, label) DO UPDATE
                            SET config = EXCLUDED.config, is_active = TRUE;
                            """,
                            (adapter_type, identifier, label, json.dumps(config)),
                        )
                        synced += 1
                    conn.commit()
                    return {"status": "success", "synced": synced}
                finally:
                    cur.execute("SELECT pg_advisory_unlock(%s);", (advisory_lock_id,))



    def get_last_observed_timestamp(self, symbol: str, library: str, label: str = "main") -> Optional[pd.Timestamp]:
        """Retrieves the latest observed timestamp for an asset."""
        label = self._sanitize_label(label)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_observed_timestamp FROM assets WHERE symbol = %s AND library = %s AND label = %s",
                    (symbol, library, label)
                )
                res = cur.fetchone()
                if res and res[0]:
                    return pd.Timestamp(res[0])
                return None

    def update_last_observed_timestamp(self, symbol: str, library: str, timestamp: pd.Timestamp, label: str = "main"):
        """Updates the latest observed timestamp for an asset."""
        label = self._sanitize_label(label)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE assets 
                    SET last_observed_timestamp = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND library = %s AND label = %s;
                    """,
                    (timestamp, symbol, library, label)
                )

    def get_all_assets(self) -> List[Dict[str, Any]]:
        """Retrieves all registered assets across all libraries."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM assets ORDER BY library, symbol, label")
                return cur.fetchall()

    def get_lineage_pairs(self) -> List[Dict[str, Any]]:
        """
        Groups assets by (symbol, label) and returns their bronze and silver metadata as pairs.
        Used for the Unified Lineage Dashboard.
        """
        assets = self.get_all_assets()
        pairs = {}
        
        for asset in assets:
            key = (asset['symbol'], asset.get('label', 'main'))
            if key not in pairs:
                pairs[key] = {
                    "symbol": asset['symbol'],
                    "label": asset.get('label', 'main'),
                    "bronze": None,
                    "silver": None
                }
            
            lib = asset['library'].lower()
            if lib in ["bronze", "silver"]:
                pairs[key][lib] = asset
        
        # Convert to list
        return list(pairs.values())

    def delete_asset_metadata(self, symbol: str, library: str, label: str = "main"):
        """
        Hard deletes an asset from the metadata registry.
        Foreign key constraints with ON DELETE CASCADE will handle child records.
        """
        label = self._sanitize_label(label)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM assets WHERE symbol = %s AND library = %s AND label = %s", (symbol, library, label))
                if cur.rowcount == 0:
                    raise ValueError(f"Asset {symbol} ({label}) not found in library {library}")
