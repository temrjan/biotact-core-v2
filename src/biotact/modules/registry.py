"""Module registry for BIOTACT departments.

Centralized registry for all department module configurations.
Modules are registered at application startup and retrieved by department_id.
"""

from typing import TypeVar

from biotact.modules.base import (
    BaseModuleConfig,
    CommandModuleConfig,
    ModuleType,
    RAGModuleConfig,
)

T = TypeVar("T", bound=BaseModuleConfig)


class ModuleRegistry:
    """Registry for department module configurations.

    This is a singleton-like class that holds all registered modules.
    Modules are registered during application initialization.

    Example:
        >>> from biotact.modules.registry import module_registry
        >>> from biotact.modules.command.dashboard import DashboardConfig
        >>>
        >>> # Register module
        >>> module_registry.register(DashboardConfig())
        >>>
        >>> # Get module by department_id
        >>> config = module_registry.get("dashboard")
        >>> config.display_name
        'Финансы'
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._modules: dict[str, BaseModuleConfig] = {}

    def register(self, config: BaseModuleConfig) -> None:
        """Register a module configuration.

        Args:
            config: Module configuration to register.

        Raises:
            ValueError: If module with same department_id already registered.
        """
        if config.department_id in self._modules:
            raise ValueError(f"Module '{config.department_id}' is already registered")
        self._modules[config.department_id] = config

    def get(self, department_id: str) -> BaseModuleConfig | None:
        """Get module configuration by department_id.

        Args:
            department_id: Unique department identifier.

        Returns:
            Module configuration or None if not found.
        """
        return self._modules.get(department_id)

    def get_or_raise(self, department_id: str) -> BaseModuleConfig:
        """Get module configuration or raise if not found.

        Args:
            department_id: Unique department identifier.

        Returns:
            Module configuration.

        Raises:
            KeyError: If module not found.
        """
        config = self.get(department_id)
        if config is None:
            raise KeyError(f"Module '{department_id}' not found in registry")
        return config

    def get_command_module(self, department_id: str) -> CommandModuleConfig | None:
        """Get command-type module configuration.

        Args:
            department_id: Unique department identifier.

        Returns:
            Command module configuration or None.
        """
        config = self.get(department_id)
        if config and isinstance(config, CommandModuleConfig):
            return config
        return None

    def get_rag_module(self, department_id: str) -> RAGModuleConfig | None:
        """Get RAG-type module configuration.

        Args:
            department_id: Unique department identifier.

        Returns:
            RAG module configuration or None.
        """
        config = self.get(department_id)
        if config and isinstance(config, RAGModuleConfig):
            return config
        return None

    def all(self) -> list[BaseModuleConfig]:
        """Get all registered modules.

        Returns:
            List of all module configurations.
        """
        return list(self._modules.values())

    def active(self) -> list[BaseModuleConfig]:
        """Get all active modules.

        Returns:
            List of active module configurations.
        """
        return [m for m in self._modules.values() if m.is_active]

    def by_type(self, module_type: ModuleType) -> list[BaseModuleConfig]:
        """Get modules by type.

        Args:
            module_type: Type of modules to filter.

        Returns:
            List of modules matching the type.
        """
        return [m for m in self._modules.values() if m.module_type == module_type]

    def command_modules(self) -> list[CommandModuleConfig]:
        """Get all command-type modules.

        Returns:
            List of command module configurations.
        """
        return [m for m in self._modules.values() if isinstance(m, CommandModuleConfig)]

    def rag_modules(self) -> list[RAGModuleConfig]:
        """Get all RAG-type modules.

        Returns:
            List of RAG module configurations.
        """
        return [m for m in self._modules.values() if isinstance(m, RAGModuleConfig)]

    def unregister(self, department_id: str) -> bool:
        """Unregister a module (mainly for testing).

        Args:
            department_id: Module to unregister.

        Returns:
            True if module was unregistered, False if not found.
        """
        if department_id in self._modules:
            del self._modules[department_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered modules (mainly for testing)."""
        self._modules.clear()

    def __len__(self) -> int:
        """Return number of registered modules."""
        return len(self._modules)

    def __contains__(self, department_id: str) -> bool:
        """Check if module is registered."""
        return department_id in self._modules


# Global registry instance
module_registry = ModuleRegistry()
