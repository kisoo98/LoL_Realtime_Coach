"""Toast/console notifier for feedback."""
from __future__ import annotations

from loguru import logger

try:
    from win10toast import ToastNotifier  # type: ignore
    _toaster = ToastNotifier()
except Exception:
    _toaster = None


def show_feedback(text: str) -> None:
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60 + "\n")
    logger.info("Feedback shown to user.")
    if _toaster is not None:
        try:
            _toaster.show_toast(
                "LoL Coach",
                text[:200],
                duration=8,
                threaded=True,
            )
        except Exception as e:
            logger.warning(f"Toast failed: {e}")
