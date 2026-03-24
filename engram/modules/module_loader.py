"""
Module Loader - Dynamic module loading system.

Phase 05: Modules
"""

import os
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable


@dataclass
class ModuleInfo:
    """Information about a loaded module."""
    name: str
    version: str
    description: str
    path: str
    enabled: bool = True
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    scratch_template: Optional[str] = None
    loaded_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleConfig:
    """Configuration for module loading."""
    registry_path: str = "engram/modules/module_registry.yaml"
    auto_load: bool = True
    hot_reload: bool = False
    module_timeout: int = 300
    shared_state: bool = True


class ModuleLoader:
    """
    Loads and manages modules dynamically.
    
    Phase 05: Basic module loading from YAML registry.
    """
    
    def __init__(self, config: Optional[ModuleConfig] = None):
        self.config = config or ModuleConfig()
        self._modules: Dict[str, ModuleInfo] = {}
        self._module_data: Dict[str, Any] = {}
        self._hooks: Dict[str, List[Callable]] = {
            "on_load": [],
            "on_unload": [],
            "on_error": [],
        }
    
    def load_registry(self, registry_path: Optional[str] = None) -> List[str]:
        """
        Load modules from registry file.
        
        Args:
            registry_path: Path to registry YAML (uses config default if None)
        
        Returns:
            List of loaded module names
        """
        path = registry_path or self.config.registry_path
        
        if not os.path.exists(path):
            return []
        
        with open(path) as f:
            registry = yaml.safe_load(f)
        
        loaded = []
        modules_data = registry.get("modules", {})
        
        for name, data in modules_data.items():
            if data.get("enabled", True):
                module_info = self._parse_module_info(name, data)
                self._modules[name] = module_info
                self._module_data[name] = data
                loaded.append(name)
                
                self._trigger_hook("on_load", name)
        
        return loaded
    
    def _parse_module_info(self, name: str, data: Dict[str, Any]) -> ModuleInfo:
        """Parse module data into ModuleInfo."""
        return ModuleInfo(
            name=data.get("name", name),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            path=data.get("path", f"modules/{name}"),
            enabled=data.get("enabled", True),
            capabilities=data.get("capabilities", []),
            tools=data.get("tools", []),
            system_prompt=data.get("system_prompt"),
            scratch_template=data.get("scratch_template"),
            loaded_at=datetime.now(),
            metadata={k: v for k, v in data.items() 
                     if k not in ["name", "version", "description", "path", 
                                 "enabled", "capabilities", "tools"]},
        )
    
    def get_module(self, name: str) -> Optional[ModuleInfo]:
        """Get module info by name."""
        return self._modules.get(name)
    
    def list_modules(self) -> List[str]:
        """List all loaded module names."""
        return list(self._modules.keys())
    
    def list_enabled_modules(self) -> List[str]:
        """List enabled module names."""
        return [name for name, mod in self._modules.items() if mod.enabled]
    
    def unload_module(self, name: str) -> bool:
        """Unload a module."""
        if name not in self._modules:
            return False
        
        del self._modules[name]
        if name in self._module_data:
            del self._module_data[name]
        
        self._trigger_hook("on_unload", name)
        return True
    
    def enable_module(self, name: str) -> bool:
        """Enable a module."""
        if name not in self._modules:
            return False
        
        self._modules[name].enabled = True
        return True
    
    def disable_module(self, name: str) -> bool:
        """Disable a module."""
        if name not in self._modules:
            return False
        
        self._modules[name].enabled = False
        return True
    
    def get_capabilities(self, module_name: Optional[str] = None) -> List[str]:
        """Get capabilities from module(s)."""
        if module_name:
            module = self.get_module(module_name)
            return module.capabilities if module else []
        
        # All capabilities from all modules
        caps = []
        for mod in self._modules.values():
            caps.extend(mod.capabilities)
        return caps
    
    def get_tools(self, module_name: Optional[str] = None) -> List[str]:
        """Get tools from module(s)."""
        if module_name:
            module = self.get_module(module_name)
            return module.tools if module else []
        
        # All tools from all modules
        tools = []
        for mod in self._modules.values():
            tools.extend(mod.tools)
        return tools
    
    def get_system_prompt(self, module_name: str) -> Optional[str]:
        """Get system prompt for a module."""
        module = self.get_module(module_name)
        if module is None or module.system_prompt is None:
            return None
        
        # Try to load from file
        prompt_path = Path(module.path) / module.system_prompt
        if prompt_path.exists():
            with open(prompt_path) as f:
                return f.read()
        
        return None
    
    def get_scratch_template(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Get scratch template for a module."""
        module = self.get_module(module_name)
        if module is None or module.scratch_template is None:
            return None
        
        # Try to load from file
        template_path = Path(module.path) / module.scratch_template
        if template_path.exists():
            with open(template_path) as f:
                return yaml.safe_load(f)
        
        return None
    
    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a hook callback."""
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    def _trigger_hook(self, event: str, *args: Any) -> None:
        """Trigger all hooks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass  # Don't let hook errors break loading
    
    def get_stats(self) -> Dict[str, Any]:
        """Get module loader statistics."""
        return {
            "total_modules": len(self._modules),
            "enabled_modules": sum(1 for m in self._modules.values() if m.enabled),
            "disabled_modules": sum(1 for m in self._modules.values() if not m.enabled),
            "modules": {
                name: {
                    "version": mod.version,
                    "enabled": mod.enabled,
                    "capabilities": mod.capabilities,
                }
                for name, mod in self._modules.items()
            },
        }


def create_module_loader(registry_path: Optional[str] = None,
                         auto_load: bool = True) -> ModuleLoader:
    """
    Factory function to create a module loader.
    
    Args:
        registry_path: Path to module registry YAML
        auto_load: Whether to auto-load modules on creation
    
    Returns:
        Configured ModuleLoader instance
    """
    config = ModuleConfig(
        registry_path=registry_path or "engram/modules/module_registry.yaml",
        auto_load=auto_load,
    )
    
    loader = ModuleLoader(config)
    
    if auto_load:
        loader.load_registry()
    
    return loader
