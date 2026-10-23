"""Bounded Through-only batching, with untouched inputs on every refusal.

The caller MUST supply the original source and pristine single-solid cutters
already intersected with that original source. A successful disjoint union
proves that every cutter retains its independent material contribution. General
Engrave/Emboss tools do not satisfy this contract and must use the existing
sequential path. No persistent CAD entities or history features are created.
"""

from dataclasses import dataclass
import math
import time


MAX_BATCH_TOOLS = 400
MIN_CELL_VOLUME_CM3 = 1e-10


@dataclass(frozen=True)
class BatchDifference:
    body: object
    tool_count: int
    timings: dict


def _volume_tolerance(expected):
    return max(1e-9, abs(expected)*1e-9)


def _agrees(actual, expected):
    return math.isfinite(actual) and abs(actual-expected) <= _volume_tolerance(expected)


def _solid_volume(body, *, temporary, lumps):
    if (body is None or not body.isValid or not body.isSolid
            or (temporary and not body.isTemporary) or body.lumps.count != lumps):
        raise ValueError("Batch geometry requires valid closed solids with the expected lump count.")
    volume = float(body.volume)
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Batch geometry requires positive finite solid volumes.")
    return volume


def _clone(manager, original, volume, lumps):
    clone = manager.copy(original)
    if clone is original or clone == original:
        raise ValueError("The temporary manager did not return an independent copy.")
    copied = _solid_volume(clone, temporary=True, lumps=lumps)
    if not _agrees(copied, volume):
        raise ValueError("The temporary copy changed the solid volume.")
    return clone


def try_through_difference(manager, source, cutters, boolean_types, *, min_tools=8):
    """Return a validated batch result, or None for the original exact fallback.

    Prevalidated cutters must be temporary, single-lump, positive solids clipped
    to *source*. Inputs are never Boolean targets. All aggregation operates on
    copies, and final Difference uses a fresh source copy. A native failure,
    touching/overlapping tools, split result, or volume mismatch returns None;
    the caller then starts its unchanged sequential operation from the original
    source and the same pristine cutters. Invalid initial inputs raise ValueError.
    """
    if type(min_tools) is not int or not 2 <= min_tools <= MAX_BATCH_TOOLS:
        raise ValueError("The batch threshold must be between 2 and 400 tools.")
    try:
        tools = tuple(cutters)
    except TypeError as error:
        raise ValueError("Provide the bounded original Through cutters.") from error
    started = time.perf_counter()
    source_volume = _solid_volume(source, temporary=False, lumps=1)
    volumes = tuple(_solid_volume(tool, temporary=True, lumps=1) for tool in tools)
    if not min_tools <= len(tools) <= MAX_BATCH_TOOLS:
        return None
    removed_volume = math.fsum(volumes)
    expected_volume = source_volume-removed_volume
    tolerance = _volume_tolerance(source_volume)
    # Tiny contributions use the original per-cell delta guard. The aggregate
    # volume tolerance must never hide a noncontributing individual cell.
    if (expected_volume <= 0 or not math.isfinite(removed_volume)
            or any(value <= max(MIN_CELL_VOLUME_CM3, 2*tolerance) for value in volumes)):
        return None
    try:
        layer = [(_clone(manager, tool, volume, 1), 1, volume)
                 for tool,volume in zip(tools,volumes)]
        unions = 0
        while len(layer) > 1:
            following = []
            for index in range(0,len(layer),2):
                left, left_lumps, left_volume = layer[index]
                if index+1 == len(layer):
                    following.append(layer[index])
                    continue
                right, right_lumps, right_volume = layer[index+1]
                if manager.booleanOperation(left, right, boolean_types.UnionBooleanType) is False:
                    return None
                unions += 1
                lumps = left_lumps+right_lumps
                volume = _solid_volume(left, temporary=True, lumps=lumps)
                if not _agrees(volume, math.fsum((left_volume,right_volume))):
                    return None
                following.append((left,lumps,volume))
            layer = following
        aggregate, lump_count, volume = layer[0]
        if lump_count != len(tools) or not _agrees(volume,removed_volume):
            return None
        aggregated = time.perf_counter()
        result = _clone(manager, source, source_volume, 1)
        if manager.booleanOperation(result, aggregate, boolean_types.DifferenceBooleanType) is False:
            return None
        actual_volume = _solid_volume(result, temporary=True, lumps=1)
        if not _agrees(actual_volume,expected_volume):
            return None
        completed = time.perf_counter()
        return BatchDifference(result,len(tools),{
            "batch_aggregate_ms":(aggregated-started)*1000,
            "batch_apply_ms":(completed-aggregated)*1000,
            "batch_total_ms":(completed-started)*1000,
            "batch_union_calls":unions,
        })
    except Exception:
        # A Boolean may partially mutate its TARGET before refusing. Every such
        # target above is an owned copy, so discarding it leaves exact fallback
        # inputs intact; never resume from a partially failed batch body.
        return None
