"""PyInstaller entry point for the Secure Messaging helper.

Keep this wrapper intentionally trivial: the public CLI/stdio contract remains
owned by ``secure_messaging.cli`` and packaging does not get a second behavior
surface.
"""

from secure_messaging.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
