"""CRM service for customer management."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.modules.crm.models import TelegramCustomer
from biotact.modules.crm.schemas import CustomerCreate, CustomerUpdate, FamilyMember

logger = logging.getLogger(__name__)


class CRMService:
    """Service for managing Telegram customers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> TelegramCustomer | None:
        """Get customer by Telegram ID."""
        result = await self.session.execute(
            select(TelegramCustomer).where(
                TelegramCustomer.telegram_id == telegram_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str | None = None,
        username: str | None = None,
    ) -> tuple[TelegramCustomer, bool]:
        """Get existing customer or create new one.
        
        Returns:
            Tuple of (customer, created) where created is True if new.
        """
        customer = await self.get_by_telegram_id(telegram_id)
        
        if customer:
            return customer, False
        
        # Create new customer
        customer = TelegramCustomer(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
        )
        self.session.add(customer)
        await self.session.flush()
        await self.session.refresh(customer)
        
        logger.info(f"Created new customer: telegram_id={telegram_id}")
        return customer, True

    async def create_or_update(self, data: CustomerCreate) -> TelegramCustomer:
        """Create new customer or update existing."""
        customer = await self.get_by_telegram_id(data.telegram_id)
        
        if customer:
            # Update existing
            update_data = data.model_dump(exclude={"telegram_id"}, exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    setattr(customer, field, value)
        else:
            # Create new
            customer = TelegramCustomer(**data.model_dump())
            self.session.add(customer)
        
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def update(
        self,
        telegram_id: int,
        data: CustomerUpdate,
    ) -> TelegramCustomer | None:
        """Update customer fields."""
        customer = await self.get_by_telegram_id(telegram_id)
        if not customer:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(customer, field, value)
        
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def add_problems(
        self,
        telegram_id: int,
        problems: list[str],
    ) -> TelegramCustomer | None:
        """Add problem tags to customer."""
        customer = await self.get_by_telegram_id(telegram_id)
        if not customer:
            return None
        
        # Add unique problems
        current = set(customer.problems or [])
        current.update(problems)
        customer.problems = list(current)
        
        await self.session.flush()
        await self.session.refresh(customer)
        
        logger.info(f"Updated problems for {telegram_id}: {customer.problems}")
        return customer

    async def add_family_member(
        self,
        telegram_id: int,
        member: FamilyMember,
    ) -> TelegramCustomer | None:
        """Add or update family member."""
        customer = await self.get_by_telegram_id(telegram_id)
        if not customer:
            return None
        
        family = list(customer.family or [])
        member_dict = member.model_dump()
        
        # Check if member with same name exists - update
        updated = False
        for i, existing in enumerate(family):
            if existing.get("name", "").lower() == member.name.lower():
                family[i] = member_dict
                updated = True
                break
        
        if not updated:
            family.append(member_dict)
        
        customer.family = family
        await self.session.flush()
        await self.session.refresh(customer)
        
        logger.info(f"Updated family for {telegram_id}: {len(family)} members")
        return customer

    async def add_purchase(
        self,
        telegram_id: int,
        product: str,
    ) -> TelegramCustomer | None:
        """Add purchased product."""
        customer = await self.get_by_telegram_id(telegram_id)
        if not customer:
            return None
        
        products = set(customer.purchased_products or [])
        products.add(product)
        customer.purchased_products = list(products)
        
        await self.session.flush()
        await self.session.refresh(customer)
        
        logger.info(f"Added purchase for {telegram_id}: {product}")
        return customer

    def format_context_for_prompt(self, customer: TelegramCustomer) -> str:
        """Format customer data for AI prompt context."""
        parts = []
        
        # Name
        name = customer.first_name or "Клиент"
        parts.append(f"Клиент: {name}")
        
        # Problems
        if customer.problems:
            problems_map = {
                "immunity": "иммунитет",
                "gut": "ЖКТ/пищеварение",
                "stress": "стресс/нервы",
                "skin": "кожа",
            }
            translated = [problems_map.get(p, p) for p in customer.problems]
            parts.append(f"Проблемы: {', '.join(translated)}")
        
        # Family
        if customer.family:
            family_parts = []
            for member in customer.family:
                m_name = member.get("name", "")
                m_rel = member.get("relation", "")
                m_age = member.get("age")
                age_str = f", {m_age} лет" if m_age else ""
                family_parts.append(f"{m_name} ({m_rel}{age_str})")
            parts.append(f"Семья: {'; '.join(family_parts)}")
        
        # Purchases
        if customer.purchased_products:
            parts.append(f"Покупал: {', '.join(customer.purchased_products)}")
        
        # AI notes
        if customer.ai_notes:
            parts.append(f"Заметки: {customer.ai_notes}")
        
        return ". ".join(parts)

    async def get_customers_paginated(
        self,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        problem: str | None = None,
    ) -> tuple[list[TelegramCustomer], int]:
        """Get paginated list of customers with optional filters.
        
        Args:
            page: Page number (1-indexed)
            size: Items per page
            search: Search by name or username
            problem: Filter by problem tag
            
        Returns:
            Tuple of (customers, total_count)
        """
        from sqlalchemy import func, or_
        
        query = select(TelegramCustomer)
        count_query = select(func.count(TelegramCustomer.id))
        
        # Apply filters
        if search:
            search_filter = or_(
                TelegramCustomer.first_name.ilike(f"%{search}%"),
                TelegramCustomer.last_name.ilike(f"%{search}%"),
                TelegramCustomer.username.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)
        
        if problem:
            problem_filter = func.array_position(TelegramCustomer.problems, problem).isnot(None)
            query = query.where(problem_filter)
            count_query = count_query.where(problem_filter)
        
        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply pagination and ordering
        offset = (page - 1) * size
        query = query.order_by(TelegramCustomer.created_at.desc())
        query = query.offset(offset).limit(size)
        
        result = await self.session.execute(query)
        customers = list(result.scalars().all())
        
        return customers, total

    async def get_stats(self) -> dict[str, Any]:
        """Get CRM statistics.
        
        Returns:
            Dictionary with stats: total_customers, new_today, with_phone, with_purchases, by_problem
        """
        from datetime import datetime, timezone
        from sqlalchemy import func, and_
        
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Total customers
        total_result = await self.session.execute(
            select(func.count(TelegramCustomer.id))
        )
        total_customers = total_result.scalar() or 0
        
        # New today
        new_today_result = await self.session.execute(
            select(func.count(TelegramCustomer.id)).where(
                TelegramCustomer.created_at >= today_start
            )
        )
        new_today = new_today_result.scalar() or 0
        
        # With phone
        with_phone_result = await self.session.execute(
            select(func.count(TelegramCustomer.id)).where(
                TelegramCustomer.phone.isnot(None)
            )
        )
        with_phone = with_phone_result.scalar() or 0
        
        # With purchases
        with_purchases_result = await self.session.execute(
            select(func.count(TelegramCustomer.id)).where(
                and_(
                    TelegramCustomer.purchased_products.isnot(None),
                    func.array_length(TelegramCustomer.purchased_products, 1) > 0
                )
            )
        )
        with_purchases = with_purchases_result.scalar() or 0
        
        # By problem - count for each problem type
        problems_list = ["immunity", "gut", "stress", "skin"]
        by_problem: dict[str, int] = {}
        
        for problem in problems_list:
            result = await self.session.execute(
                select(func.count(TelegramCustomer.id)).where(
                    func.array_position(TelegramCustomer.problems, problem).isnot(None)
                )
            )
            by_problem[problem] = result.scalar() or 0
        
        return {
            "total_customers": total_customers,
            "new_today": new_today,
            "with_phone": with_phone,
            "with_purchases": with_purchases,
            "by_problem": by_problem,
        }
