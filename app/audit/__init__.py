# Only the service functions are re-exported here: the router lives in
# app.audit.controller (imported by app.main). Importing it from this package
# would make every service that records an audit row import the auth
# dependencies, which import those services - a cycle.
from .service import label_of, record as record_audit

__all__ = ["label_of", "record_audit"]
