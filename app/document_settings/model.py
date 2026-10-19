import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Kept in step with the presets in src/documents/documentTheme.ts - the
# backend only validates the name, the frontend owns what each one looks like.
Theme = Literal[
    "indigo", "emerald", "teal", "crimson", "amber", "slate", "violet", "terracotta", "custom"
]
# Layout styles - same rule: the backend validates the name, the frontend
# (src/documents/documentTemplates.ts) owns what each one looks like.
Template = Literal["classic", "minimal", "modern", "compact"]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class DocumentSettingsRead(BaseModel):
    business_name: str
    tagline: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    has_logo: bool = False
    template: str
    theme: str
    custom_color: Optional[str] = None
    show_top_bar: bool
    show_payment_history: bool
    tax_label: str
    tax_note: str
    invoice_terms: Optional[str] = None
    quotation_terms: Optional[str] = None
    footer_message: str

    model_config = {"from_attributes": True}


class DocumentSettingsUpdate(BaseModel):
    business_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    tagline: Optional[str] = Field(default=None, max_length=160)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=255)
    tax_id: Optional[str] = Field(default=None, max_length=40)
    template: Optional[Template] = None
    theme: Optional[Theme] = None
    custom_color: Optional[str] = None
    show_top_bar: Optional[bool] = None
    show_payment_history: Optional[bool] = None
    tax_label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    tax_note: Optional[str] = Field(default=None, max_length=80)
    invoice_terms: Optional[str] = Field(default=None, max_length=1000)
    quotation_terms: Optional[str] = Field(default=None, max_length=1000)
    footer_message: Optional[str] = Field(default=None, max_length=200)

    @field_validator("custom_color")
    @classmethod
    def _valid_hex(cls, v):
        if v in (None, ""):
            return None
        if not _HEX.match(v):
            raise ValueError("custom_color must be a #RRGGBB hex value")
        return v.lower()
