"""Entry points called by Autodesk Fusion, using its package-relative loader."""

from .partelier import addin


def run(context):
    """Start Partelier and open its HTML tool library."""
    try:
        addin.start()
    except Exception:
        addin.report_error("Partelier could not start")


def stop(context):
    """Unregister the command and release its event handlers."""
    try:
        addin.stop()
    except Exception:
        addin.report_error("Partelier could not stop cleanly")
