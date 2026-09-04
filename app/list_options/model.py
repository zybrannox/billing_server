from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# A hardcoded allowlist of categories, not free-text - a typo'd category
# ("projecttype" instead of "project_type") would silently create an
# orphan list nothing ever reads, so this rejects that at the API boundary
# instead of only ever surfacing as "why is my new option not showing up".
# Add to this tuple (and the frontend's matching field->category mapping)
# whenever another dropdown moves onto this system.
VALID_CATEGORIES = ("project_type", "item_type")

# Categories where each option carries a price - see ListOption.rate.
# "item_type" backs the invoice line-item catalog (Flex/Photo Frame/...
# each priced per sq ft, see GenerateInvoice.tsx); nothing else uses rate.
PRICED_CATEGORIES = ("item_type",)


class ListOptionCreate(BaseModel):
    category: str
    value: str
    rate: Optional[float] = Field(default=None, ge=0)

    @field_validator("category")
    @classmethod
    def category_must_be_known(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Unknown category '{v}'")
        return v

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Value cannot be blank")
        return v

    @model_validator(mode="after")
    def rate_required_for_priced_categories(self) -> "ListOptionCreate":
        if self.category in PRICED_CATEGORIES and self.rate is None:
            raise ValueError(f"A rate is required for '{self.category}' options")
        return self


class ListOptionRead(BaseModel):
    id: int
    category: str
    value: str
    sort_order: int
    is_active: bool
    created_at: datetime
    rate: Optional[float] = None

    model_config = {"from_attributes": True}
