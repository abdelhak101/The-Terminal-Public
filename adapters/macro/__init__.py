import importlib

_MACRO_ADAPTERS = {
    "BLSAdapter": ("adapters.macro.bls", "BLSAdapter"),
    "CensusAdapter": ("adapters.macro.census", "CensusAdapter"),
    "FREDAdapter": ("adapters.macro.fred", "FREDAdapter"),
    "MoneycontrolAdapter": ("adapters.macro.moneycontrol", "MoneycontrolAdapter"),
}

__all__ = list(_MACRO_ADAPTERS.keys())


def __getattr__(name):
    if name in _MACRO_ADAPTERS:
        module_path, class_name = _MACRO_ADAPTERS[name]
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
