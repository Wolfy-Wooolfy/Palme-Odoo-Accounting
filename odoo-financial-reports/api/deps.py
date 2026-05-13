from functools import lru_cache

from src.odoo_client import OdooReadOnlyClient
from src.utils.audit import AuditLogger


@lru_cache(maxsize=1)
def get_odoo_client() -> OdooReadOnlyClient:
    """Singleton Odoo client — connects once, reused for every request."""
    return OdooReadOnlyClient(audit_logger=get_audit_logger())


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    return AuditLogger()
