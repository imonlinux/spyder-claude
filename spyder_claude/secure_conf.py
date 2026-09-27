# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Direct interop with the system keyring.

Spyder's ``CONF.set(..., secure=True)`` reacts to a missing keyring backend
by showing a modal dialog and then *continuing as if the write succeeded*.
That is safe for opaque settings but not for a value whose plaintext
original would be deleted right after — a failed secure write must raise,
not pop a dialog and carry on. These helpers call keyring directly so
callers can detect failure and decide what to do.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def keyring_backend_available() -> bool:
    """True if a usable keyring backend is configured.

    With no backend installed, keyring hands out
    ``keyring.backends.fail.Keyring`` (priority 0), whose every operation
    raises ``NoKeyringError`` — so a truthy priority is the availability
    signal. A missing keyring package counts as unavailable.
    """
    try:
        import keyring

        return bool(keyring.get_keyring().priority)
    except Exception:
        return False


def keyring_write(section: str, option: str, value: str) -> None:
    """Store a value in the system keyring.

    The keyring entry is keyed ``(service=section, username=option)``, the
    same convention Spyder's CONF uses for ``secure=True`` options, so values
    written here are read back by ``get_conf(..., secure=True)``.

    Raises on failure (including "no backend") instead of swallowing it.
    """
    import keyring

    keyring.set_password(section, option, value)
