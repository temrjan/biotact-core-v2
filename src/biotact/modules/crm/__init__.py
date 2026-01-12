"""CRM module for managing Telegram customer profiles."""

from biotact.modules.crm.models import TelegramCustomer
from biotact.modules.crm.router import router
from biotact.modules.crm.service import CRMService

__all__ = ["TelegramCustomer", "CRMService", "router"]
