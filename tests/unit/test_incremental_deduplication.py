import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from dagster import build_op_context

from adapters.macro.bls import BLSAdapter
from adapters.factory import create_adapter_assets
from shared.models import BronzePayload


class TestIncrementalDeduplication:

    def test_precision_slicing_filters_older_data(self):
        adapter = BLSAdapter("CUUR0000SA0")
        assets = create_adapter_assets(adapter, config={}, label="main")
        asset_pipeline = assets[0]

        # Sample DataFrame spanning 3 months
        sample_df = pd.DataFrame([
            {"series_id": "CUUR0000SA0", "observation_date": pd.Timestamp("2026-05-01"), "value": 335.1, "batch_id": "b1"},
            {"series_id": "CUUR0000SA0", "observation_date": pd.Timestamp("2026-06-01"), "value": 333.9, "batch_id": "b1"},
            {"series_id": "CUUR0000SA0", "observation_date": pd.Timestamp("2026-07-01"), "value": 333.9, "batch_id": "b1"},
        ])

        with patch("adapters.factory.MetadataRegistry") as mock_registry_cls:
            mock_registry = mock_registry_cls.return_value
            # Simulate previous run observed up to 2026-06-01
            mock_registry.get_last_observed_timestamp.return_value = pd.Timestamp("2026-06-01")

            with patch.object(adapter, "fetch_raw") as mock_fetch, \
                 patch.object(adapter, "to_silver") as mock_to_silver:
                
                mock_fetch.return_value = BronzePayload(
                    protocol="http",
                    origin_metadata={},
                    execution_metadata={},
                    payload_format="json",
                    raw_payload="{}"
                )
                mock_to_silver.return_value = sample_df.copy()

                context = build_op_context()
                outputs = list(asset_pipeline(context))

                # Find silver output
                silver_output = next(o for o in outputs if o.output_name == "silver_asset")
                sliced_df = silver_output.value

                # Should only retain 2026-07-01 (1 row instead of 3)
                assert len(sliced_df) == 1
                assert pd.to_datetime(sliced_df["observation_date"].iloc[0]) == pd.Timestamp("2026-07-01")
                
                # Check that registry symbol was passed correctly (without silver. prefix)
                mock_registry.update_last_observed_timestamp.assert_called_once()
                args, kwargs = mock_registry.update_last_observed_timestamp.call_args
                symbol_arg = args[0]
                assert not symbol_arg.startswith("silver.")

    def test_precision_slicing_all_old_returns_empty(self):
        adapter = BLSAdapter("CUUR0000SA0")
        assets = create_adapter_assets(adapter, config={}, label="main")
        asset_pipeline = assets[0]

        sample_df = pd.DataFrame([
            {"series_id": "CUUR0000SA0", "observation_date": pd.Timestamp("2026-05-01"), "value": 335.1, "batch_id": "b1"},
            {"series_id": "CUUR0000SA0", "observation_date": pd.Timestamp("2026-06-01"), "value": 333.9, "batch_id": "b1"},
        ])

        with patch("adapters.factory.MetadataRegistry") as mock_registry_cls:
            mock_registry = mock_registry_cls.return_value
            # Last observed is newer than all records (2026-07-01)
            mock_registry.get_last_observed_timestamp.return_value = pd.Timestamp("2026-07-01")

            with patch.object(adapter, "fetch_raw") as mock_fetch, \
                 patch.object(adapter, "to_silver") as mock_to_silver:
                
                mock_fetch.return_value = BronzePayload(
                    protocol="http",
                    origin_metadata={},
                    execution_metadata={},
                    payload_format="json",
                    raw_payload="{}"
                )
                mock_to_silver.return_value = sample_df.copy()

                context = build_op_context()
                outputs = list(asset_pipeline(context))

                silver_output = next(o for o in outputs if o.output_name == "silver_asset")
                sliced_df = silver_output.value

                # All data was old -> 0 rows
                assert len(sliced_df) == 0
