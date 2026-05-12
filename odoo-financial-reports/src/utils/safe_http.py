"""Layers 3 & 5: HTTP method whitelist + JSON-RPC payload inspector."""
from __future__ import annotations

import requests

ALLOWED_HTTP_METHODS: frozenset[str] = frozenset({"GET", "POST"})

_FORBIDDEN_PAYLOAD_METHODS: frozenset[str] = frozenset({
    "create", "write", "unlink", "copy", "copy_data",
    "create_multi", "write_multi", "browse_write",
    "toggle_active", "archive", "unarchive",
    "load", "import_data", "message_post", "message_subscribe",
    "action_post", "action_cancel", "action_draft",
    "button_cancel", "button_confirm", "button_draft",
})

_FORBIDDEN_PAYLOAD_PREFIXES: tuple[str, ...] = (
    "create_", "write_", "unlink_", "action_", "button_",
    "do_", "set_", "update_", "delete_", "remove_",
    "send_", "post_", "cancel_", "confirm_", "validate_",
    "approve_", "reject_", "submit_", "process_",
)


class SafeHttpClient(requests.Session):
    """
    requests.Session subclass that enforces read-only at the HTTP transport layer.

    Layer 3: blocks HTTP methods other than GET and POST.
    Layer 5: inspects every Odoo JSON-RPC payload and blocks requests whose
             `params.method` is a forbidden write operation.

    Because this extends requests.Session, it is a drop-in replacement —
    cookies, headers, and connection pooling all work identically.
    """

    def __init__(self, audit_logger=None) -> None:
        super().__init__()
        self._audit = audit_logger

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        upper = method.upper()

        # ── Layer 3: HTTP method whitelist ──────────────────────────────
        if upper not in ALLOWED_HTTP_METHODS:
            raise PermissionError(
                f"BLOCKED: HTTP method {method!r} is not allowed. "
                f"Only GET and POST are permitted by this read-only client."
            )

        # ── Layer 5: JSON-RPC payload inspection ────────────────────────
        json_payload = kwargs.get("json")
        if json_payload is not None:
            self._inspect_payload(json_payload, url)

        # Track HTTP method usage in audit log
        if self._audit is not None:
            self._audit.log_http(upper)

        return super().request(method, url, **kwargs)

    # ------------------------------------------------------------------ #

    def _inspect_payload(self, payload: object, url: str) -> None:
        """
        Check the Odoo JSON-RPC payload dict for forbidden method names.
        Only `params.method` is inspected — this is the field Odoo uses to
        dispatch model methods (search_read, create, write, etc.).
        """
        if not isinstance(payload, dict):
            return
        params = payload.get("params")
        if not isinstance(params, dict):
            return
        odoo_method = params.get("method")
        if not isinstance(odoo_method, str) or not odoo_method:
            return

        if odoo_method in _FORBIDDEN_PAYLOAD_METHODS:
            raise PermissionError(
                f"BLOCKED at HTTP layer: Odoo method '{odoo_method}' is "
                f"forbidden. URL={url}"
            )
        if odoo_method.startswith(_FORBIDDEN_PAYLOAD_PREFIXES):
            raise PermissionError(
                f"BLOCKED at HTTP layer: Odoo method '{odoo_method}' matches "
                f"a forbidden prefix pattern. URL={url}"
            )
