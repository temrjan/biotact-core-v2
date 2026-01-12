"""Department modules for BIOTACT.

This package contains module configurations and services for each department.
Modules are divided into two types:

- Command-based (Dashboard): Use Function Calling to execute actions
- RAG-based (CallCenter, Marketing, HR): Use knowledge retrieval for answers

Usage:
    >>> from biotact.modules import module_registry, ModuleType
    >>> from biotact.modules.command.dashboard import DashboardConfig
    >>>
    >>> # Register module at startup
    >>> module_registry.register(DashboardConfig())
    >>>
    >>> # Get module by department_id
    >>> config = module_registry.get("dashboard")
"""

from biotact.modules.base import (
    BaseModuleConfig,
    CommandModuleConfig,
    ModuleType,
    RAGModuleConfig,
)
from biotact.modules.registry import ModuleRegistry, module_registry

__all__ = [
    "BaseModuleConfig",
    "CommandModuleConfig",
    "ModuleRegistry",
    "ModuleType",
    "RAGModuleConfig",
    "module_registry",
]
