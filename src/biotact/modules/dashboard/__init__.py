"""Dashboard module for financial tracking."""

from biotact.modules.dashboard.config import dashboard_config
from biotact.modules.dashboard.service import DashboardService

__all__ = [
    "DashboardService",
    "dashboard_config",
]
