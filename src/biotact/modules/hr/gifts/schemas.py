"""HR Gifts Pydantic schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from biotact.modules.hr.gifts.models import GiftStatus


class GiftCreateRequest(BaseModel):
    """Schema for creating a gift request.

    responsible_person_id is intentionally absent: the service assigns
    the authenticated creator. Free-form IDs caused FK 500s in prod
    (2026-06-11) and users cannot know internal IDs anyway.
    """

    event_id: int | None = None
    initiator: str = Field(..., max_length=300)
    recipient: str = Field(..., max_length=300)
    occasion: str = Field(..., max_length=200)
    category: str = Field(..., max_length=100)
    gift_name: str | None = Field(None, max_length=300)
    budget: int = Field(..., ge=0)
    vendor: str | None = Field(None, max_length=200)
    presentation_date: date | None = None
    comment: str | None = Field(None, max_length=1000)


class GiftUpdateRequest(BaseModel):
    """Schema for partially updating a gift request.

    responsible_person_id is not updatable — it is always the creator
    (see GiftCreateRequest). Reassignment needs a user picker first.
    """

    event_id: int | None = None
    initiator: str | None = Field(None, max_length=300)
    recipient: str | None = Field(None, max_length=300)
    occasion: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    gift_name: str | None = Field(None, max_length=300)
    budget: int | None = Field(None, ge=0)
    vendor: str | None = Field(None, max_length=200)
    presentation_date: date | None = None
    comment: str | None = Field(None, max_length=1000)


class GiftResponse(BaseModel):
    """Gift request response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    initiator: str
    recipient: str
    occasion: str
    category: str
    gift_name: str | None
    budget: int
    vendor: str | None
    status: GiftStatus
    presentation_date: date | None
    responsible_person_id: int
    comment: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class GiftListResponse(BaseModel):
    """Paginated list of gift requests."""

    items: list[GiftResponse]
    total: int
    page: int
    size: int
    pages: int


class GiftStatusUpdateRequest(BaseModel):
    """Schema for updating gift request status."""

    status: GiftStatus
    comment: str | None = Field(None, max_length=1000)


class GiftHistoryResponse(BaseModel):
    """Gift status history response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int | None
    from_status: GiftStatus
    to_status: GiftStatus
    changed_by: int
    comment: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Budget Plan schemas
# ---------------------------------------------------------------------------


class BudgetPlanCreateRequest(BaseModel):
    """Schema for creating a monthly budget plan."""

    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)
    planned_amount: int = Field(..., ge=0)


class BudgetPlanUpdateRequest(BaseModel):
    """Schema for partially updating a budget plan."""

    month: int | None = Field(None, ge=1, le=12)
    year: int | None = Field(None, ge=2000, le=2100)
    planned_amount: int | None = Field(None, ge=0)


class BudgetPlanResponse(BaseModel):
    """Budget plan response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    month: int
    year: int
    planned_amount: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class BudgetPlanListResponse(BaseModel):
    """Paginated list of budget plans."""

    items: list[BudgetPlanResponse]
    total: int
    page: int
    size: int
    pages: int


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class GiftReportResponse(BaseModel):
    """Monthly gift report — 1:1 on Table 1 from doc_content.txt."""

    month: int
    year: int
    total_requests: int
    planned_amount: int
    actual_amount: int
    delta: int
    avg_check: int


# ---------------------------------------------------------------------------
# KPI schemas
# ---------------------------------------------------------------------------


class KPICreateRequest(BaseModel):
    """Schema for creating a monthly KPI record."""

    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)
    employee_congrats_planned: int = Field(0, ge=0)
    employee_congrats_actual: int = Field(0, ge=0)
    partner_congrats_planned: int = Field(0, ge=0)
    partner_congrats_actual: int = Field(0, ge=0)
    budget_compliance_planned: int = Field(100, ge=0)
    budget_compliance_actual: int = Field(0, ge=0)
    satisfaction_planned: int = Field(0, ge=0)
    satisfaction_actual: int = Field(0, ge=0)
    timely_closure_planned: int = Field(0, ge=0)
    timely_closure_actual: int = Field(0, ge=0)
    notes: str | None = Field(None, max_length=2000)


class KPIUpdateRequest(BaseModel):
    """Schema for partially updating a KPI record.

    month and year are immutable — not present here.
    """

    employee_congrats_planned: int | None = Field(None, ge=0)
    employee_congrats_actual: int | None = Field(None, ge=0)
    partner_congrats_planned: int | None = Field(None, ge=0)
    partner_congrats_actual: int | None = Field(None, ge=0)
    budget_compliance_planned: int | None = Field(None, ge=0)
    budget_compliance_actual: int | None = Field(None, ge=0)
    satisfaction_planned: int | None = Field(None, ge=0)
    satisfaction_actual: int | None = Field(None, ge=0)
    timely_closure_planned: int | None = Field(None, ge=0)
    timely_closure_actual: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)


class KPIResponse(BaseModel):
    """KPI response with computed completion percentages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    month: int
    year: int

    employee_congrats_planned: int
    employee_congrats_actual: int
    partner_congrats_planned: int
    partner_congrats_actual: int
    budget_compliance_planned: int
    budget_compliance_actual: int
    satisfaction_planned: int
    satisfaction_actual: int
    timely_closure_planned: int
    timely_closure_actual: int

    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def employee_congrats_pct(self) -> int:
        if self.employee_congrats_planned == 0:
            return 0
        return round(
            self.employee_congrats_actual / self.employee_congrats_planned * 100
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def partner_congrats_pct(self) -> int:
        if self.partner_congrats_planned == 0:
            return 0
        return round(self.partner_congrats_actual / self.partner_congrats_planned * 100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def budget_compliance_pct(self) -> int:
        if self.budget_compliance_planned == 0:
            return 0
        return round(
            self.budget_compliance_actual / self.budget_compliance_planned * 100
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def satisfaction_pct(self) -> int:
        if self.satisfaction_planned == 0:
            return 0
        return round(self.satisfaction_actual / self.satisfaction_planned * 100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def timely_closure_pct(self) -> int:
        if self.timely_closure_planned == 0:
            return 0
        return round(self.timely_closure_actual / self.timely_closure_planned * 100)


class KPIListResponse(BaseModel):
    """Paginated list of KPI records."""

    items: list[KPIResponse]
    total: int
    page: int
    size: int
    pages: int
