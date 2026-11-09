import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs
import pandas as pd

from shared.adapters import BaseAdapter
from shared.models import TerminalDataFrameMetadata, BronzePayload
from shared.http_client import HttpClient
from shared.metrics import TERMINAL_ADAPTER_MESSAGES_TOTAL

logger = logging.getLogger("adapters.macro.moneycontrol")


class MoneycontrolAdapter(BaseAdapter):
    """
    Adapter for Moneycontrol Economic Calendar statistical time-series data.
    Accepts full API URLs containing query parameters (e.g. calendarId=1414914&duration=).
    """

    def __init__(self, url: str):
        self.raw_url = url
        self.calendar_id, self.default_params = self._parse_url(url)
        self.client = HttpClient(base_url="https://api.moneycontrol.com/mcapi/v1/ecalendar/")

    def _parse_url(self, url: str) -> tuple[str, Dict[str, Any]]:
        """Extract calendarId and default query parameters from URL or query string."""
        if not url:
            raise ValueError("Moneycontrol URL or calendarId must be provided.")

        # Check if url is directly an integer / numeric string calendar ID
        if url.isdigit():
            return url, {"calendarId": url, "duration": ""}

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        calendar_id_list = params.get("calendarId") or params.get("calendar_id")
        if not calendar_id_list or not calendar_id_list[0]:
            raise ValueError(f"Could not extract 'calendarId' from provided URL: {url}")

        calendar_id = calendar_id_list[0]
        extracted_params = {k: v[0] for k, v in params.items()}
        if "duration" not in extracted_params:
            extracted_params["duration"] = ""

        return calendar_id, extracted_params

    @property
    def source_name(self) -> str:
        return "Moneycontrol"

    @property
    def identifier(self) -> str:
        return self.calendar_id

    @classmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "duration": {"type": str, "default": ""},
        }

    def fetch_raw(self, **kwargs) -> BronzePayload:
        allowed_keys = {"calendarId", "duration"} | set(self.get_parameter_schema().keys())
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_keys}

        params = {
            **self.default_params,
            "calendarId": self.calendar_id,
            **filtered_kwargs,
        }

        # Merge defaults from schema if not provided
        schema_defaults = {k: v.get("default") for k, v in self.get_parameter_schema().items()}
        for k, v in schema_defaults.items():
            if k not in params and v is not None:
                params[k] = v

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://www.moneycontrol.com",
            "Referer": "https://www.moneycontrol.com/",
            "auth-token": "-1",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            **kwargs.get("headers", {}),
        }

        response = self.client.get("get-stats-data", params=params, headers=headers)
        raw_text = response.text

        # Increment ingestion counter
        try:
            data = response.json()
            observations = data.get("data", [])
            TERMINAL_ADAPTER_MESSAGES_TOTAL.labels(
                source=self.source_name, entity_id=self.identifier
            ).inc(len(observations))
        except Exception:
            pass

        return BronzePayload(
            protocol="http",
            origin_metadata={"url": str(response.url), "method": response.request.method},
            execution_metadata={
                "status_code": response.status_code,
                "headers": dict(response.headers),
            },
            payload_format="json",
            raw_payload=raw_text,
        )

    def to_silver(self, payload: BronzePayload, batch_id: Optional[str] = None) -> pd.DataFrame:
        """
        Normalize Moneycontrol raw data into the canonical Silver layer format.
        """
        from domains.macro.transformers import normalize_macro_data
        from domains.macro.models import SilverMacroObservations

        try:
            raw_data = json.loads(payload.raw_payload)
        except Exception as e:
            logger.error(f"Failed to parse raw JSON payload: {e}")
            return pd.DataFrame(columns=list(SilverMacroObservations.model_fields.keys()))

        observations = raw_data.get("data", [])
        if not observations or not isinstance(observations, list):
            return pd.DataFrame(columns=list(SilverMacroObservations.model_fields.keys()))

        bronze_ref = payload.payload_checksum or "unknown"
        lineage = {
            "source_version": payload.origin_metadata.get("url", "unknown"),
            "bronze_reference": bronze_ref,
            "batch_id": batch_id,
        }

        records_read = len(observations)
        records_transformed = 0
        records_rejected = 0
        rejection_reasons: Dict[str, int] = {}

        validated_records = []
        for row in observations:
            if not isinstance(row, dict):
                records_rejected += 1
                rejection_reasons["InvalidRowFormat"] = rejection_reasons.get("InvalidRowFormat", 0) + 1
                continue

            obs_date = row.get("date")
            obs_value = row.get("value")

            if obs_date is None or obs_value is None:
                records_rejected += 1
                rejection_reasons["MissingFields"] = rejection_reasons.get("MissingFields", 0) + 1
                continue

            transformed_row = {
                "series_id": self.identifier,
                "observation_date": obs_date,
                "value": obs_value,
                "unit": "INDEX",
            }

            try:
                validated_model = normalize_macro_data(transformed_row, lineage)
                validated_records.append(validated_model.model_dump())
                records_transformed += 1
            except Exception as e:
                records_rejected += 1
                exc_type = type(e).__name__
                rejection_reasons[exc_type] = rejection_reasons.get(exc_type, 0) + 1
                logger.warning(
                    "Validation failed for record. Source: %s, Domain: %s, Batch ID: %s, Bronze Record ID: %s, Exception Type: %s, Message: %s",
                    self.source_name,
                    "macro",
                    batch_id or "N/A",
                    bronze_ref,
                    exc_type,
                    str(e),
                )
                continue

        logger.info(
            "Transformation summary for %s (%s) - Read: %d, Transformed: %d, Rejected: %d, Rejection Reasons: %s, Written: %d",
            self.source_name,
            self.identifier,
            records_read,
            records_transformed,
            records_rejected,
            json.dumps(rejection_reasons),
            records_transformed,
        )

        silver_df = pd.DataFrame(validated_records)

        if not silver_df.empty:
            silver_df = silver_df.set_index("observation_date", drop=False)
            silver_df.index.name = "timestamp"

        return silver_df

    def get_metadata(self) -> TerminalDataFrameMetadata:
        metadata = TerminalDataFrameMetadata(
            name=f"Moneycontrol - {self.identifier}",
            description="Moneycontrol economic calendar statistical time series.",
            frequency="monthly",
            source=self.source_name,
            is_seasonally_adjusted=False,
        )
        metadata.metadata["columns"] = [
            {
                "name": "value",
                "unit": "INDEX",
                "semantic_type": "value",
                "description": "Numeric observation value",
            }
        ]
        return metadata
