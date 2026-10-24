from pydantic import BaseModel, ConfigDict


class ResponseModel(BaseModel):
    """Base for models the API returns.

    The server always serialises every field (including ones that default to
    None / []), so the published OpenAPI schema marks them required. Without
    this flag pydantic describes defaulted fields as optional, and the
    TypeScript types generated for the frontend would force `?.`/`?? []` checks
    for values that are always there.
    """

    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)
