from __future__ import annotations

import re
import xmlrpc.client
from urllib.parse import urlparse

import requests

from src.utils import logger


class DatabaseDetector:
    def __init__(
        self,
        url: str,
        username: str,
        api_key: str,
        password: str | None = None,
    ) -> None:
        # Strip path/hash/query — we only need scheme+host
        parsed = urlparse(url.strip())
        self.url = f"{parsed.scheme}://{parsed.netloc}"
        self.username = username
        self.api_key = api_key
        self.password = password  # actual login password (for Strategy 7)
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def detect(self) -> dict:
        candidates_tried: list[str] = []

        # Strategy 1 — /web/database/list (JSON-RPC POST)
        result = self._strategy_web_db_list(candidates_tried)
        if result:
            return result

        # Strategy 2 — /jsonrpc db.list
        result = self._strategy_jsonrpc_db_list(candidates_tried)
        if result:
            return result

        # Strategy 3 — XML-RPC /xmlrpc/2/db .list()
        result = self._strategy_xmlrpc_db_list(candidates_tried)
        if result:
            return result

        # Strategy 4 — hostname candidate generation
        # Strategy 5 — auth probe each candidate
        result = self._strategy_hostname_auth_probe(candidates_tried)
        if result:
            return result

        # Strategy 7 — form-based session login (uses password, server resolves DB)
        # Skipped here; handled in OdooReadOnlyClient._try_session_form_auth()
        # (requires password + cookie session management beyond this detector's scope)

        self._print_manual_instructions()
        return {
            "success": False,
            "database": None,
            "strategy_used": None,
            "candidates_tried": candidates_tried,
            "message": "Database could not be auto-detected. Manual intervention required.",
        }

    # ------------------------------------------------------------------ #
    # Strategy 1 — POST /web/database/list
    # ------------------------------------------------------------------ #

    def _strategy_web_db_list(self, candidates_tried: list) -> dict | None:
        logger.debug("Strategy 1: /web/database/list …")
        endpoint = f"{self.url}/web/database/list"
        try:
            resp = self._session.post(
                endpoint,
                json={"jsonrpc": "2.0", "method": "call", "params": {}},
                timeout=10,
                allow_redirects=False,
            )
            status = resp.status_code
            ct = resp.headers.get("Content-Type", "")
            logger.debug(f"  → status={status}, content-type={ct}")

            if status != 200 or "application/json" not in ct:
                logger.debug(
                    f"  Strategy 1: endpoint disabled or redirected "
                    f"(status={status}, content-type={ct}) — preview: {resp.text[:200]!r}"
                )
                return None

            data = resp.json()
            dbs = data.get("result")
            if not isinstance(dbs, list) or not dbs:
                logger.debug("  Strategy 1: result is not a non-empty list")
                return None

            candidates_tried.extend(dbs)
            return self._pick_from_list(dbs, "strategy_1_web_db_list", candidates_tried)

        except Exception as exc:
            logger.debug(f"  Strategy 1 error: {exc}")
            return None

    # ------------------------------------------------------------------ #
    # Strategy 2 — POST /jsonrpc db.list
    # ------------------------------------------------------------------ #

    def _strategy_jsonrpc_db_list(self, candidates_tried: list) -> dict | None:
        logger.debug("Strategy 2: /jsonrpc db.list …")
        endpoint = f"{self.url}/jsonrpc"
        try:
            resp = self._session.post(
                endpoint,
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {"service": "db", "method": "list", "args": []},
                },
                timeout=10,
                allow_redirects=False,
            )
            status = resp.status_code
            ct = resp.headers.get("Content-Type", "")
            logger.debug(f"  → status={status}, content-type={ct}")

            if status != 200 or "application/json" not in ct:
                logger.debug(
                    f"  Strategy 2: endpoint disabled or redirected "
                    f"(status={status}, content-type={ct}) — preview: {resp.text[:200]!r}"
                )
                return None

            data = resp.json()
            dbs = data.get("result")
            if not isinstance(dbs, list) or not dbs:
                logger.debug("  Strategy 2: result is not a non-empty list")
                return None

            new_dbs = [d for d in dbs if d not in candidates_tried]
            candidates_tried.extend(new_dbs)
            return self._pick_from_list(dbs, "strategy_2_jsonrpc_db_list", candidates_tried)

        except Exception as exc:
            logger.debug(f"  Strategy 2 error: {exc}")
            return None

    # ------------------------------------------------------------------ #
    # Strategy 3 — XML-RPC db.list
    # ------------------------------------------------------------------ #

    def _strategy_xmlrpc_db_list(self, candidates_tried: list) -> dict | None:
        logger.debug("Strategy 3: XML-RPC /xmlrpc/2/db .list() …")
        try:
            proxy = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/db", allow_none=True
            )
            dbs = proxy.list()
            if not isinstance(dbs, list) or not dbs:
                logger.debug("  Strategy 3: empty or invalid result")
                return None

            logger.debug(f"  Strategy 3: got {len(dbs)} databases")
            new_dbs = [d for d in dbs if d not in candidates_tried]
            candidates_tried.extend(new_dbs)
            return self._pick_from_list(dbs, "strategy_3_xmlrpc_db_list", candidates_tried)

        except Exception as exc:
            logger.debug(f"  Strategy 3 error: {exc}")
            return None

    # ------------------------------------------------------------------ #
    # Strategy 4+5 — hostname candidates + auth probe
    # ------------------------------------------------------------------ #

    def _strategy_hostname_auth_probe(self, candidates_tried: list) -> dict | None:
        logger.debug("Strategy 4: deriving candidates from hostname …")
        parsed = urlparse(self.url)
        hostname = parsed.hostname or ""

        subdomain = re.sub(r"\.odoo\.com$|\.odoo\.sh$", "", hostname)
        if "." in subdomain:
            subdomain = subdomain.split(".")[0]

        seen: set[str] = set()
        candidates: list[str] = []
        for name in [
            subdomain,
            f"{subdomain}_prod",
            f"{subdomain}_production",
            f"{subdomain}-main",
            hostname,
        ]:
            if name and name not in seen and name not in candidates_tried:
                seen.add(name)
                candidates.append(name)

        candidates_tried.extend(candidates)
        logger.debug(f"  Candidates: {candidates}")

        logger.debug("Strategy 5: auth-probing each candidate …")
        for candidate in candidates:
            uid = self._try_authenticate(candidate)
            if uid is not None:
                logger.success(
                    f"Database detected: {candidate} (via strategy_5_auth_probe, uid={uid})"
                )
                return {
                    "success": True,
                    "database": candidate,
                    "strategy_used": "strategy_5_auth_probe",
                    "candidates_tried": candidates_tried,
                    "message": f"Database '{candidate}' confirmed via auth probe (uid={uid}).",
                }
            else:
                logger.debug(f"  Probing '{candidate}' … failed")

        return None

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #

    def _pick_from_list(
        self, dbs: list[str], strategy: str, candidates_tried: list
    ) -> dict | None:
        if len(dbs) == 1:
            db = dbs[0]
            logger.success(f"Database detected: {db} (via {strategy})")
            return {
                "success": True,
                "database": db,
                "strategy_used": strategy,
                "candidates_tried": candidates_tried,
                "message": f"Single database '{db}' found via {strategy}.",
            }

        # Multiple — auth-probe each
        logger.debug(f"  Multiple DBs found ({len(dbs)}), auth-probing each …")
        for db in dbs:
            uid = self._try_authenticate(db)
            if uid is not None:
                logger.success(f"Database detected: {db} (via {strategy} + auth probe, uid={uid})")
                return {
                    "success": True,
                    "database": db,
                    "strategy_used": strategy,
                    "candidates_tried": candidates_tried,
                    "message": f"Database '{db}' confirmed via auth probe (from list of {len(dbs)}).",
                }
        return None

    def _try_authenticate(self, candidate_db: str) -> int | None:
        """Auth-probe a candidate DB name. Returns uid (int > 0) on success, None otherwise."""
        logger.debug(f"  Probing '{candidate_db}' via authentication …")
        try:
            resp = requests.post(
                f"{self.url}/web/session/authenticate",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "db": candidate_db,
                        "login": self.username,
                        "password": self.api_key,
                    },
                },
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.debug(f"    ✗ status={resp.status_code}")
                return None
            ct = resp.headers.get("Content-Type", "")
            if "application/json" not in ct:
                logger.debug(f"    ✗ non-JSON response (content-type={ct})")
                return None
            data = resp.json()
            result = data.get("result") or {}
            uid = result.get("uid")
            if isinstance(uid, int) and uid > 0:
                logger.debug(f"    ✓ uid={uid}")
                return uid
            # Log any Odoo-level error
            error = data.get("error", {})
            if error:
                logger.debug(f"    ✗ Odoo error: {error.get('data', {}).get('message', error)}")
            return None
        except Exception as exc:
            logger.debug(f"    ✗ exception: {exc}")
            return None

    def _print_manual_instructions(self) -> None:
        logger.error("Could not auto-detect the database name.")
        logger.info(f"  Try opening: {self.url}/web/database/selector")
        logger.info("  Or check the 'Database' field on the Odoo login screen")
        logger.info("  Or contact your Odoo administrator")
        logger.info("  Once you know the name, set ODOO_DB=<name> in your .env file")
