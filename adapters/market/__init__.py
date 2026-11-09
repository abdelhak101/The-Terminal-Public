import importlib

_MARKET_ADAPTERS = {
    "YahooAdapter": ("adapters.market.yahoo", "YahooAdapter"),
}

__all__ = list(_MARKET_ADAPTERS.keys())


def __getattr__(name):
    if name in _MARKET_ADAPTERS:
        module_path, class_name = _MARKET_ADAPTERS[name]
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
