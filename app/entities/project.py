from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
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
        default="In Progress",
        nullable=False)
    start_date = Column(DateTime)
    delivery_date = Column(DateTime)
    description = Column(String, nullable=True)
    # Nullable: existing projects predate this column, and not every
    # historical row will have a matching customer.
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    customer = relationship("Customer")

    # Replaces the old file_paths JSON column (see entities/project_file.py
    # for why) - order_by keeps upload order stable since nothing else
    # tracks it explicitly.
    files = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectFile.id",
    )

    @property
    def file_paths(self):
        """Back-compat shim so the API/frontend contract (and any code
        still written against `.file_paths`) is unaffected by the storage
        move from a JSON blob to the indexed `files` relationship."""
        return self.files

    @property
    def customer_name(self):
        return f"{self.customer.first_name} {self.customer.last_name}" if self.customer else None

    # Order-lifecycle milestones, set server-side (never client-supplied) by
    # the dedicated /design-completed and /delivered endpoints. Nullable =
    # not reached yet. These are the future trigger points for customer
    # notifications (not implemented yet - see conversation).
    design_completed_at = Column(DateTime, nullable=True)
    design_completed_by = Column(String, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    delivered_by = Column(String, nullable=True)
