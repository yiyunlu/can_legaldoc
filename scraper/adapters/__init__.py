"""
Multi-source adapter registry.
Each data source adapter registers itself via the @register_adapter decorator.
Use get_adapter() to instantiate an adapter by source_type.
"""
from typing import Dict, Type

# Lazy imports to avoid circular dependencies
_ADAPTER_REGISTRY: Dict[str, Type] = {}


def register_adapter(source_type: str):
    """Decorator to register an adapter class for a given source_type."""
    def decorator(cls):
        _ADAPTER_REGISTRY[source_type] = cls
        return cls
    return decorator


def get_adapter(source_type: str, **kwargs):
    """
    Factory: instantiate an adapter by source_type.

    Args:
        source_type: registered source type string
        **kwargs: passed to the adapter constructor

    Returns:
        BaseSourceAdapter instance

    Raises:
        ValueError if source_type is not registered
    """
    if source_type not in _ADAPTER_REGISTRY:
        # Try importing known adapter modules to trigger registration
        _ensure_adapters_loaded()

    if source_type not in _ADAPTER_REGISTRY:
        available = ', '.join(sorted(_ADAPTER_REGISTRY.keys())) or '(none)'
        raise ValueError(
            f"Unknown source_type: '{source_type}'. Available: {available}"
        )
    return _ADAPTER_REGISTRY[source_type](**kwargs)


def list_adapters() -> Dict[str, Type]:
    """Return all registered adapters."""
    _ensure_adapters_loaded()
    return dict(_ADAPTER_REGISTRY)


def _ensure_adapters_loaded():
    """Import all adapter modules to trigger their @register_adapter decorators."""
    import importlib
    adapter_modules = [
        'scraper.adapters.justice_canada_xml',
        'scraper.adapters.bc_laws_api',
        'scraper.adapters.alberta_kings_printer',
        'scraper.adapters.a2aj_case_law',
        'scraper.adapters.canlii_legacy',
        'scraper.adapters.manitoba_laws',
        'scraper.adapters.newfoundland_laws',
        'scraper.adapters.nova_scotia_laws',
        'scraper.adapters.new_brunswick_laws',
        'scraper.adapters.ontario_elaws',
        'scraper.adapters.yukon_laws',
        'scraper.adapters.nwt_laws',
        'scraper.adapters.nunavut_laws',
    ]
    for mod_name in adapter_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass  # Module not yet implemented or deps missing
