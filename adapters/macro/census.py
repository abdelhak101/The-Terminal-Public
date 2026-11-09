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

class CensusAdapter(SearchableAdapter[List[List[str]]]):
    """
    Adapter for US Census Bureau API (handling timeseries/eits datasets).
    """

    # Class-level mappings for popular indicators to their Census configurations
    INDICATOR_MAPPING = {
        # Housing (Residential Construction - resconst)
        "HOUSING_STARTS": {
            "dataset": "timeseries/eits/resconst",
            "category_code": "ASTARTS",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "THOUSANDS"
        },
        "HOUSING_PERMITS": {
            "dataset": "timeseries/eits/resconst",
            "category_code": "APERMITS",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "THOUSANDS"
        },
        "HOUSING_COMPLETIONS": {
            "dataset": "timeseries/eits/resconst",
            "category_code": "ACOMPLETIONS",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "THOUSANDS"
        },
        "HOUSING_UNDER_CONSTRUCTION": {
            "dataset": "timeseries/eits/resconst",
            "category_code": "UNDERCONST",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "THOUSANDS"
        },
        # Retail Trade (Monthly Advance Retail Trade - marts)
        "RETAIL_SALES": {
            "dataset": "timeseries/eits/marts",
            "category_code": "44000",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_EXCL_AUTO": {
            "dataset": "timeseries/eits/marts",
            "category_code": "44X72",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_FOOD_SERVICES": {
            "dataset": "timeseries/eits/marts",
            "category_code": "722",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_MOTOR_VEHICLES": {
            "dataset": "timeseries/eits/marts",
            "category_code": "44111",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_GASOLINE": {
            "dataset": "timeseries/eits/marts",
            "category_code": "44711",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_BUILDING_MATERIALS": {
            "dataset": "timeseries/eits/marts",
            "category_code": "444",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_CLOTHING": {
            "dataset": "timeseries/eits/marts",
            "category_code": "448",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_GENERAL_MERCHANDISE": {
            "dataset": "timeseries/eits/marts",
            "category_code": "452",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "RETAIL_ECOMMERCE": {
            "dataset": "timeseries/eits/marts",
            "category_code": "4541",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # Manufacturing (M3 Survey)
        "MFG_NEW_ORDERS": {
            "dataset": "timeseries/eits/m3",
            "category_code": "TOTAL",
            "data_type_code": "NO",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "MFG_SHIPMENTS": {
            "dataset": "timeseries/eits/m3",
            "category_code": "TOTAL",
            "data_type_code": "VS",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "MFG_UNFILLED_ORDERS": {
            "dataset": "timeseries/eits/m3",
            "category_code": "TOTAL",
            "data_type_code": "UO",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "MFG_INVENTORIES": {
            "dataset": "timeseries/eits/m3",
            "category_code": "TOTAL",
            "data_type_code": "TI",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # Durable Goods (Advance M3)
        "DURABLE_GOODS_ORDERS": {
            "dataset": "timeseries/eits/advm3",
            "category_code": "TOTAL",
            "data_type_code": "NO",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "DURABLE_GOODS_SHIPMENTS": {
            "dataset": "timeseries/eits/advm3",
            "category_code": "TOTAL",
            "data_type_code": "VS",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "DURABLE_GOODS_EXCL_TRANSPORT": {
            "dataset": "timeseries/eits/advm3",
            "category_code": "AXTRAN",
            "data_type_code": "NO",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # Construction Spending (Value of Construction Put in Place)
        "CONSTRUCTION_TOTAL": {
            "dataset": "timeseries/eits/vip",
            "category_code": "TOTAL",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "CONSTRUCTION_RESIDENTIAL": {
            "dataset": "timeseries/eits/vip",
            "category_code": "RES",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "CONSTRUCTION_NONRESIDENTIAL": {
            "dataset": "timeseries/eits/vip",
            "category_code": "NRES",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # Business Inventories (Manufacturing & Trade)
        "BUSINESS_INVENTORIES": {
            "dataset": "timeseries/eits/mtis",
            "category_code": "TOTAL",
            "data_type_code": "IM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "BUSINESS_SALES": {
            "dataset": "timeseries/eits/mtis",
            "category_code": "TOTAL",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # Wholesale Trade
        "WHOLESALE_SALES": {
            "dataset": "timeseries/eits/mwts",
            "category_code": "TOTAL",
            "data_type_code": "SM",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        "WHOLESALE_INVENTORIES": {
            "dataset": "timeseries/eits/mwts",
            "category_code": "TOTAL",
            "data_type_code": "EI",
            "seasonally_adj": "yes",
            "unit": "USD_MILLIONS"
        },
        # New Home Sales
        "NEW_HOME_SALES": {
            "dataset": "timeseries/eits/ressales",
            "category_code": "ASOLD",
            "data_type_code": "TOTAL",
            "seasonally_adj": "yes",
            "unit": "THOUSANDS"
        },
        "NEW_HOME_MEDIAN_PRICE": {
            "dataset": "timeseries/eits/ressales",
            "category_code": "ASOLD",
            "data_type_code": "AMPR",
            "seasonally_adj": "no",
            "unit": "USD"
        },
    }

    # Rich metadata catalog for search discovery
    SEARCH_CATALOG = {
        "HOUSING_STARTS": {
            "name": "Housing Starts",
            "description": "New privately-owned housing units started (annualized). Key leading indicator for residential construction.",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
        "HOUSING_PERMITS": {
            "name": "Building Permits",
            "description": "New privately-owned housing units authorized by building permits (annualized).",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
        "HOUSING_COMPLETIONS": {
            "name": "Housing Completions",
            "description": "New privately-owned housing units completed (annualized).",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
        "HOUSING_UNDER_CONSTRUCTION": {
            "name": "Housing Under Construction",
            "description": "New privately-owned housing units currently under construction.",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
        "RETAIL_SALES": {
            "name": "Retail Sales (Total)",
            "description": "Total retail trade sales. Monthly measure of consumer spending on goods.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_EXCL_AUTO": {
            "name": "Retail Sales Excl. Auto",
            "description": "Retail and food services sales excluding motor vehicle and parts dealers.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_FOOD_SERVICES": {
            "name": "Food Services & Drinking Places",
            "description": "Sales at restaurants, bars, and other food services establishments.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_MOTOR_VEHICLES": {
            "name": "Motor Vehicle & Parts Sales",
            "description": "Retail sales of motor vehicles and parts dealers.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_GASOLINE": {
            "name": "Gasoline Station Sales",
            "description": "Retail sales at gasoline stations.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_BUILDING_MATERIALS": {
            "name": "Building Materials & Garden Sales",
            "description": "Retail sales of building materials, garden equipment, and supplies.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_CLOTHING": {
            "name": "Clothing & Accessories Sales",
            "description": "Retail sales at clothing and clothing accessories stores.",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_GENERAL_MERCHANDISE": {
            "name": "General Merchandise Store Sales",
            "description": "Retail sales at general merchandise stores (department stores, warehouse clubs).",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "RETAIL_ECOMMERCE": {
            "name": "Electronic Shopping & Mail-Order Sales",
            "description": "Retail sales from electronic shopping and mail-order houses (e-commerce proxy).",
            "metadata": {"category": "retail", "frequency": "monthly"}
        },
        "MFG_NEW_ORDERS": {
            "name": "Manufacturing New Orders",
            "description": "New orders for manufactured goods (total). Leading indicator for manufacturing activity.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "MFG_SHIPMENTS": {
            "name": "Manufacturing Shipments",
            "description": "Value of shipments for manufactured goods (total).",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "MFG_UNFILLED_ORDERS": {
            "name": "Manufacturing Unfilled Orders",
            "description": "Unfilled orders for manufactured goods. Indicator of manufacturing backlog.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "MFG_INVENTORIES": {
            "name": "Manufacturing Inventories",
            "description": "Total value of inventories held by manufacturers.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "DURABLE_GOODS_ORDERS": {
            "name": "Durable Goods New Orders",
            "description": "Advance report on new orders for durable goods. Key leading economic indicator.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "DURABLE_GOODS_SHIPMENTS": {
            "name": "Durable Goods Shipments",
            "description": "Advance report on shipments of durable goods.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "DURABLE_GOODS_EXCL_TRANSPORT": {
            "name": "Durable Goods Excl. Transportation",
            "description": "New orders for durable goods excluding transportation equipment. Removes volatile aircraft orders.",
            "metadata": {"category": "manufacturing", "frequency": "monthly"}
        },
        "CONSTRUCTION_TOTAL": {
            "name": "Construction Spending (Total)",
            "description": "Total value of construction put in place (public + private).",
            "metadata": {"category": "construction", "frequency": "monthly"}
        },
        "CONSTRUCTION_RESIDENTIAL": {
            "name": "Construction Spending (Residential)",
            "description": "Value of residential construction put in place.",
            "metadata": {"category": "construction", "frequency": "monthly"}
        },
        "CONSTRUCTION_NONRESIDENTIAL": {
            "name": "Construction Spending (Nonresidential)",
            "description": "Value of nonresidential construction put in place.",
            "metadata": {"category": "construction", "frequency": "monthly"}
        },
        "BUSINESS_INVENTORIES": {
            "name": "Business Inventories",
            "description": "Total business inventories (manufacturing, wholesale, retail). Used to calculate inventory-to-sales ratio.",
            "metadata": {"category": "trade", "frequency": "monthly"}
        },
        "BUSINESS_SALES": {
            "name": "Business Sales",
            "description": "Total business sales (manufacturing, wholesale, retail).",
            "metadata": {"category": "trade", "frequency": "monthly"}
        },
        "WHOLESALE_SALES": {
            "name": "Wholesale Trade Sales",
            "description": "Monthly wholesale trade sales. Measures demand at the wholesale level.",
            "metadata": {"category": "trade", "frequency": "monthly"}
        },
        "WHOLESALE_INVENTORIES": {
            "name": "Wholesale Trade Inventories",
            "description": "Month-end wholesale trade inventories.",
            "metadata": {"category": "trade", "frequency": "monthly"}
        },
        "NEW_HOME_SALES": {
            "name": "New Home Sales",
            "description": "New single-family houses sold (annualized). Key housing market indicator.",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
        "NEW_HOME_MEDIAN_PRICE": {
            "name": "New Home Median Sale Price",
            "description": "Median sale price of new single-family houses sold.",
            "metadata": {"category": "housing", "frequency": "monthly"}
        },
    }

    def __init__(self, indicator_or_dataset: str = "HOUSING_STARTS"):
        # Resolve popular alias or treat as custom dataset path
        if indicator_or_dataset in self.INDICATOR_MAPPING:
            config = self.INDICATOR_MAPPING[indicator_or_dataset]
            self.dataset = config["dataset"]
            self.category_code = config["category_code"]
            self.data_type_code = config["data_type_code"]
            self.seasonally_adj = config["seasonally_adj"]
            self.default_unit = config["unit"]
        else:
            # Custom configuration mode
            self.dataset = indicator_or_dataset
            self.category_code = ""
            self.data_type_code = ""
            self.seasonally_adj = "yes"
            self.default_unit = "INDEX"

        self.api_key = os.getenv("CENSUS_API_KEY", "")
        self.client = HttpClient(base_url="https://api.census.gov/data/")

    @property
    def source_name(self) -> str:
        return "Census Bureau"

    @property
    def identifier(self) -> str:
        ident = self.dataset.replace("timeseries/", "").replace("/", "_")
        if self.category_code:
            ident += f"_{self.category_code}"
        return ident.upper()

    @classmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "category_code": {"type": str, "default": ""},
            "data_type_code": {"type": str, "default": ""},
            "seasonally_adj": {"type": str, "default": "yes"},
        }

    @classmethod
    def get_search_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "query": {"type": str, "required": True, "description": "Search query text"},
            "limit": {"type": int, "required": False, "default": 10, "description": "Max results"},
        }

    def search(self, query: str, limit: int = 10, **kwargs) -> List[SearchResult]:
        """Search the Census indicator catalog by keyword."""
        results = []
        q = query.lower()
        for key, info in self.SEARCH_CATALOG.items():
            if (q in key.lower()
                    or q in info["name"].lower()
                    or q in info.get("description", "").lower()):
                config = self.INDICATOR_MAPPING.get(key, {})
                results.append(SearchResult(
                    identifier=key,
                    name=info["name"],
                    source=self.source_name,
                    description=info.get("description"),
                    metadata={
                        "dataset": config.get("dataset", ""),
                        **info.get("metadata", {})
                    }
                ))
        return results[:limit]

    def fetch_raw(self, **kwargs) -> BronzePayload:
        """
        Fetch data from Census API using standard GET variables.
        """
        # Resolve parameters (prefer kwargs, fallback to instance defaults)
        category = kwargs.get("category_code") or self.category_code
        data_type = kwargs.get("data_type_code") or self.data_type_code
        adj = kwargs.get("seasonally_adj") or self.seasonally_adj

        params = {
            "get": "cell_value,time_slot_id",
            "time": "from 2000"
        }
        
        if category:
            params["category_code"] = category
        if data_type:
            params["data_type_code"] = data_type
        if adj:
            params["seasonally_adj"] = adj
            
        if self.api_key:
            params["key"] = self.api_key

        try:
            response = self.client.get(self.dataset, params=params)
            data = response.json()
            
            # Census returns headers as the first row. Row count is len(data) - 1
            row_count = len(data) - 1 if data and isinstance(data, list) else 0
            TERMINAL_ADAPTER_MESSAGES_TOTAL.labels(source=self.source_name, entity_id=self.identifier).inc(row_count)
            
            return BronzePayload(
                protocol="http",
                origin_metadata={"url": str(response.url), "method": response.request.method},
                execution_metadata={"status_code": response.status_code},
                payload_format="json",
                raw_payload=response.text
            )
        except Exception as e:
            logger.error(f"Census API fetch failed for {self.dataset}: {str(e)}")
            fallback = [["cell_value", "time", "category_code", "data_type_code", "seasonally_adj"]]
            return BronzePayload(
                protocol="http",
                origin_metadata={"url": self.dataset},
                execution_metadata={"error": str(e)},
                payload_format="json",
                raw_payload=json.dumps(fallback)
            )

    def to_silver(self, payload: BronzePayload, batch_id: Optional[str] = None) -> pd.DataFrame:
        """
        Normalize Census raw payload to domain-specific SilverCensusObservations.
        """
        import json
        import logging
        from domains.census.models import SilverCensusObservations
        from domains.census.transformers import normalize_census_data
        
        logger = logging.getLogger("adapters.macro.census")
        
        raw_list = json.loads(payload.raw_payload)
        
        if not raw_list or len(raw_list) <= 1:
            return pd.DataFrame(columns=list(SilverCensusObservations.model_fields.keys()))

        headers = raw_list[0]
        rows = raw_list[1:]
        
        bronze_ref = payload.payload_checksum or "unknown"
        lineage = {
            "source_version": self.dataset,
            "bronze_reference": bronze_ref,
            "batch_id": batch_id
        }
        
        records_read = len(rows)
        records_transformed = 0
        records_rejected = 0
        rejection_reasons = {}
        
        validated_records = []
        for row in rows:
            # Map Census array to dictionary using headers
            row_dict = dict(zip(headers, row))
            
            # Helper to parse time_slot into Date
            ts = row_dict.get("time", "").strip()
            date_val = None
            if "-Q" in ts.upper():
                parts = ts.upper().split("-Q")
                year = parts[0]
                q = int(parts[1])
                m = (q - 1) * 3 + 1
                date_val = f"{year}-{m:02d}-01"
            elif len(ts) == 7 and ts[4] == '-' and ts[5:].isdigit():
                date_val = f"{ts}-01"
            elif len(ts) == 4 and ts.isdigit():
                date_val = f"{ts}-01-01"
                
            transformed_row = {
                "dataset_id": self.dataset,
                "observation_date": date_val,
                "reference_period": ts,
                "value": row_dict.get("cell_value"),
                "category_code": row_dict.get("category_code") or self.category_code,
                "data_type_code": row_dict.get("data_type_code") or self.data_type_code,
                "dimensions": {k: v for k, v in row_dict.items() if k not in ["time", "cell_value", "category_code", "data_type_code"]}
            }
            
            try:
                validated_model = normalize_census_data(transformed_row, lineage)
                validated_records.append(validated_model.model_dump())
                records_transformed += 1
            except Exception as e:
                records_rejected += 1
                exc_type = type(e).__name__
                rejection_reasons[exc_type] = rejection_reasons.get(exc_type, 0) + 1
                logger.warning(
                    "Validation failed for record. Source: %s, Domain: %s, Batch ID: %s, Bronze Record ID: %s, Exception Type: %s, Message: %s",
                    self.source_name, "census", batch_id or "N/A", bronze_ref, exc_type, str(e)
                )
                continue
                
        logger.info(
            "Transformation summary for %s (%s) - Read: %d, Transformed: %d, Rejected: %d, Rejection Reasons: %s, Written: %d",
            self.source_name, self.identifier, records_read, records_transformed, records_rejected, json.dumps(rejection_reasons), records_transformed
        )
        
        silver_df = pd.DataFrame(validated_records)
        
        if not silver_df.empty:
            # We must map observation_date to timestamp for Dagster/ClickHouse compatibility in the factory
            # OR we ensure the factory uses the right timestamp column.
            # Currently the factory checks for 'timestamp' or index.
            silver_df = silver_df.set_index("observation_date", drop=False)
            silver_df.index.name = "timestamp"

        return silver_df

    def get_metadata(self) -> TerminalDataFrameMetadata:
        metadata = TerminalDataFrameMetadata(
            name=f"Census - {self.identifier}",
            description="US Census Bureau macroeconomic indicators.",
            frequency="monthly",
            source=self.source_name,
            is_seasonally_adjusted=(self.seasonally_adj == "yes")
        )
        metadata.metadata["columns"] = [
            {"name": "value", "unit": self.default_unit, "semantic_type": "value", "description": "Numeric observation"},
            {"name": "realtime_start", "unit": "DATE", "semantic_type": "vintage_start", "description": "Date observation was ingested"},
            {"name": "realtime_end", "unit": "DATE", "semantic_type": "vintage_end", "description": "Date observation was superseded"}
        ]
        return metadata
