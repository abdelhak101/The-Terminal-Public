from pathlib import Path
import dotenv
def find_env_file(start_path: Path) -> Path:
    for parent in start_path.resolve().parents:
        env_path = parent / ".env"
        if env_path.exists():
            return env_path
    return start_path.parent / ".env"

# Load environment variables in all parent/child processes, overriding container defaults
dotenv.load_dotenv(find_env_file(Path(__file__)), override=True)

from dagster import Definitions, multiprocess_executor
from adapters.factory import create_adapter_assets
from adapters import ADAPTER_MAP
from shared.clickhouse import ClickHouseIOManager
from shared.registry import MetadataRegistry
from infrastructure.docker.orchestration.jobs import register_source_job
import os
import sys
import logging
import yaml

logger = logging.getLogger(__name__)

def load_dynamic_assets():
    """Queries the Metadata Registry for active sources and instantiates their assets."""
    registry = MetadataRegistry()
    all_assets = []
    
    try:
        sources = registry.get_active_sources()
        for src in sources:
            adapter_type = src["adapter_type"]
            identifier = src["identifier"]
            label = src.get("label", "main")
            config = src.get("config", {})
            
            if adapter_type in ADAPTER_MAP:
                # Instantiate adapter with identifier and optional config
                # We assume the first argument is the identifier (ticker or series_id)
                adapter_cls = ADAPTER_MAP[adapter_type]
                adapter = adapter_cls(identifier) # identifier is always the first arg
                all_assets.extend(create_adapter_assets(adapter, config, label=label, adapter_type=adapter_type))
            else:
                logger.warning(f"Unknown adapter type '{adapter_type}' for identifier '{identifier}'")
    except Exception as e:
        logger.error(f"Failed to load dynamic assets from registry: {e}")
        # In a real scenario, we might want to return some 'static' fallback assets
        # or just an empty list so Dagster starts but shows a warning.
    
    return all_assets


def is_step_worker() -> bool:
    """Detects whether the current Python process is a Dagster step worker."""
    return any("execute_step" in arg for arg in sys.argv) or bool(os.getenv("DAGSTER_STEP_WORKER"))


def sync_sources_from_yaml():
    """Syncs config/sources.yaml into PostgreSQL source_inventory.

    Declarative: uses PostgreSQL session advisory locking via
    registry.sync_sources_declarative to safely synchronize sources.
    If sources.yaml is missing or unparseable, logs a warning and skips
    sync to preserve existing PG state.
    """
    sources_path = Path(os.getenv(
        "SOURCES_YAML_PATH",
        Path(os.getenv("PYTHONPATH", ".")) / "config" / "sources.yaml"
    ))

    if not sources_path.exists():
        logger.warning(f"sources.yaml not found at {sources_path} — skipping sync")
        return

    try:
        with open(sources_path, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse sources.yaml: {e} — skipping sync")
        return

    if not data or not isinstance(data.get("sources"), list):
        logger.warning("sources.yaml has no 'sources' list — skipping sync")
        return

    try:
        entries = data["sources"]
        valid_entries = []
        skipped = 0

        for entry in entries:
            adapter_type = entry.get("adapter_type")
            identifier = entry.get("identifier")

            if not adapter_type or not identifier:
                logger.error(f"Source entry missing adapter_type or identifier: {entry}")
                skipped += 1
                continue

            if adapter_type not in ADAPTER_MAP:
                logger.error(f"Unknown adapter_type '{adapter_type}' for '{identifier}' — skipping")
                skipped += 1
                continue

            # Validate config keys against adapter schema
            config = entry.get("config", {})
            adapter_cls = ADAPTER_MAP[adapter_type]
            schema = adapter_cls.get_parameter_schema()
            invalid_keys = [k for k in config if k not in schema]
            if invalid_keys:
                logger.error(
                    f"Invalid config keys {invalid_keys} for "
                    f"'{adapter_type}/{identifier}' — skipping"
                )
                skipped += 1
                continue

            valid_entries.append(entry)

        registry = MetadataRegistry()
        result = registry.sync_sources_declarative(valid_entries)
        if result.get("status") == "skipped":
            logger.info("Source synchronization skipped (advisory lock held by another process)")
        else:
            logger.info(
                f"Source sync complete: {result.get('synced', 0)} synced, {skipped} skipped "
                f"(from {len(entries)} entries in sources.yaml)"
            )
    except Exception as e:
        logger.error(f"Failed to sync sources from YAML to registry: {e}")


# Only sync sources from YAML in parent/coordinator processes, never in worker subprocesses
if not is_step_worker():
    sync_sources_from_yaml()

max_concurrent_steps = int(os.getenv("DAGSTER_MAX_CONCURRENT_STEPS", "4"))
default_executor = multiprocess_executor.configured({"max_concurrent": max_concurrent_steps})

defs = Definitions(
    assets=load_dynamic_assets(),
    jobs=[register_source_job],
    resources={
        "io_manager": ClickHouseIOManager(),
    },
    executor=default_executor,
)
