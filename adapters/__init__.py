import importlib
import logging

logger = logging.getLogger(__name__)

# Registry of adapter name → (module_path, class_name).
# Adapters are imported lazily on first access, not at module load time.
_ADAPTER_REGISTRY = {
    "yahoo": ("adapters.market.yahoo", "YahooAdapter"),
    "fred": ("adapters.macro.fred", "FREDAdapter"),
    "bls": ("adapters.macro.bls", "BLSAdapter"),
    "census": ("adapters.macro.census", "CensusAdapter"),
    "moneycontrol": ("adapters.macro.moneycontrol", "MoneycontrolAdapter"),
}


def _resolve(key):
    """Import and return the adapter class for a registry key."""
    module_path, class_name = _ADAPTER_REGISTRY[key]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class _LazyAdapterMap(dict):
    """Dict that lazily imports adapter classes on first access.

    Adapters whose dependencies are unavailable are logged and skipped,
    preventing a single missing package from crashing the entire service.
    """

    def _ensure_loaded(self):
        """Attempt to load every registered adapter (once)."""
        for key in list(_ADAPTER_REGISTRY):
            if key not in dict.keys(self):
                try:
                    dict.__setitem__(self, key, _resolve(key))
                except Exception as exc:
                    logger.warning("Adapter '%s' unavailable: %s", key, exc)

    # --- single-key access ---

    def __getitem__(self, key):
        if key not in dict.keys(self) and key in _ADAPTER_REGISTRY:
            try:
                dict.__setitem__(self, key, _resolve(key))
            except Exception as exc:
                logger.warning("Adapter '%s' unavailable: %s", key, exc)
                raise KeyError(key) from exc
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        if key not in dict.keys(self) and key in _ADAPTER_REGISTRY:
            try:
                dict.__setitem__(self, key, _resolve(key))
            except Exception:
                return False
        return dict.__contains__(self, key)

    # --- iteration (loads all) ---

    def items(self):
        self._ensure_loaded()
        return dict.items(self)

    def keys(self):
        self._ensure_loaded()
        return dict.keys(self)

    def values(self):
        self._ensure_loaded()
        return dict.values(self)

    def __iter__(self):
        self._ensure_loaded()
        return dict.__iter__(self)

    def __len__(self):
        self._ensure_loaded()
        return dict.__len__(self)


ADAPTER_MAP = _LazyAdapterMap()
