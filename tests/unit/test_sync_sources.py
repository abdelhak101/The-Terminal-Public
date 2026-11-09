import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml
from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_YAML = yaml.dump({
    "sources": [
        {
            "adapter_type": "yahoo",
            "identifier": "AAPL",
            "label": "daily_main",
            "description": "Apple Inc.",
            "config": {"interval": "1d", "period": "max", "auto_adjust": True},
        },
        {
            "adapter_type": "fred",
            "identifier": "GDP",
            "label": "quarterly",
            "description": "Gross Domestic Product",
            "config": {"frequency": "q"},
        },
    ]
})

SINGLE_SOURCE_YAML = yaml.dump({
    "sources": [
        {
            "adapter_type": "yahoo",
            "identifier": "AAPL",
            "label": "daily_main",
            "config": {"interval": "1d"},
        },
    ]
})

INVALID_ADAPTER_YAML = yaml.dump({
    "sources": [
        {"adapter_type": "nonexistent", "identifier": "XYZ"},
        {"adapter_type": "yahoo", "identifier": "AAPL", "config": {"interval": "1d"}},
    ]
})

INVALID_CONFIG_KEY_YAML = yaml.dump({
    "sources": [
        {
            "adapter_type": "yahoo",
            "identifier": "AAPL",
            "config": {"bad_key": "value"},
        },
        {
            "adapter_type": "fred",
            "identifier": "GDP",
            "config": {"frequency": "q"},
        },
    ]
})

MISSING_FIELDS_YAML = yaml.dump({
    "sources": [
        {"adapter_type": "yahoo"},  # missing identifier
        {"identifier": "AAPL"},     # missing adapter_type
        {"adapter_type": "yahoo", "identifier": "MSFT", "config": {"interval": "1d"}},
    ]
})

EMPTY_SOURCES_YAML = yaml.dump({"sources": []})

MALFORMED_YAML = "sources:\n  - adapter_type: yahoo\n    identifier: [unterminated"

NO_SOURCES_KEY_YAML = yaml.dump({"other_key": "value"})


def _make_mock_adapter(schema_keys):
    """Creates a mock adapter class with a given parameter schema."""
    mock = MagicMock()
    mock.get_parameter_schema.return_value = schema_keys
    return mock


def _build_adapter_map():
    """Builds a mock ADAPTER_MAP with yahoo and fred adapters."""
    yahoo = _make_mock_adapter(["interval", "period", "auto_adjust"])
    fred = _make_mock_adapter(["frequency", "observation_start", "observation_end"])
    adapter_map = {"yahoo": yahoo, "fred": fred}
    return adapter_map


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_valid_yaml(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Valid YAML is parsed, sources upserted, count matches."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=VALID_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    assert mock_registry.add_source.call_count == 2
    mock_registry.add_source.assert_any_call(
        adapter_type="yahoo",
        identifier="AAPL",
        label="daily_main",
        config={"interval": "1d", "period": "max", "auto_adjust": True},
        description="Apple Inc.",
    )
    mock_registry.add_source.assert_any_call(
        adapter_type="fred",
        identifier="GDP",
        label="quarterly",
        config={"frequency": "q"},
        description="Gross Domestic Product",
    )


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_deactivates_unlisted(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Source in PG but not in YAML is deactivated after sync (only YAML sources are re-activated)."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    # YAML has only 1 source — any others in PG should remain deactivated
    with patch("builtins.open", mock_open(read_data=SINGLE_SOURCE_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    assert mock_registry.add_source.call_count == 1
    mock_registry.add_source.assert_called_once_with(
        adapter_type="yahoo",
        identifier="AAPL",
        label="daily_main",
        config={"interval": "1d"},
        description=None,
    )


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_missing_file(mock_path_cls, mock_registry_cls):
    """Missing sources.yaml logs warning and leaves PG untouched."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = False
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_not_called()
    mock_registry.add_source.assert_not_called()


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_malformed_yaml(mock_path_cls, mock_registry_cls):
    """Invalid YAML syntax logs warning and leaves PG untouched."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=MALFORMED_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_not_called()
    mock_registry.add_source.assert_not_called()


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_invalid_adapter(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Unknown adapter_type is skipped with error log, valid entries still sync."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=INVALID_ADAPTER_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    # Only the yahoo entry should be synced, nonexistent is skipped
    assert mock_registry.add_source.call_count == 1
    mock_registry.add_source.assert_called_once_with(
        adapter_type="yahoo",
        identifier="AAPL",
        label="main",
        config={"interval": "1d"},
        description=None,
    )


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_invalid_config_key(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Bad config key skips that entry, other valid entries still sync."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=INVALID_CONFIG_KEY_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    # yahoo/AAPL has bad_key → skipped, fred/GDP is valid → synced
    assert mock_registry.add_source.call_count == 1
    mock_registry.add_source.assert_called_once_with(
        adapter_type="fred",
        identifier="GDP",
        label="main",
        config={"frequency": "q"},
        description=None,
    )


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_idempotent(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Running sync twice with the same YAML produces the same calls."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=SINGLE_SOURCE_YAML)):
        sync_sources_from_yaml()

    first_deactivate_count = mock_registry.deactivate_all_sources.call_count
    first_add_count = mock_registry.add_source.call_count

    with patch("builtins.open", mock_open(read_data=SINGLE_SOURCE_YAML)):
        sync_sources_from_yaml()

    # Each sync call should deactivate + add exactly once more
    assert mock_registry.deactivate_all_sources.call_count == first_deactivate_count * 2
    assert mock_registry.add_source.call_count == first_add_count * 2


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_missing_required_fields(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Entries missing adapter_type or identifier are skipped, valid entries sync."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=MISSING_FIELDS_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    # Only the third entry (yahoo/MSFT) is valid
    assert mock_registry.add_source.call_count == 1


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_no_sources_key(mock_path_cls, mock_registry_cls):
    """YAML without a 'sources' key logs warning and skips sync."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=NO_SOURCES_KEY_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_not_called()
    mock_registry.add_source.assert_not_called()


@patch("infrastructure.docker.orchestration.definitions.MetadataRegistry")
@patch("infrastructure.docker.orchestration.definitions.ADAPTER_MAP", new_callable=_build_adapter_map)
@patch("infrastructure.docker.orchestration.definitions.Path")
def test_sync_empty_sources_list(mock_path_cls, mock_adapter_map, mock_registry_cls):
    """Empty sources list deactivates all — intentional full clear."""
    from infrastructure.docker.orchestration.definitions import sync_sources_from_yaml

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path_cls.return_value = mock_path

    mock_registry = mock_registry_cls.return_value

    with patch("builtins.open", mock_open(read_data=EMPTY_SOURCES_YAML)):
        sync_sources_from_yaml()

    mock_registry.deactivate_all_sources.assert_called_once()
    mock_registry.add_source.assert_not_called()
