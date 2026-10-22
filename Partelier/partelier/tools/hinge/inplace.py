"""Native attached output on the selected bodies, without backup/copy results.

The owned BaseFeature holds full transient final shapes as boolean TOOLS and
optional pins. Native Join(keep tools) followed by Intersect(consume tools)
changes each existing target into exactly its validated final shape:
(S union F) intersect F = F. Only pins increase the end-of-history body count.
The tools remain editable in history, not as hidden copies in the body browser.

Rebuild updates the SAME tool source bodies using BaseFeature.updateBody and
leaves the native Combine references and target body identities in place. Input
faces are resolved and prepared before the owned BaseFeature; native finishing
runs on detached results only after the history marker has been restored.

All writes MUST run in a caller-owned Fusion command transaction. On failure the
caller must fail/abort that transaction, including source body attribute edits
and any pin additions/removals. This is the same contract as native_finish.py.
Full final tools are snapshots: upstream source edits are incorporated by an
explicit Rebuild, not by automatic add-in recomputation.
"""

from contextlib import contextmanager
from dataclasses import replace
import json
import math
import time
import uuid


RECIPE_VERSION = 9
PERSISTENCE = "in_place"
COMBINE_ROLES = ("A_join", "A_intersect", "B_join", "B_intersect")
RECIPE_KEYS = frozenset({"version", "tool", "feature_id", "settings", "sources",
                         "results", "base_feature", "persistence", "combines",
                         "tool_roles", "tool_tokens"})
SOURCE_KEYS = frozenset({"face_a", "face_b", "axis_edge", "body_a", "body_b"})


def _adapter():
    from . import fusion
    return fusion


def _fail(message):
    return _adapter().HingeGeometryError(message)


def is_recipe(recipe):
    return (isinstance(recipe, dict) and type(recipe.get("version")) is int
            and recipe["version"] == RECIPE_VERSION)


def _valid_token(token):
    return isinstance(token, str) and 0 < len(token) <= 16384


def read_recipe(raw):
    """Strict independent v9 schema; copied v1-v8 never enter this contract."""
    adapter = _adapter()
    if not isinstance(raw, str) or len(raw) > 131072:
        raise _fail("The attached hinge recipe is missing or too large.")
    try:
        recipe = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise _fail("The attached hinge recipe is damaged.") from error
    if (not is_recipe(recipe) or set(recipe) != RECIPE_KEYS
            or recipe["persistence"] != PERSISTENCE or recipe["tool"] != adapter.TOOL_ID):
        raise _fail("The attached hinge recipe has an unsupported structure.")
    try:
        if str(uuid.UUID(recipe["feature_id"])) != recipe["feature_id"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as error:
        raise _fail("The attached hinge ownership identity is invalid.") from error
    try:
        settings = adapter.HingeSettings.from_dict(recipe["settings"])
    except (ValueError, TypeError) as error:
        raise _fail("The attached hinge settings are damaged: " + str(error)) from error
    if settings.output_mode != "attached":
        raise _fail("An in-place hinge recipe must use attached output.")
    roles = adapter._result_roles(settings)
    if (not isinstance(recipe["sources"], dict) or set(recipe["sources"]) != SOURCE_KEYS
            or not all(_valid_token(value) for value in recipe["sources"].values())
            or not _valid_token(recipe["base_feature"])):
        raise _fail("The attached hinge source references are damaged.")
    if (not isinstance(recipe["combines"], dict)
            or set(recipe["combines"]) != set(COMBINE_ROLES)
            or not all(_valid_token(value) for value in recipe["combines"].values())):
        raise _fail("The attached hinge native feature references are damaged.")
    if (not isinstance(recipe["tool_roles"], list)
            or len(recipe["tool_roles"]) != len(roles)
            or any(not isinstance(role, str) for role in recipe["tool_roles"])
            or set(recipe["tool_roles"]) != roles):
        raise _fail("The attached hinge tool ownership is damaged.")
    if (not isinstance(recipe["tool_tokens"], dict) or set(recipe["tool_tokens"]) != roles
            or not all(_valid_token(value) for value in recipe["tool_tokens"].values())):
        raise _fail("The attached hinge tool references are damaged.")
    if not isinstance(recipe["results"], dict) or set(recipe["results"]) != roles:
        raise _fail("The attached hinge result ownership is damaged.")
    for value in recipe["results"].values():
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise _fail("The attached hinge result fingerprint is damaged.")
    return recipe, settings


@contextmanager
def historical_scope(design, feature, *, before=True):
    """Restore the caller's exact history marker even if source work fails."""
    adapter = _adapter()
    adapter._require_main_thread()
    if not adapter._valid(feature) or feature.parentComponent != design.rootComponent:
        raise _fail("The attached hinge history feature is missing.")
    timeline = feature.timelineObject
    if timeline is None or timeline.index < 0:
        raise _fail("The attached hinge history feature is unavailable.")
    marker = design.timeline.markerPosition
    if not timeline.rollTo(before):
        raise _fail("Fusion could not inspect the attached hinge source history.")
    try:
        yield
    finally:
        design.timeline.markerPosition = marker
        if design.timeline.markerPosition != marker:
            raise _fail("Fusion could not restore the history marker. Restore it before continuing.")


def _sources(design, recipe):
    adapter = _adapter()
    _, fusion = adapter._api()
    sources = {name: adapter._resolve_one(design, token, "Hinge source " + name)
               for name, token in recipe["sources"].items()}
    face_a, face_b = fusion.BRepFace.cast(sources["face_a"]), fusion.BRepFace.cast(sources["face_b"])
    edge = fusion.BRepEdge.cast(sources["axis_edge"])
    if (face_a is None or face_b is None or edge is None
            or face_a.body != sources["body_a"] or face_b.body != sources["body_b"]):
        raise _fail("The attached hinge source references no longer match their original bodies.")
    return face_a, face_b, edge


def _source_bodies(design, recipe):
    adapter = _adapter()
    return tuple(adapter._resolve_one(design, recipe["sources"]["body_" + role.lower()],
                                      "The attached hinge target " + role) for role in ("A", "B"))


def result_bodies(design, recipe):
    """Only the original final targets and actual pins; never history tools."""
    adapter = _adapter()
    result = dict(zip(("A", "B"), _source_bodies(design, recipe)))
    for role in recipe["tool_roles"]:
        if role not in result:
            result[role] = adapter._resolve_one(design, recipe["tool_tokens"][role], "Hinge " + role)
    return result


def _owned(entity, feature_id, role=None):
    adapter = _adapter()
    value = entity.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.OWNER_NAME)
    expected = feature_id if role is None else {"feature_id": feature_id, "role": role}
    if value is None:
        return False
    if role is None:
        return value.value == expected
    try:
        return json.loads(value.value) == expected
    except (TypeError, ValueError):
        return False


def _stamp(entity, feature_id, role=None):
    adapter = _adapter()
    value = feature_id if role is None else json.dumps({"feature_id": feature_id, "role": role}, separators=(",", ":"))
    adapter._attribute(entity, adapter.OWNER_NAME, value)


def _healthy(feature):
    adapter = _adapter()
    _, fusion = adapter._api()
    states = getattr(fusion, "FeatureHealthStates", None)
    healthy = getattr(states, "HealthyFeatureHealthState", None)
    if healthy is not None and feature.healthState != healthy:
        detail = feature.errorOrWarningMessage
        raise _fail("An attached hinge native feature could not compute cleanly." + (" " + detail if detail else ""))


def _feature_set(design, recipe):
    """Validate exact owned feature sequence without inspecting unrelated bodies."""
    adapter = _adapter()
    _, fusion = adapter._api()
    base = adapter._resolve_one(design, recipe["base_feature"], "The attached hinge tool feature")
    if fusion.BaseFeature.cast(base) is None or not _owned(base, recipe["feature_id"]):
        raise _fail("The attached hinge no longer owns its tool feature.")
    features = {}
    indices = []
    for role, feature in [("tools", base)] + [
            (role, adapter._resolve_one(design, recipe["combines"][role], "Hinge " + role))
            for role in COMBINE_ROLES]:
        if not adapter._valid(feature) or feature.parentComponent != design.rootComponent:
            raise _fail("The attached hinge native features were moved or removed.")
        if role != "tools":
            if fusion.CombineFeature.cast(feature) is None or not _owned(feature, recipe["feature_id"], role):
                raise _fail("The attached hinge no longer owns its native combine features.")
            features[role] = feature
        timeline = feature.timelineObject
        if timeline is None or timeline.index < 0:
            raise _fail("The attached hinge requires ungrouped native history features.")
        indices.append(timeline.index)
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise _fail("Features were inserted inside the attached hinge history. Preserve them before rebuilding.")
    for role, feature in features.items():
        _healthy(feature)
        with historical_scope(design, feature):
            owner, action = role.split("_", 1)
            target = adapter._resolve_one(design, recipe["sources"]["body_" + owner.lower()], "Attached hinge target " + owner)
            tool = adapter._resolve_one(design, recipe["tool_tokens"][owner], "Attached hinge boolean tool " + owner)
            expected_operation = (fusion.FeatureOperations.JoinFeatureOperation if action == "join"
                                  else fusion.FeatureOperations.IntersectFeatureOperation)
            tools = adapter._items(feature.toolBodies)
            if (feature.targetBody != target or tools != (tool,)
                    or feature.operation != expected_operation
                    or feature.isKeepToolBodies != (action == "join")
                    or feature.isNewComponent):
                raise _fail("The attached hinge native combine definition was changed outside Partelier.")
    return base, features


def _read_target(design, base, selected_body=None):
    adapter = _adapter()
    if design.timeline.markerPosition != design.timeline.count:
        raise _fail("Move the history marker to the end before editing an attached hinge.")
    attribute = base.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME)
    if attribute is None:
        raise _fail("The attached hinge recipe is missing.")
    recipe, settings = read_recipe(attribute.value)
    owned_base, _ = _feature_set(design, recipe)
    if owned_base != base:
        raise _fail("The attached hinge recipe identifies another tool feature.")
    outputs = result_bodies(design, recipe)
    if selected_body is not None and selected_body not in outputs.values():
        raise _fail("The selected body is not an output of its recorded attached hinge.")
    for role, body in outputs.items():
        adapter._require_body(body, "An attached hinge output is no longer one solid.")
        if (body.parentComponent != design.rootComponent or body.assemblyContext is not None
                or not _owned(body, recipe["feature_id"], role)
                or adapter._body_signature(body) != recipe["results"][role]):
            raise _fail("The attached hinge bodies were edited after creation. Preserve those edits before rebuilding.")
    with historical_scope(design, base):
        face_a, face_b, edge = _sources(design, recipe)
        adapter._selection(design, face_a, face_b, edge, settings, historical=True)
    return adapter.EditTarget(design.rootComponent, None, settings, face_a, face_b, edge,
                              recipe["feature_id"], recipe, base)


def read_if_inplace(design, entity):
    """Return v9 EditTarget, or None so the adapter can inspect legacy output."""
    adapter = _adapter()
    _, fusion = adapter._api()
    base_type = getattr(fusion, "BaseFeature", None)
    body_type = getattr(fusion, "BRepBody", None)
    base = base_type.cast(entity) if base_type is not None else None
    body = body_type.cast(entity) if body_type is not None else None
    if base is None and body is not None:
        tag = body.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.OWNER_NAME)
        if tag is None:
            return None
        try:
            owner = json.loads(tag.value)
        except (TypeError, ValueError):
            return None
        if not isinstance(owner, dict) or set(owner) != {"feature_id", "role"}:
            return None
        candidates = []
        for candidate in adapter._items(design.rootComponent.features.baseFeatures):
            if _owned(candidate, owner["feature_id"]):
                attribute = candidate.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME)
                if attribute is not None:
                    try:
                        if is_recipe(json.loads(attribute.value)):
                            candidates.append(candidate)
                    except (TypeError, ValueError):
                        pass
        if len(candidates) > 1:
            raise _fail("The selected attached hinge has conflicting ownership features.")
        base = candidates[0] if candidates else None
    if base is None:
        return None
    attribute = base.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME)
    if attribute is None:
        return None
    try:
        raw = json.loads(attribute.value)
    except (TypeError, ValueError):
        return None
    if not is_recipe(raw):
        return None
    return _read_target(design, base, body)


def prepare_edit(design, target, settings, *, edge_finisher=None):
    """Prepare from pre-hinge sources; finish detached solids after restoring end."""
    adapter = _adapter()
    if settings.output_mode != "attached":
        raise _fail("An attached hinge rebuild keeps the existing bodies attached. Create separate leaves as a new hinge.")
    current = _read_target(design, target.anchor)
    if current.recipe != target.recipe:
        raise _fail("The attached hinge changed. Reopen Edit/Rebuild.")
    deferred = []

    def defer_finish(*args, **kwargs):
        deferred.append((args, kwargs))
        return args[4]

    with historical_scope(design, current.anchor):
        faces = _sources(design, current.recipe)
        prepared = adapter.prepare_hinge(design, *faces, settings,
                                         edge_finisher=defer_finish if edge_finisher is not None else None,
                                         _historical=True)
    prepared = replace(prepared, history_anchor=current.anchor,
                       source_tokens=dict(current.recipe["sources"]))
    if deferred:
        started = time.perf_counter()
        args, kwargs = deferred[0]
        finished = tuple(edge_finisher(*args, **kwargs))
        _, fusion = adapter._api()
        manager = fusion.TemporaryBRepManager.get()
        for index, (role, body) in enumerate(finished):
            for other_role, other in finished[index + 1:]:
                adapter._require_separate(manager, body, other,
                                          "The generated hinge bodies " + role + " and " + other_role)
        timings = dict(prepared.timings)
        timings["temporary_geometry_ms"] += (time.perf_counter() - started) * 1000
        prepared = replace(prepared, result_bodies=finished, preview_bodies=finished, timings=timings)
    return prepared


def assert_fresh(design, prepared):
    adapter = _adapter()
    anchor = prepared.history_anchor
    if design != prepared.design or not adapter._valid(anchor):
        raise _fail("The attached hinge source design or history changed. Reopen Edit/Rebuild.")
    with historical_scope(design, anchor):
        faces = _sources(design, {"sources": prepared.source_tokens})
        _, signature, _ = adapter._selection(design, *faces, prepared.settings, historical=True)
        if signature != prepared.source_signature:
            raise _fail("The pre-hinge source geometry changed. Refresh the hinge preview.")


def _combine(design, target, tool, role, feature_id):
    adapter = _adapter()
    core, fusion = adapter._api()
    tools = core.ObjectCollection.create()
    tools.add(tool)
    collection = design.rootComponent.features.combineFeatures
    operation = fusion.FeatureOperations.JoinFeatureOperation if role.endswith("_join") else fusion.FeatureOperations.IntersectFeatureOperation
    spec = collection.createInput(target, tools)
    if spec is None:
        raise _fail("Fusion could not define the in-place hinge combine.")
    spec.operation = operation
    spec.isKeepToolBodies = role.endswith("_join")
    spec.isNewComponent = False
    feature = collection.add(spec)
    if feature is None or not feature.isValid:
        raise _fail("Fusion could not join the hinge into its existing body.")
    _healthy(feature)
    feature.name = "Partelier hinge " + role.replace("_", " ")
    _stamp(feature, feature_id, role)
    return feature


def _validate_shape(actual, desired):
    adapter = _adapter()
    adapter._require_body(actual, "The in-place hinge did not remain one solid.")
    expected_volume, actual_volume = float(desired.volume), float(actual.volume)
    if (not math.isfinite(actual_volume)
            or abs(actual_volume - expected_volume) > max(1e-8, abs(expected_volume) * 1e-7)):
        raise _fail("Fusion's in-place hinge result does not match the validated shape.")
    for one, two in ((actual.boundingBox.minPoint, desired.boundingBox.minPoint),
                     (actual.boundingBox.maxPoint, desired.boundingBox.maxPoint)):
        if any(abs(a - b) > adapter.POSITION_TOLERANCE_CM for a, b in zip(adapter._xyz(one), adapter._xyz(two))):
            raise _fail("Fusion's in-place hinge result bounds do not match the preview.")


def _record(design, base, feature_id, settings, sources, roles, tools, combines):
    adapter = _adapter()
    recipe = {"version": RECIPE_VERSION, "tool": adapter.TOOL_ID, "feature_id": feature_id,
              "settings": settings.to_dict(), "sources": sources, "results": {},
              "base_feature": adapter._token(base), "persistence": PERSISTENCE,
              "combines": {role: adapter._token(feature) for role, feature in combines.items()},
              "tool_roles": list(roles), "tool_tokens": tools}
    outputs = result_bodies(design, recipe)
    for role, body in outputs.items():
        _stamp(body, feature_id, role)
        recipe["results"][role] = adapter._body_signature(body)
    _stamp(base, feature_id)
    adapter._attribute(base, adapter.RECIPE_NAME, json.dumps(recipe, separators=(",", ":")))
    return recipe


def create(design, prepared, feature_id=None):
    """Consume history tools into the SAME two selected native root bodies."""
    adapter = _adapter()
    adapter._require_main_thread()
    adapter._assert_fresh(design, prepared)
    if prepared.settings.output_mode != "attached":
        raise _fail("In-place persistence requires attached output.")
    feature_id = feature_id or str(uuid.uuid4())
    root = design.rootComponent
    originals = {"A": prepared.face_a.body, "B": prepared.face_b.body}
    for body in originals.values():
        if body.parentComponent != root or body.assemblyContext is not None:
            raise _fail("In-place hinges currently require native root-component bodies.")
        if any(body.attributes.itemByName(group, adapter.OWNER_NAME) is not None
               for group in (adapter.ATTRIBUTE_GROUP, adapter.LEGACY_ATTRIBUTE_GROUP)):
            raise _fail("This body already belongs to a Partelier hinge. Use Edit/Rebuild to change that hinge.")
    sources = {"face_a": adapter._token(prepared.face_a), "face_b": adapter._token(prepared.face_b),
               "axis_edge": adapter._token(prepared.axis_edge),
               "body_a": adapter._token(originals["A"]), "body_b": adapter._token(originals["B"])}
    desired = dict(prepared.result_bodies)
    roles = ["A", "B"] + [role for role, _ in prepared.result_bodies if role not in ("A", "B")]
    names = {role: body.name for role, body in originals.items()}
    visibility = {role: body.isLightBulbOn for role, body in originals.items()}
    count_before = root.bRepBodies.count
    base = None
    editing = False
    combines = {}
    try:
        base = root.features.baseFeatures.add()
        if base is None or not base.startEdit():
            raise _fail("Fusion could not start the attached hinge tool feature.")
        editing = True
        base.name = "Partelier attached hinge " + feature_id[:8]
        added = []
        for role in roles:
            body = root.bRepBodies.add(desired[role], base)
            adapter._require_body(body, "Fusion could not create an attached hinge boolean tool.")
            body.name = "Partelier hinge tool " + role if role in ("A", "B") else adapter._result_name(role)
            added.append((role, body))
        source_order = adapter._items(base.bodies)
        if len(source_order) != len(added):
            raise _fail("Fusion returned an unexpected editable attached hinge tool count.")
        ordered_roles = []
        for source in source_order:
            matches = [role for role, body in added if body == source]
            if len(matches) != 1 or matches[0] in ordered_roles:
                raise _fail("Fusion could not map the editable attached hinge tool roles.")
            ordered_roles.append(matches[0])
        roles = ordered_roles
        if not base.finishEdit():
            raise _fail("Fusion could not finish the attached hinge tool feature.")
        editing = False
        tool_results = adapter._items(base.bodies)
        if len(tool_results) != len(roles):
            raise _fail("Fusion returned an unexpected attached hinge tool count.")
        tool_tokens = {role: adapter._token(body) for role, body in zip(roles, tool_results)}
        for owner in ("A", "B"):
            for suffix in ("join", "intersect"):
                target = adapter._resolve_one(design, sources["body_" + owner.lower()], "The selected target " + owner)
                tool = adapter._resolve_one(design, tool_tokens[owner], "The attached hinge tool " + owner)
                role = owner + "_" + suffix
                combines[role] = _combine(design, target, tool, role, feature_id)
            target = adapter._resolve_one(design, sources["body_" + owner.lower()], "The selected target " + owner)
            if target != originals[owner] or target.name != names[owner]:
                raise _fail("Fusion replaced or renamed a selected body instead of modifying it.")
            _validate_shape(target, desired[owner])
            if target.isLightBulbOn != visibility[owner]:
                target.isLightBulbOn = visibility[owner]
        if root.bRepBodies.count != count_before + len(roles) - 2:
            raise _fail("The attached hinge left unconsumed tool or duplicate bodies.")
        _record(design, base, feature_id, prepared.settings, sources, roles, tool_tokens, combines)
        return base
    except Exception:
        if editing and base is not None and base.isValid:
            base.finishEdit()
        # Native command failure owns rollback of target geometry and metadata.
        # Removing these owned history nodes also makes direct diagnostic cleanup
        # bounded; never delete or replace either selected target body.
        for feature in reversed(tuple(combines.values())):
            if feature.isValid:
                feature.deleteMe()
        if base is not None and base.isValid:
            base.deleteMe()
        raise


def _editable_tools(design, base, recipe):
    """Map saved result positions to source positions before startEdit changes them."""
    adapter = _adapter()
    current = adapter._items(base.bodies)
    roles = recipe["tool_roles"]
    if len(current) != len(roles):
        raise _fail("The attached hinge tool bodies were changed outside Partelier.")
    for role, body in zip(roles, current):
        saved = adapter._resolve_one(design, recipe["tool_tokens"][role], "Attached hinge tool " + role)
        if saved != body:
            raise _fail("The attached hinge tool role mapping changed outside Partelier.")
    return tuple(roles)


def rebuild(design, target, prepared):
    """Update owned native tools; keep targets, BaseFeature and Combines intact."""
    adapter = _adapter()
    adapter._require_main_thread()
    current = _read_target(design, target.anchor)
    if current.feature_id != target.feature_id or current.recipe != target.recipe:
        raise _fail("The attached hinge changed. Reopen Edit/Rebuild.")
    if prepared.settings.output_mode != "attached" or prepared.history_anchor != current.anchor:
        raise _fail("Rebuild requires the saved attached hinge sources. Refresh its preview.")
    adapter._assert_fresh(design, prepared)
    base, combines = _feature_set(design, current.recipe)
    with historical_scope(design, base):
        expected_sources = _sources(design, current.recipe)
        prepared_sources = _sources(design, {"sources": prepared.source_tokens})
        if expected_sources != prepared_sources:
            raise _fail("Edit/Rebuild uses the saved source selections. Refresh the hinge preview.")
    old_roles = current.recipe["tool_roles"]
    desired = dict(prepared.result_bodies)
    new_roles = ["A", "B"] + [role for role, _ in prepared.result_bodies if role not in ("A", "B")]
    if set(old_roles) != set(new_roles) and design.timeline.count != combines["B_intersect"].timelineObject.index + 1:
        raise _fail("Changing the pin count requires this hinge to be last in the history, to preserve later pin references.")
    originals = result_bodies(design, current.recipe)
    names = {role: body.name for role, body in originals.items()}
    visibility = {role: body.isLightBulbOn for role, body in originals.items()}
    before_count = design.rootComponent.bRepBodies.count
    editing = False
    tool_tokens = None
    actual_roles = None
    with historical_scope(design, base, before=False):
        try:
            source_roles = _editable_tools(design, base, current.recipe)
            if not base.startEdit():
                raise _fail("Fusion could not edit the attached hinge tool bodies.")
            editing = True
            source_bodies = adapter._items(base.bodies)
            if len(source_bodies) != len(source_roles):
                raise _fail("Fusion changed the editable attached hinge tool count.")
            mapped = dict(zip(source_roles, source_bodies))
            for role in source_roles:
                if role in desired and not base.updateBody(mapped[role], desired[role]):
                    raise _fail("Fusion could not update the attached hinge tool " + role + ".")
            for role in new_roles:
                if role not in mapped:
                    body = design.rootComponent.bRepBodies.add(desired[role], base)
                    adapter._require_body(body, "Fusion could not add the requested hinge pin.")
                    body.name = adapter._result_name(role)
                    mapped[role] = body
            for role in source_roles:
                if role not in desired:
                    if not mapped[role].deleteMe():
                        raise _fail("Fusion could not remove the previous hinge pin.")
                    del mapped[role]
            remaining = adapter._items(base.bodies)
            actual_roles = []
            for body in remaining:
                matches = [role for role, source in mapped.items() if source == body]
                if len(matches) != 1:
                    raise _fail("Fusion could not map rebuilt attached hinge tool roles.")
                actual_roles.append(matches[0])
            if set(actual_roles) != set(new_roles) or len(actual_roles) != len(new_roles):
                raise _fail("Fusion returned inconsistent rebuilt attached hinge tool roles.")
            if not base.finishEdit():
                raise _fail("Fusion could not finish the rebuilt attached hinge tools.")
            editing = False
            tool_results = adapter._items(base.bodies)
            if len(tool_results) != len(actual_roles):
                raise _fail("Fusion returned an unexpected rebuilt hinge tool count.")
            tool_tokens = {role: adapter._token(body) for role, body in zip(actual_roles, tool_results)}
        finally:
            if editing and base.isValid:
                base.finishEdit()
    for feature in combines.values():
        _healthy(feature)
    expected_count = before_count + len(new_roles) - len(old_roles)
    if design.rootComponent.bRepBodies.count != expected_count:
        raise _fail("The rebuilt attached hinge left unconsumed tool or duplicate bodies.")
    sources = current.recipe["sources"]
    for role, body in zip(("A", "B"), _source_bodies(design, current.recipe)):
        if body != originals[role] or body.name != names[role]:
            raise _fail("Fusion replaced or renamed a selected body while rebuilding.")
        _validate_shape(body, desired[role])
        body.isLightBulbOn = visibility[role]
    for role in set(new_roles) & set(old_roles) - {"A", "B"}:
        body = adapter._resolve_one(design, tool_tokens[role], "Rebuilt hinge " + role)
        body.name = names[role]
        body.isLightBulbOn = visibility[role]
    _record(design, base, current.feature_id, prepared.settings, sources, actual_roles, tool_tokens, combines)
    return base
