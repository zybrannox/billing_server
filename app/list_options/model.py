from datetime import datetime

from pydantic import BaseModel, field_validator


# A hardcoded allowlist of categories, not free-text - a typo'd category
# ("projecttype" instead of "project_type") would silently create an
# orphan list nothing ever reads, so this rejects that at the API boundary
# instead of only ever surfacing as "why is my new option not showing up".
# Add to this tuple (and the frontend's matching field->category mapping)
# whenever another dropdown moves onto this system.
VALID_CATEGORIES = ("project_type",)


class ListOptionCreate(BaseModel):
    category: str
    value: str

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


class ListOptionRead(BaseModel):
    id: int
    category: str
    value: str
    sort_order: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
