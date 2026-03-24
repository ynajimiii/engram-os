"""
Probe - Discovery and introspection utilities.

Phase 00: Foundation
"""

from typing import Any, Dict, List, Optional


class Probe:
    """Discovers and inspects system state, capabilities, and context."""

    def __init__(self):
        self._discovered: Dict[str, Any] = {}

    def introspect(self, target: Any) -> Dict[str, Any]:
        """Introspect a target object to discover its structure."""
        result = {
            "type": type(target).__name__,
            "attributes": {},
            "methods": [],
        }

        if hasattr(target, "__dict__"):
            result["attributes"] = {
                k: v for k, v in target.__dict__.items()
                if not k.startswith("_")
            }

        if hasattr(target, "__class__"):
            result["methods"] = [
                m for m in dir(target)
                if callable(getattr(target, m)) and not m.startswith("_")
            ]

        self._discovered[str(id(target))] = result
        return result

    def discover_capabilities(self) -> List[str]:
        """Discover available system capabilities."""
        capabilities = []

        # Check for optional dependencies
        try:
            import yaml
            capabilities.append("yaml")
        except ImportError:
            pass

        try:
            import numpy
            capabilities.append("numpy")
        except ImportError:
            pass

        return capabilities

    def get_discovery(self, target_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a previous discovery by target ID."""
        return self._discovered.get(target_id)

    def clear(self) -> None:
        """Clear all discoveries."""
        self._discovered.clear()


def get_hardware_state() -> Dict[str, Any]:
    """
    Get current hardware state including GPU and RAM information.
    
    Returns:
        Dictionary with hardware state information
    """
    import psutil
    
    result = {
        "vram_total_mb": 24576,  # Default for RTX 3090
        "vram_free_mb": 23226,
        "ram_total_mb": psutil.virtual_memory().total // (1024**2),
        "ram_available_mb": psutil.virtual_memory().available // (1024**2),
    }
    
    try:
        import nvidia_ml_py as pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        result["vram_total_mb"] = mem.total // (1024**2)
        result["vram_free_mb"] = mem.free // (1024**2)
    except Exception:
        pass  # Use defaults if nvidia-ml-py fails
    
    return result
