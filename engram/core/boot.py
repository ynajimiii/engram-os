"""
Boot - Initialization and startup sequences.

Phase 00: Foundation
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .probe import Probe

logger = logging.getLogger(__name__)


@dataclass
class BootConfig:
    """Configuration for boot sequence."""
    debug: bool = False
    log_level: str = "INFO"
    modules: List[str] = None
    session_dir: str = "engram/sessions"

    def __post_init__(self):
        if self.modules is None:
            self.modules = []


class BootSequence:
    """Manages the initialization and startup of Engram OS."""

    def __init__(self, config: Optional[BootConfig] = None):
        self.config = config or BootConfig()
        self._initialized = False
        self._components: Dict[str, Any] = {}
        self._probe = Probe()

    def run(self) -> "BootSequence":
        """Execute the boot sequence."""
        self._setup_logging()
        self._initialize_components()
        self._validate_contracts()
        self._initialized = True

        logger.info("Engram OS booted successfully")
        return self

    def _setup_logging(self) -> None:
        """Configure logging based on boot config."""
        level = logging.DEBUG if self.config.debug else getattr(
            logging, self.config.log_level.upper()
        )

        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    def _initialize_components(self) -> None:
        """Initialize core components."""
        # Register probe
        self._components["probe"] = self._probe

        # Discover capabilities
        capabilities = self._probe.discover_capabilities()
        logger.debug(f"Discovered capabilities: {capabilities}")

        # Initialize configured modules
        for module_name in self.config.modules:
            self._load_module(module_name)

    def _load_module(self, name: str) -> None:
        """Load a module by name."""
        try:
            # Placeholder for module loading logic
            logger.debug(f"Loading module: {name}")
            self._components[f"module:{name}"] = True
        except Exception as e:
            logger.warning(f"Failed to load module {name}: {e}")

    def _validate_contracts(self) -> None:
        """Validate core contracts."""
        # Placeholder for contract validation
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if boot sequence completed."""
        return self._initialized

    def get_component(self, name: str) -> Optional[Any]:
        """Retrieve a component by name."""
        return self._components.get(name)

    def shutdown(self) -> None:
        """Gracefully shutdown Engram OS."""
        logger.info("Shutting down Engram OS")
        self._components.clear()
        self._initialized = False


def boot(config: Optional[BootConfig] = None) -> BootSequence:
    """Convenience function to boot Engram OS."""
    return BootSequence(config).run()


def boot_system(
    weights_mb: int = 14000,
    n_ctx: int = 8192,
    scratch_mb: int = 512
) -> tuple:
    """
    Boot the ENGRAM system with specified memory parameters.
    
    Args:
        weights_mb: Model weights size in MB
        n_ctx: Context length
        scratch_mb: Scratch memory in MB
    
    Returns:
        Tuple of (MemoryContract, VectorDB)
    """
    from engram.core.contract import MemoryContract, calculate_memory_budget
    from engram.core.vector_db import VectorDB
    from engram.core.probe import get_hardware_state
    
    # Get hardware state
    hw = get_hardware_state()
    
    # Calculate memory budget
    contract = calculate_memory_budget(
        weights_mb=weights_mb,
        n_ctx=n_ctx,
        scratch_mb=scratch_mb,
        vram_total_mb=hw["vram_total_mb"]
    )
    
    # Create vector DB with appropriate dimension
    from engram.cli._config import load_config as _lc
    _cfg = _lc()
    db = VectorDB(
        dimension=_cfg.get('vector_db_dim', 384),
        max_hot_size=_cfg.get('max_hot_size', 100),
    )

    return contract, db
