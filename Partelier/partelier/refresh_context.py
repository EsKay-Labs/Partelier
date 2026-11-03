"""Scoped authority for rebuilding an exactly owned historical operation."""
from contextlib import contextmanager

_current = None

def authorized(design, anchor):
    return _current is not None and _current[0] == design and _current[1] == anchor

def end(design):
    return _current[2] if _current is not None and _current[0] == design else design.timeline.count

@contextmanager
def scope(design, anchor, marker):
    global _current
    if _current is not None:
        raise ValueError('A feature update is already running.')
    previous = design.timeline.markerPosition
    _current = (design, anchor, marker)
    try:
        design.timeline.markerPosition = marker
        yield
    finally:
        _current = None
        design.timeline.markerPosition = previous
