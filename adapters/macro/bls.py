import os
import logging
import pandas as pd
from typing import Any, Dict, List, Optional
import json
from shared.adapters import SearchableAdapter, SearchResult
from shared.models import TerminalDataFrameMetadata, BronzePayload
from shared.http_client import HttpClient
from shared.metrics import TERMINAL_ADAPTER_MESSAGES_TOTAL

logger = logging.getLogger(__name__)

class BLSAdapter(SearchableAdapter[Dict[str, Any]]):
    """
    Adapter for Bureau of Labor Statistics (BLS) API (V1/V2).
    """

    # Class-level mappings for popular indicators to their BLS Series IDs
    SERIES_MAPPING = {
        # Consumer Price Index (CPI)
        "CPI_URBAN": "CUUR0000SA0",
        "CPI_CORE": "CUUR0000SA0L1E",
        "CPI_FOOD": "CUUR0000SAF1",
        "CPI_ENERGY": "CUUR0000SA0E",
        "CPI_SHELTER": "CUUR0000SAH1",
        "CPI_MEDICAL": "CUUR0000SAM",
        "CPI_APPAREL": "CUUR0000SAA",
        "CPI_TRANSPORTATION": "CUUR0000SAT",
        "CPI_EDUCATION": "CUUR0000SAE1",
        "CPI_W": "CWUR0000SA0",
        # Employment
        "UNEMPLOYMENT_RATE": "LNS14000000",
        "UNEMPLOYMENT_U6": "LNS13327709",
        "PAYROLLS": "CES0000000001",
        "PAYROLLS_PRIVATE": "CES0500000001",
        "PAYROLLS_MANUFACTURING": "CES3000000001",
        "PAYROLLS_GOVERNMENT": "CES9000000001",
        "PAYROLLS_RETAIL": "CES4200000001",
        "LABOR_FORCE_PARTICIPATION": "LNS11300000",
        "EMPLOYMENT_POPULATION_RATIO": "LNS12300000",
        "AVG_HOURLY_EARNINGS": "CES0500000003",
        "AVG_HOURLY_EARNINGS_PROD": "CES0500000008",
        "AVG_WEEKLY_HOURS": "CES0500000002",
        # Producer Prices
        "PPI_COMMODITY": "WPUFD4",  # Legacy alias
        "PPI_FINAL_DEMAND": "WPUFD4",
        "PPI_FINAL_DEMAND_GOODS": "WPUFD41",
        "PPI_FINAL_DEMAND_SERVICES": "WPUFD42",
        # JOLTS
        "JOLTS_OPENINGS": "JTS000000000000000JOR",
        "JOLTS_HIRES": "JTS000000000000000HIR",
        "JOLTS_QUITS": "JTS000000000000000QUR",
        "JOLTS_SEPARATIONS": "JTS000000000000000TSR",
        # Productivity
        "PRODUCTIVITY_OUTPUT": "PRS85006092",
        "UNIT_LABOR_COSTS": "PRS85006112",
        # Import/Export
        "IMPORT_PRICE_INDEX": "EIUIR",
        "EXPORT_PRICE_INDEX": "EIUIQ",
    }

    # Rich metadata catalog for search discovery
    SEARCH_CATALOG = {
        "CPI_URBAN": {
            "name": "CPI-U All Items",
            "description": "Consumer Price Index for All Urban Consumers, all items. Primary U.S. inflation measure.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_CORE": {
            "name": "CPI-U Core (Less Food & Energy)",
            "description": "Consumer Price Index excluding volatile food and energy components.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_FOOD": {
            "name": "CPI-U Food",
            "description": "Consumer Price Index for food items.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_ENERGY": {
            "name": "CPI-U Energy",
            "description": "Consumer Price Index for energy commodities and services.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_SHELTER": {
            "name": "CPI-U Shelter",
            "description": "Consumer Price Index for shelter (rent, owners equivalent rent). Largest CPI component.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_MEDICAL": {
            "name": "CPI-U Medical Care",
            "description": "Consumer Price Index for medical care services and commodities.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_APPAREL": {
            "name": "CPI-U Apparel",
            "description": "Consumer Price Index for apparel (clothing and footwear).",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_TRANSPORTATION": {
            "name": "CPI-U Transportation",
            "description": "Consumer Price Index for transportation (vehicles, fuel, public transit).",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_EDUCATION": {
            "name": "CPI-U Education & Communication",
            "description": "Consumer Price Index for education and communication services.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "CPI_W": {
            "name": "CPI-W All Items (Wage Earners)",
            "description": "Consumer Price Index for Urban Wage Earners and Clerical Workers. Used for Social Security COLA adjustments.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "UNEMPLOYMENT_RATE": {
            "name": "Unemployment Rate (U-3)",
            "description": "Total unemployed as percent of civilian labor force. Headline unemployment measure.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "UNEMPLOYMENT_U6": {
            "name": "Unemployment Rate (U-6)",
            "description": "Total unemployed plus marginally attached workers plus employed part-time for economic reasons.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "PAYROLLS": {
            "name": "Total Nonfarm Payrolls",
            "description": "Total nonfarm employment from the CES survey. Key jobs report headline.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "PAYROLLS_PRIVATE": {
            "name": "Private Nonfarm Payrolls",
            "description": "Total private-sector nonfarm employment.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "PAYROLLS_MANUFACTURING": {
            "name": "Manufacturing Payrolls",
            "description": "Employment in the manufacturing sector.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "PAYROLLS_GOVERNMENT": {
            "name": "Government Payrolls",
            "description": "Total government employment (federal, state, local).",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "PAYROLLS_RETAIL": {
            "name": "Retail Trade Payrolls",
            "description": "Employment in the retail trade sector.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "LABOR_FORCE_PARTICIPATION": {
            "name": "Labor Force Participation Rate",
            "description": "Civilian labor force as percent of civilian noninstitutional population.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "EMPLOYMENT_POPULATION_RATIO": {
            "name": "Employment-Population Ratio",
            "description": "Employed persons as percent of civilian noninstitutional population.",
            "metadata": {"category": "employment", "frequency": "monthly", "seasonal_adj": True}
        },
        "AVG_HOURLY_EARNINGS": {
            "name": "Average Hourly Earnings (Private)",
            "description": "Average hourly earnings of all employees on private nonfarm payrolls.",
            "metadata": {"category": "earnings", "frequency": "monthly", "seasonal_adj": True}
        },
        "AVG_HOURLY_EARNINGS_PROD": {
            "name": "Average Hourly Earnings (Production Workers)",
            "description": "Average hourly earnings of production and nonsupervisory employees on private nonfarm payrolls.",
            "metadata": {"category": "earnings", "frequency": "monthly", "seasonal_adj": True}
        },
        "AVG_WEEKLY_HOURS": {
            "name": "Average Weekly Hours (Private)",
            "description": "Average weekly hours of all employees on private nonfarm payrolls.",
            "metadata": {"category": "earnings", "frequency": "monthly", "seasonal_adj": True}
        },
        "PPI_FINAL_DEMAND": {
            "name": "PPI Final Demand",
            "description": "Producer Price Index for Final Demand. Measures wholesale price changes for finished goods and services.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "PPI_FINAL_DEMAND_GOODS": {
            "name": "PPI Final Demand Goods",
            "description": "Producer Price Index for Final Demand finished goods.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "PPI_FINAL_DEMAND_SERVICES": {
            "name": "PPI Final Demand Services",
            "description": "Producer Price Index for Final Demand services.",
            "metadata": {"category": "prices", "frequency": "monthly", "seasonal_adj": True}
        },
        "JOLTS_OPENINGS": {
            "name": "JOLTS Job Openings Rate",
            "description": "Job openings as percent of employment plus openings. From Job Openings and Labor Turnover Survey.",
            "metadata": {"category": "labor_market", "frequency": "monthly", "seasonal_adj": True}
        },
        "JOLTS_HIRES": {
            "name": "JOLTS Hires Rate",
            "description": "Hires as percent of total employment. From JOLTS.",
            "metadata": {"category": "labor_market", "frequency": "monthly", "seasonal_adj": True}
        },
        "JOLTS_QUITS": {
            "name": "JOLTS Quits Rate",
            "description": "Voluntary quits as percent of total employment. Indicator of worker confidence.",
            "metadata": {"category": "labor_market", "frequency": "monthly", "seasonal_adj": True}
        },
        "JOLTS_SEPARATIONS": {
            "name": "JOLTS Total Separations Rate",
            "description": "Total separations (quits, layoffs, discharges, other) as percent of total employment.",
            "metadata": {"category": "labor_market", "frequency": "monthly", "seasonal_adj": True}
        },
        "PRODUCTIVITY_OUTPUT": {
            "name": "Nonfarm Business Output Per Hour",
            "description": "Labor productivity: real output per hour in the nonfarm business sector.",
            "metadata": {"category": "productivity", "frequency": "quarterly", "seasonal_adj": True}
        },
        "UNIT_LABOR_COSTS": {
            "name": "Nonfarm Business Unit Labor Costs",
            "description": "Compensation per unit of output in nonfarm business. Key wage inflation indicator.",
            "metadata": {"category": "productivity", "frequency": "quarterly", "seasonal_adj": True}
        },
        "IMPORT_PRICE_INDEX": {
            "name": "Import Price Index",
            "description": "Price index for all imports into the United States.",
            "metadata": {"category": "trade", "frequency": "monthly", "seasonal_adj": False}
        },
        "EXPORT_PRICE_INDEX": {
            "name": "Export Price Index",
            "description": "Price index for all exports from the United States.",
            "metadata": {"category": "trade", "frequency": "monthly", "seasonal_adj": False}
        },
    }

    def __init__(self, series_id: str = "CUUR0000SA0"):
        # Resolve popular alias if provided
        self.series_id = self.SERIES_MAPPING.get(series_id, series_id)
        self.api_key = os.getenv("BLS_API_KEY", "")
        
        # Use V2 if key exists, else fallback to V1
        if self.api_key:
            self.base_url = "https://api.bls.gov/publicAPI/v2/"
        else:
            self.base_url = "https://api.bls.gov/publicAPI/v1/"
            
        self.client = HttpClient(base_url=self.base_url)

    @property
    def source_name(self) -> str:
        return "BLS"

    @property
    def identifier(self) -> str:
        return self.series_id

    @classmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "startyear": {"type": str, "default": ""},
            "endyear": {"type": str, "default": ""},
        }

    @classmethod
    def get_search_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "query": {"type": str, "required": True, "description": "Search query text"},
            "limit": {"type": int, "required": False, "default": 10, "description": "Max results"},
        }

    def search(self, query: str, limit: int = 10, **kwargs) -> List[SearchResult]:
        """Search the BLS series catalog by keyword."""
        results = []
        q = query.lower()
        for key, info in self.SEARCH_CATALOG.items():
            if (q in key.lower()
                    or q in info["name"].lower()
                    or q in info.get("description", "").lower()):
                results.append(SearchResult(
                    identifier=key,
                    name=info["name"],
                    source=self.source_name,
                    description=info.get("description"),
                    metadata={
                        "series_id": self.SERIES_MAPPING.get(key, ""),
                        **info.get("metadata", {})
                    }
                ))
        return results[:limit]

    def fetch_raw(self, **kwargs) -> BronzePayload:
        """
        Fetch data from the BLS API.
        Handles multi-year pagination due to BLS API restrictions (10-year limit for V1, 20-year limit for V2).
        """
        start_year_str = kwargs.get("startyear", "")
        end_year_str = kwargs.get("endyear", "")

        # If start and end year are provided, compute query spans
        if start_year_str and end_year_str:
            try:
                start_year = int(start_year_str)
                end_year = int(end_year_str)
            except ValueError:
                logger.error(f"Invalid startyear/endyear: {start_year_str}/{end_year_str}. Falling back to default.")
                start_year, end_year = None, None
        else:
            start_year, end_year = None, None

        all_data_points = []
        
        if start_year and end_year:
            # V2 allows 20 years, V1 allows 10 years
            step = 20 if self.api_key else 10
            
            # Loop in chunks of step size
            current_start = start_year
            while current_start <= end_year:
                current_end = min(current_start + step - 1, end_year)
                
                payload = {
                    "seriesid": [self.series_id],
                    "startyear": str(current_start),
                    "endyear": str(current_end),
                }
                if self.api_key:
                    payload["registrationkey"] = self.api_key
                
                try:
                    response = self.client.post("timeseries/data/", json=payload)
                    res_json = response.json()
                    
                    if res_json.get("status") == "REQUEST_SUCCEEDED":
                        series_list = res_json.get("Results", {}).get("series", [])
                        if series_list:
                            all_data_points.extend(series_list[0].get("data", []))
                    else:
                        msg = res_json.get("message", "Unknown API error")
                        logger.warning(f"BLS request returned error status for {current_start}-{current_end}: {msg}")
                except Exception as e:
                    logger.error(f"BLS API fetch failed for {current_start}-{current_end}: {str(e)}")
                    
                current_start += step
        else:
            # Default payload fetches the most recent 3 years
            payload = {"seriesid": [self.series_id]}
            if self.api_key:
                payload["registrationkey"] = self.api_key
                
            response = self.client.post("timeseries/data/", json=payload)
            res_json = response.json()
            if res_json.get("status") == "REQUEST_SUCCEEDED":
                series_list = res_json.get("Results", {}).get("series", [])
                if series_list:
                    all_data_points.extend(series_list[0].get("data", []))
            else:
                msg = res_json.get("message", "Unknown API error")
                logger.warning(f"BLS request failed: {msg}")

        # Construct final payload structure
        raw_payload = {
            "status": "REQUEST_SUCCEEDED" if all_data_points else "FAILED",
            "Results": {
                "series": [
                    {
                        "seriesID": self.series_id,
                        "data": all_data_points
                    }
                ]
            }
        }

        # Increment metrics
        TERMINAL_ADAPTER_MESSAGES_TOTAL.labels(source=self.source_name, entity_id=self.series_id).inc(len(all_data_points))
        
        return BronzePayload(
            protocol="http",
            origin_metadata={"url": self.base_url + "timeseries/data/", "method": "POST"},
            execution_metadata={},
            payload_format="json",
            raw_payload=json.dumps(raw_payload)
        )

    def to_silver(self, payload: BronzePayload, batch_id: Optional[str] = None) -> pd.DataFrame:
        """
        Normalize BLS agnostic BronzePayload to canonical Silver layer.
        """
        import json
        import logging
        from domains.macro.models import SilverMacroObservations
        from domains.macro.transformers import normalize_macro_data
        
        logger = logging.getLogger("adapters.macro.bls")
        
        raw_data = json.loads(payload.raw_payload)
        series_list = raw_data.get("Results", {}).get("series", [])
        
        if not series_list:
            return pd.DataFrame(columns=list(SilverMacroObservations.model_fields.keys()))
            
        data = series_list[0].get("data", [])
        if not data:
            return pd.DataFrame(columns=list(SilverMacroObservations.model_fields.keys()))

        bronze_ref = payload.payload_checksum or "unknown"
        lineage = {
            "source_version": self.base_url + "timeseries/data/",
            "bronze_reference": bronze_ref,
            "batch_id": batch_id
        }
        
        # Determine unit (Unemployment is percent, CPI/PPI is index)
        unit_val = "PERCENT" if "LNS14" in self.series_id else "INDEX"

        records_read = len(data)
        records_transformed = 0
        records_rejected = 0
        rejection_reasons = {}

        validated_records = []
        for row in data:
            year = row.get("year")
            period = row.get("period", "")
            
            # Standardize month parsing
            date_val = None
            if period.startswith("M"):
                m = int(period[1:])
                if m > 12:
                    date_val = f"{year}-12-31"
                else:
                    date_val = f"{year}-{m:02d}-01"
            elif period.startswith("Q"):
                q = int(period[1:])
                m = (q - 1) * 3 + 1
                date_val = f"{year}-{m:02d}-01"
            else:
                date_val = f"{year}-12-31"

            transformed_row = {
                "series_id": self.series_id,
                "observation_date": date_val,
                "value": row.get("value"),
                # BLS does not track vintage revisions, use defaults
                "realtime_start": "1970-01-01",
                "realtime_end": "2099-12-31",
                "unit": unit_val
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
                    self.source_name, "macro", batch_id or "N/A", bronze_ref, exc_type, str(e)
                )
                continue

        logger.info(
            "Transformation summary for %s (%s) - Read: %d, Transformed: %d, Rejected: %d, Rejection Reasons: %s, Written: %d",
            self.source_name, self.series_id, records_read, records_transformed, records_rejected, json.dumps(rejection_reasons), records_transformed
        )

        silver_df = pd.DataFrame(validated_records)
        
        if not silver_df.empty:
            silver_df = silver_df.set_index("observation_date", drop=False)
            silver_df.index.name = "timestamp"

        return silver_df

    def get_metadata(self) -> TerminalDataFrameMetadata:
        metadata = TerminalDataFrameMetadata(
            name=f"BLS - {self.series_id}",
            description="Bureau of Labor Statistics macroeconomic data series.",
            frequency="monthly",
            source=self.source_name,
            is_seasonally_adjusted=True
        )
        metadata.metadata["columns"] = [
            {"name": "value", "unit": "INDEX", "semantic_type": "value", "description": "Numeric observation"},
            {"name": "realtime_start", "unit": "DATE", "semantic_type": "vintage_start", "description": "Date observation was ingested"},
            {"name": "realtime_end", "unit": "DATE", "semantic_type": "vintage_end", "description": "Date observation was superseded"}
        ]
        return metadata
