from pydantic import BaseModel


class ShareLinkResponse(BaseModel):
    url: str
