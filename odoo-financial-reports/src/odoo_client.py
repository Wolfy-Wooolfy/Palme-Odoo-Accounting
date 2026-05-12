"""
READ-ONLY Odoo client with 7-layer write protection.

Layer 1: Method blocklist  (FORBIDDEN_METHODS + FORBIDDEN_PREFIXES)
Layer 2: Method allowlist  (ALLOWED_METHODS — anything else is blocked)
Layer 3: HTTP method whitelist  (GET and POST only, via SafeHttpClient)
Layer 4: Immutable read-only flag  (_READ_ONLY class var + __read_only instance var)
Layer 5: HTTP payload inspector  (SafeHttpClient checks every JSON-RPC body)
Layer 6: Pre-flight self-test  (run via safety_test.run_safety_self_test)
Layer 7: Audit log + SAFETY_REPORT.md  (AuditLogger)
"""
from __future__ import annotations

import os
import re
import xmlrpc.client
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.db_detector import DatabaseDetector
from src.utils import logger
from src.utils.safe_http import SafeHttpClient

load_dotenv()


def _normalize_url(raw: str) -> str:
    """Return scheme+host only — strip any path, hash, or query string."""
    p = urlparse(raw.strip())
    return f"{p.scheme}://{p.netloc}"


# ── Layer 1: blocklist ──────────────────────────────────────────────────────

FORBIDDEN_METHODS: frozenset[str] = frozenset({
    "create", "write", "unlink", "copy", "copy_data",
    "create_multi", "write_multi", "browse_write",
    "toggle_active", "archive", "unarchive",
    "load", "import_data", "message_post", "message_subscribe",
})

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "create_", "write_", "unlink_", "action_", "button_",
    "do_", "set_", "update_", "delete_", "remove_",
    "send_", "post_", "cancel_", "confirm_", "validate_",
    "approve_", "reject_", "submit_", "process_",
)

# ── Layer 2: allowlist ──────────────────────────────────────────────────────

ALLOWED_METHODS: frozenset[str] = frozenset({
    "search", "read", "search_read", "search_count",
    "fields_get", "name_search", "name_get", "default_get",
    "check_access_rights", "check_access_rule",
    "get_metadata",
})


class OdooReadOnlyClient:
    # ── Layer 4: class-level immutable flag ────────────────────────────────
    _READ_ONLY: bool = True

    def __init__(
        self,
        skip_connect: bool = False,
        audit_logger=None,
    ) -> None:
        # ── Layer 4: instance-level flag (name-mangled → harder to tamper) ─
        self.__read_only: bool = True

        self._audit = audit_logger

        self.url: str = _normalize_url(os.environ["ODOO_URL"])
        self.username: str = os.environ["ODOO_USERNAME"]
        self.api_key: str = os.environ["ODOO_API_KEY"]

        self.uid: int | None = None
        self.session_id: str | None = None
        self.version_info: dict = {}
        self.api_method: str = "test-mode" if skip_connect else "unknown"

        # ── SafeHttpClient: Layers 3 & 5 ───────────────────────────────────
        self._http = SafeHttpClient(audit_logger=audit_logger)
        self._http.headers.update({"Content-Type": "application/json"})

        # DB resolution
        raw_db = os.environ.get("ODOO_DB", "").strip()
        if raw_db:
            logger.info(f"Using DB from .env: {raw_db}")
            self.db: str | None = raw_db
            self._db_detection_info: dict = {
                "success": True,
                "database": raw_db,
                "strategy_used": "env_variable",
                "candidates_tried": [],
                "message": f"Database '{raw_db}' loaded from ODOO_DB env variable.",
            }
        elif not skip_connect:
            detector = DatabaseDetector(
                self.url, self.username, self.api_key,
                password=os.environ.get("ODOO_PASSWORD", "").strip() or None,
            )
            info = detector.detect()
            self._db_detection_info = info
            if info["success"]:
                self.db = info["database"]
            else:
                logger.warning("DB auto-detection failed — will try session-based auth.")
                self.db = None
        else:
            self.db = None
            self._db_detection_info = {
                "success": False,
                "database": None,
                "strategy_used": "skip_connect",
                "candidates_tried": [],
                "message": "skip_connect=True; no auth attempted.",
            }

        if not skip_connect:
            self._fetch_version_info()
            self._authenticate()

    # ── Layer 4: integrity check ────────────────────────────────────────────

    def __check_integrity(self) -> None:
        if not self.__class__._READ_ONLY:
            raise RuntimeError(
                "FATAL: Class-level _READ_ONLY flag was tampered with. Aborting."
            )
        if not self.__read_only:
            raise RuntimeError(
                "FATAL: Instance-level read-only flag was tampered with. Aborting."
            )

    # ── Safety guard: Layers 1 & 2 ─────────────────────────────────────────

    def _check_method(self, model: str, method: str) -> None:
        """Apply Layer 2 (allowlist) then Layer 1 (blocklist)."""
        # Layer 2 — allowlist (stricter: anything NOT on this list is blocked)
        if method not in ALLOWED_METHODS:
            reason = f"not in ALLOWED_METHODS allowlist"
            if self._audit:
                self._audit.log_blocked(model, method, reason)
            raise PermissionError(
                f"BLOCKED (Layer 2): method '{method}' on '{model}' is not in the "
                f"allowed-methods list {sorted(ALLOWED_METHODS)}. "
                f"This client is READ-ONLY."
            )
        # Layer 1 — blocklist (defence-in-depth: should never be reached after Layer 2)
        if method in FORBIDDEN_METHODS or method.startswith(FORBIDDEN_PREFIXES):
            reason = "matches Layer 1 blocklist"
            if self._audit:
                self._audit.log_blocked(model, method, reason)
            raise PermissionError(
                f"BLOCKED (Layer 1): method '{method}' on '{model}' is explicitly "
                f"forbidden. This client is READ-ONLY."
            )

    # ── Init helpers ────────────────────────────────────────────────────────

    def _fetch_version_info(self) -> None:
        """Try POST first (Odoo 17+), then GET (Odoo 13–16)."""
        for http_method, extra in [
            ("post", {"json": {"jsonrpc": "2.0", "method": "call", "id": 1, "params": {}}}),
            ("get", {}),
        ]:
            try:
                resp = getattr(self._http, http_method)(
                    f"{self.url}/web/webclient/version_info",
                    timeout=10,
                    **extra,
                )
                if resp.status_code == 200 and "application/json" in resp.headers.get(
                    "Content-Type", ""
                ):
                    data = resp.json()
                    self.version_info = data.get("result", data)
                    return
            except PermissionError:
                raise
            except Exception:
                pass
        logger.warning("Could not fetch version_info from server")
        self.version_info = {}

    def _authenticate(self) -> None:
        if self.db:
            if self._try_json_rpc_auth(self.db):
                self.api_method = "json-rpc"
                return
            logger.debug("JSON-RPC with explicit DB failed, trying XML-RPC …")
            if self._try_xml_rpc_auth(self.db):
                self.api_method = "xml-rpc"
                return
            logger.warning(
                f"JSON-RPC and XML-RPC both failed with db='{self.db}'. "
                "Trying session-based auth (server resolves DB from hostname) …"
            )

        if self._try_session_form_auth():
            self.api_method = "json-rpc-session"
            return

        self._raise_auth_failure()

    def _try_json_rpc_auth(self, db: str) -> bool:
        try:
            resp = self._http.post(
                f"{self.url}/web/session/authenticate",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "id": 1,
                    "params": {"db": db, "login": self.username, "password": self.api_key},
                },
                timeout=15,
            )
            data = resp.json()
            result = data.get("result") or {}
            uid = result.get("uid")
            if isinstance(uid, int) and uid > 0:
                self.uid = uid
                self.db = result.get("db", db)
                self.session_id = result.get("session_id")
                self._http.cookies.update(resp.cookies)
                return True
            err = data.get("error", {})
            if err:
                msg = err.get("data", {}).get("message", str(err))[:120]
                logger.debug(f"JSON-RPC auth server error: {msg}")
            return False
        except PermissionError:
            raise
        except Exception as exc:
            logger.debug(f"JSON-RPC auth exception: {exc}")
            return False

    def _try_xml_rpc_auth(self, db: str) -> bool:
        try:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            uid = common.authenticate(db, self.username, self.api_key, {})
            if isinstance(uid, int) and uid > 0:
                self.uid = uid
                self._xml_models = xmlrpc.client.ServerProxy(
                    f"{self.url}/xmlrpc/2/object"
                )
                return True
            logger.debug(f"XML-RPC auth returned uid={uid!r}")
            return False
        except xmlrpc.client.Fault as f:
            last = f.faultString.strip().split("\n")[-1][:150]
            logger.debug(f"XML-RPC auth fault: {last}")
            return False
        except Exception as exc:
            logger.debug(f"XML-RPC auth exception: {exc}")
            return False

    def _try_session_form_auth(self) -> bool:
        """
        Authenticate via HTML form POST to /web/login.
        The server determines the database from the hostname — no DB name needed.
        Tries ODOO_PASSWORD first, then ODOO_API_KEY as fallback.
        After success: updates ODOO_DB and clears ODOO_PASSWORD in .env.
        """
        password = os.environ.get("ODOO_PASSWORD", "").strip()
        if not password:
            password = self.api_key
            logger.debug(
                "ODOO_PASSWORD not set — trying API key as form-login password (may fail)"
            )
        else:
            logger.debug("ODOO_PASSWORD found — using it for session form auth")

        try:
            # Step 1: GET login page for CSRF token + session cookie
            self._http.headers.pop("Content-Type", None)
            r_get = self._http.get(
                f"{self.url}/web/login", timeout=15, allow_redirects=True
            )
            csrf_m = re.search(r'csrf_token:\s*["\']([^"\']+)["\']', r_get.text)
            csrf_token = csrf_m.group(1) if csrf_m else ""
            if not csrf_token:
                logger.debug("Session form auth: no CSRF token in login page")
                self._http.headers["Content-Type"] = "application/json"
                return False

            # Step 2: POST the login form
            r_post = self._http.post(
                f"{self.url}/web/login",
                data={
                    "login": self.username,
                    "password": password,
                    "csrf_token": csrf_token,
                    "redirect": "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
                allow_redirects=True,
            )
            self._http.headers["Content-Type"] = "application/json"

            if "/web/login" in r_post.url:
                logger.debug(
                    "Session form auth: redirected back to login — credentials rejected. "
                    "Set ODOO_PASSWORD=<your Odoo login password> in .env."
                )
                return False

            # Step 3: Confirm authenticated session + discover DB name
            r_info = self._http.post(
                f"{self.url}/web/session/get_session_info",
                json={"jsonrpc": "2.0", "method": "call", "id": 2, "params": {}},
                timeout=15,
            )
            info = r_info.json().get("result") or {}
            uid = info.get("uid")
            if isinstance(uid, int) and uid > 0:
                self.uid = uid
                discovered_db = info.get("db") or self.db
                self.db = discovered_db
                logger.success(
                    f"Authenticated via session (uid={uid}, db={discovered_db})"
                )
                # Update .env: persist real DB name, wipe password
                self._update_env_after_session_auth(discovered_db)
                return True

            logger.debug(f"Session form auth: get_session_info uid={uid!r}")
            return False

        except PermissionError:
            raise
        except Exception as exc:
            self._http.headers["Content-Type"] = "application/json"
            logger.debug(f"Session form auth exception: {exc}")
            return False

    def _update_env_after_session_auth(self, db_name: str | None) -> None:
        """Persist the discovered DB name and clear ODOO_PASSWORD in .env."""
        env_path = Path(".env")
        if not env_path.exists():
            return
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_lines: list[str] = []
        db_updated = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("ODOO_PASSWORD=") and not stripped.startswith("#"):
                new_lines.append(f"# ODOO_PASSWORD=***CLEARED_{ts}*** (used once for DB detection)\n")
                logger.success("ODOO_PASSWORD cleared from .env")
            elif stripped.startswith("ODOO_DB=") and db_name and not stripped.startswith("#"):
                new_lines.append(f"ODOO_DB={db_name}\n")
                db_updated = True
            else:
                new_lines.append(line)
        if db_name and not db_updated:
            new_lines.append(f"\nODOO_DB={db_name}\n")
        env_path.write_text("".join(new_lines), encoding="utf-8")
        if db_name:
            logger.success(f"ODOO_DB updated to '{db_name}' in .env")
        logger.success("Future runs will use API key only (no password needed)")

    def _raise_auth_failure(self) -> None:
        lines = [
            "Authentication failed via all strategies.",
            "",
            "  Strategies tried:",
        ]
        if self.db:
            lines.append(f"    1. JSON-RPC /web/session/authenticate  (db='{self.db}')")
            lines.append(f"    2. XML-RPC /xmlrpc/2/common.authenticate  (db='{self.db}')")
        lines.append(
            "    3. Form-based session login via /web/login  (server determines DB from hostname)"
        )
        lines += [
            "",
            "  How to fix — pick ONE:",
            "",
            "    Option A (preferred) — Add your real Odoo login password:",
            "      ODOO_PASSWORD=<the password you type at kamahtech-palme.odoo.com>",
            "      in your .env file. The password is used ONE TIME to auto-detect",
            "      the database name, then cleared from .env automatically.",
            "",
            "    Option B — Provide the correct PostgreSQL database name:",
            "      Set ODOO_DB=<actual_name> in .env",
            "      (Check your Odoo.sh dashboard, or ask admin: psql -l)",
        ]
        raise RuntimeError("\n".join(lines))

    # ── execute_kw — ALL Odoo model calls go through here ──────────────────

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: dict | None = None,
    ) -> Any:
        # Layer 4: integrity check (every call)
        self.__check_integrity()
        # Layers 1 & 2: method safety check
        self._check_method(model, method)
        kwargs = kwargs or {}

        try:
            if self.api_method in ("json-rpc", "json-rpc-session"):
                result = self._execute_json_rpc(model, method, args, kwargs)
            else:
                result = self._execute_xml_rpc(model, method, args, kwargs)
            if self._audit:
                self._audit.log_call(model, method, success=True)
            return result
        except PermissionError:
            raise
        except Exception as exc:
            if self._audit:
                self._audit.log_call(model, method, success=False, error=str(exc))
            raise

    def _execute_json_rpc(self, model: str, method: str, args: list, kwargs: dict) -> Any:
        # Note: SafeHttpClient (Layer 5) will re-inspect this payload before sending
        resp = self._http.post(
            f"{self.url}/web/dataset/call_kw",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"model": model, "method": method, "args": args, "kwargs": kwargs},
            },
            timeout=30,
        )
        data = resp.json()
        if "error" in data:
            raise RuntimeError(
                f"Odoo error on {model}.{method}: "
                f"{data['error'].get('data', {}).get('message', data['error'])}"
            )
        return data["result"]

    def _execute_xml_rpc(self, model: str, method: str, args: list, kwargs: dict) -> Any:
        return self._xml_models.execute_kw(
            self.db, self.uid, self.api_key, model, method, args, kwargs
        )

    # ── Public read-only helper methods ────────────────────────────────────

    def search_read(
        self,
        model: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict]:
        kw: dict = {"limit": limit, "offset": offset}
        if fields is not None:
            kw["fields"] = fields
        if order is not None:
            kw["order"] = order
        return self.execute_kw(model, "search_read", [domain or []], kw)

    def read(self, model: str, ids: list[int], fields: list[str] | None = None) -> list[dict]:
        kw: dict = {}
        if fields is not None:
            kw["fields"] = fields
        return self.execute_kw(model, "read", [ids], kw)

    def search(
        self,
        model: str,
        domain: list | None = None,
        limit: int = 80,
        offset: int = 0,
    ) -> list[int]:
        return self.execute_kw(model, "search", [domain or []], {"limit": limit, "offset": offset})

    def search_count(self, model: str, domain: list | None = None) -> int:
        return self.execute_kw(model, "search_count", [domain or []])

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        kw: dict = {}
        if attributes is not None:
            kw["attributes"] = attributes
        return self.execute_kw(model, "fields_get", [], kw)

    def name_search(self, model: str, name: str = "", limit: int = 10) -> list:
        return self.execute_kw(model, "name_search", [], {"name": name, "limit": limit})
