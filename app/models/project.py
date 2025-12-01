from typing import List
from pydantic import BaseModel

# Project model
class Project(BaseModel):
    name: str
    assignee: str
    started: str
    delivery: str
    status: str
    priority: str
    description: str | None = None
    client_status: str
    images: List[str]