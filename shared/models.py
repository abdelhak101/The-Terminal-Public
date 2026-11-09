from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class SilverBase(BaseModel):
    """Base model for all Silver domain schemas, ensuring consistent lineage and versioning."""
    schema_version: str = Field("v1", description="The version of this specific domain schema.")
    transformation_version: str = Field("v1", description="The version of the transformation logic used to create this record.")
    source_version: str = Field(..., description="The version or timestamp of the underlying source data.")
    bronze_record_id: str = Field(..., description="A reference (e.g. checksum or ID) to the exact Bronze payload this was derived from.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional domain-specific context.")


class TerminalDataFrameMetadata(BaseModel):
    """AI-Native metadata for a dataset."""
    name: str = Field(..., description="The human-readable name of the metric.")
    description: str = Field(..., description="Detailed explanation for AI agents and researchers.")
    frequency: str = Field(..., description="Observation frequency (e.g., 'daily', 'monthly', 'real-time').")
    source: str = Field(..., description="The provider name (e.g., 'FRED', 'Yahoo').")
    is_seasonally_adjusted: bool = Field(default=False)
    schema_version: str = Field("v1")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or column schemas.")

class BronzePayload(BaseModel):
    """Protocol-agnostic wrapper for raw data payloads destined for the Bronze layer."""
    protocol: str = Field(..., description="The protocol used to fetch the data (e.g., 'http', 's3', 'ftp').")
    origin_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the source (e.g., {'url': '...', 'method': 'GET'}).")
    execution_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the execution result (e.g., {'status_code': 200, 'headers': {...}}).")
    payload_format: str = Field(..., description="The format of the raw payload (e.g., 'json', 'csv', 'xml').")
    raw_payload: str = Field(..., description="The completely unmodified, unparsed raw string/bytes from the source.")
    payload_checksum: Optional[str] = Field(None, description="SHA-256 hash of the raw payload for integrity verification.")
