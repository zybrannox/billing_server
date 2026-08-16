from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_type = Column(String)
    assigned_to = Column(String)
    priority = Column(String)
    client_status = Column(String)
    print_status = Column(
        String(20),
        default="Pending",
        nullable=False)
    start_date = Column(DateTime)
    delivery_date = Column(DateTime)
    file_paths = Column(JSON, default=list)
    description = Column(String, nullable=True)
