from dagster import job, op, Config
from shared.registry import MetadataRegistry
from adapters import ADAPTER_MAP
from typing import Dict, Any

class RegistrationConfig(Config):
    adapter_type: str
    identifier: str
    label: str = "main"
    config: Dict[str, Any] = {}

@op
def register_source_op(config: RegistrationConfig):
    registry = MetadataRegistry()
    
    if config.adapter_type not in ADAPTER_MAP:
        raise ValueError(f"Unknown adapter type: {config.adapter_type}")
    
    adapter_cls = ADAPTER_MAP[config.adapter_type]
    schema = adapter_cls.get_parameter_schema()
    
    # Validate provided config keys
    for key in config.config.keys():
        if key not in schema:
            raise ValueError(f"Invalid parameter '{key}' for adapter '{config.adapter_type}'")
    
    registry.add_source(
        adapter_type=config.adapter_type,
        identifier=config.identifier,
        label=config.label,
        config=config.config
    )

@job
def register_source_job():
    register_source_op()
