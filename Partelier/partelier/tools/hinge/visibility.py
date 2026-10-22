"""Bounded ownership of body light-bulb changes for one hinge session.

This changes visibility only. It does not move, copy, delete or edit geometry.
The caller retains failed restoration records and can retry on Cancel/Stop.
"""

from dataclasses import dataclass
import threading


class VisibilityError(ValueError):
    """Visibility could not be applied/restored without losing prior state."""


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise VisibilityError("Change hinge visibility on Fusion's main thread.")


def _body_visibility(body):
    try:
        valid = (body is not None and body.isValid and body.isSolid
                 and not body.isTemporary and body.assemblyContext is None)
        visible = body.isLightBulbOn if valid else None
    except Exception as error:
        raise VisibilityError("A hinge visibility body is no longer readable.") from error
    if not valid or type(visible) is not bool:
        raise VisibilityError("Hinge visibility requires valid native persistent solid bodies.")
    return visible


def validated_bodies(bodies):
    """Validate the whole explicit collection before any visibility mutation."""
    _main_thread()
    unique = []
    for body in bodies:
        _body_visibility(body)
        if not any(body == existing for existing in unique):
            unique.append(body)
    return tuple(unique)


@dataclass
class _Record:
    body: object
    original: bool


class BodyVisibilityLease:
    """Hide explicit bodies until restore, or commit after successful creation."""

    def __init__(self):
        self._records = []

    @property
    def pending_count(self):
        return len(self._records)

    def hide(self, bodies):
        _main_thread()
        bodies = validated_bodies(bodies)
        additions = []
        try:
            for body in bodies:
                record = next((item for item in self._records if item.body == body), None)
                current = _body_visibility(body)
                if record is not None:
                    if current:
                        raise VisibilityError("A leased body's visibility changed outside the hinge preview.")
                    continue
                record = _Record(body, current)
                self._records.append(record)
                additions.append(record)
                if current:
                    body.isLightBulbOn = False
                if _body_visibility(body):
                    raise VisibilityError("Fusion did not hide a selected hinge body.")
        except Exception as error:
            failed = self._restore_records(additions)
            detail = " Some original visibility could not be restored; Cancel or Stop will retry." if failed else ""
            raise VisibilityError("Could not prepare the hinge view. " + str(error) + detail) from error
        return self

    def _restore_records(self, records):
        failed = []
        for record in reversed(records):
            try:
                current = _body_visibility(record.body)
                if current != record.original:
                    if current is not False:
                        raise VisibilityError("A body's visibility was changed outside the hinge session.")
                    record.body.isLightBulbOn = record.original
                if _body_visibility(record.body) != record.original:
                    raise VisibilityError("Fusion did not restore a body's original visibility.")
                self._records = [item for item in self._records if item is not record]
            except Exception as error:
                failed.append(error)
        return failed

    def restore(self):
        """Restore original flags; failed records remain owned for a later retry."""
        _main_thread()
        failed = self._restore_records(tuple(self._records))
        if failed:
            raise VisibilityError(
                f"Could not restore {len(failed)} body visibility setting(s). Retry Cancel or Stop. "
                + str(failed[0]))

    def commit(self):
        """Forget snapshots only after persistence succeeds; leave backups hidden."""
        _main_thread()
        self._records.clear()
