from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
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
    file_paths = Column(JSON, default=list)
    description = Column(String, nullable=True)
    # Nullable: existing projects predate this column, and not every
    # historical row will have a matching customer.
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    customer = relationship("Customer")

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
