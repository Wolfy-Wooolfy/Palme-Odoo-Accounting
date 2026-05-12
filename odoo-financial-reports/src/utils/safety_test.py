"""Layer 6: Pre-flight self-test — verifies all guards are functional."""
from __future__ import annotations

from src.utils import logger


def run_safety_self_test(client) -> None:
    """
    Verify all read-only guards are active and blocking write operations.

    MUST be called and pass BEFORE any real Odoo API call is made.
    Aborts the process immediately (SystemExit) if any guard is broken.

    Tests are designed to exercise every blocking path:
      1. Blocklist match (create)
      2. Prefix match (action_)
      3. Allowlist miss (non-standard method)
      4. Blocklist match (write)
      5. Blocklist match (unlink)
    """
    logger.section("Pre-Flight Safety Self-Test (Layer 6)")
    logger.info("Running 5 write-block assertions before any real Odoo call …")

    tests: list[tuple[str, object]] = [
        (
            "create is blocked (Layer 1 — blocklist)",
            lambda: client.execute_kw("res.partner", "create", [{"name": "GUARD_TEST"}]),
        ),
        (
            "action_ prefix is blocked (Layer 1 — prefix blocklist)",
            lambda: client.execute_kw("account.move", "action_post", [[1]]),
        ),
        (
            "arbitrary method is blocked (Layer 2 — allowlist miss)",
            lambda: client.execute_kw("res.partner", "some_unregistered_method", []),
        ),
        (
            "write is blocked (Layer 1 — blocklist)",
            lambda: client.execute_kw("res.partner", "write", [[1], {"name": "X"}]),
        ),
        (
            "unlink is blocked (Layer 1 — blocklist)",
            lambda: client.execute_kw("res.partner", "unlink", [[1]]),
        ),
    ]

    for i, (description, fn) in enumerate(tests, 1):
        try:
            fn()
            # Reaching here means the guard did NOT block — fatal
            msg = (
                f"FATAL: Self-test #{i} ({description!r}) "
                f"did NOT raise PermissionError. "
                f"A write operation was not blocked. Aborting NOW."
            )
            logger.error(msg)
            raise SystemExit(msg)
        except PermissionError:
            logger.success(f"  Test {i}/5 PASSED — {description}")
        except SystemExit:
            raise
        except Exception as exc:
            # Unexpected error — guard did not activate properly
            msg = (
                f"FATAL: Self-test #{i} ({description!r}) raised an unexpected "
                f"exception instead of PermissionError: {exc!r}. Aborting."
            )
            logger.error(msg)
            raise SystemExit(msg) from exc

    logger.success("All 5 safety guards verified — proceeding with discovery")

    if hasattr(client, "_audit") and client._audit is not None:
        client._audit.mark_self_test_passed()
