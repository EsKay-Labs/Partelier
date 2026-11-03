"""Two existing solids updated by owned BaseFeature tools and native Combines.

The caller owns a Fusion command transaction and must abort it on failure. Full
final shapes are history tools: Join(keep) then Intersect(consume) preserves each
selected body's identity without end-of-history duplicates. Rebuild updates the
same two tool sources. Input geometry is inspected before the owned BaseFeature.
No tool settings, user-body deletion, hidden backups or geometry planners live
here. The conservative fingerprint is reused from the validated hinge adapter.
"""

from .. import refresh_context
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import threading
import uuid


PAIR_NAME = "pair"
OWNER_NAME = "pair_owner"
ROLES = ("A", "B")
COMBINE_ROLES = ("A_join", "A_intersect", "B_join", "B_intersect")
KEYS = frozenset({"version", "tool", "feature_id", "base_feature", "targets",
                  "results", "combines", "tool_roles", "tool_tokens"})


@dataclass(frozen=True)
class SolidPairRecord:
    anchor: object
    feature_id: str
    targets: tuple
    recipe: dict


def _api():
    import adsk.core
    import adsk.fusion
    return adsk.core, adsk.fusion


def _signature(body):
    from .hinge.fusion import _body_signature
    return _body_signature(body)


def _items(collection):
    return tuple(collection.item(index) for index in range(collection.count))


def _valid(entity):
    return entity is not None and getattr(entity, "isValid", False)


def _token(entity):
    token = entity.entityToken
    if not _valid_token(token):
        raise ValueError("Fusion did not provide a persistent solid reference.")
    return token


def _valid_token(token):
    return isinstance(token, str) and 0 < len(token) <= 16384


def _identity(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _resolve(design, token):
    entities = design.findEntityByToken(token)
    if entities is None or len(entities) != 1 or not _valid(entities[0]):
        raise ValueError("A saved solid or history reference is missing or split. Reopen Edit.")
    return entities[0]


def _body(body, root=None):
    if (not _valid(body) or not body.isSolid or body.lumps.count != 1
            or not math.isfinite(float(body.volume)) or float(body.volume) <= 0):
        raise ValueError("Each selected or generated part must remain one valid solid.")
    if root is not None and (body.parentComponent != root or body.assemblyContext is not None
                             or body.isTemporary):
        raise ValueError("Select native bodies in the root component.")
    return body


def _healthy(feature):
    _, fusion = _api()
    if feature.healthState != fusion.FeatureHealthStates.HealthyFeatureHealthState:
        detail = feature.errorOrWarningMessage
        raise ValueError("An owned native feature could not compute cleanly."
                         + (" " + detail if detail else ""))


@contextmanager
def _history(design, feature, before=True):
    if not _valid(feature) or feature.parentComponent != design.rootComponent:
        raise ValueError("The saved tool history is missing.")
    node = feature.timelineObject
    if node is None or node.index < 0:
        raise ValueError("The saved tool requires ungrouped native history features.")
    marker = design.timeline.markerPosition
    if not node.rollTo(before):
        raise ValueError("Fusion could not inspect the source history.")
    try:
        yield
    finally:
        design.timeline.markerPosition = marker
        if design.timeline.markerPosition != marker:
            raise ValueError("Fusion could not restore the history marker. Restore it before continuing.")


class SolidPairStore:
    """Persistence scoped to one attribute namespace and one product tool ID."""

    def __init__(self, attribute_group, tool_id):
        if (not isinstance(attribute_group, str) or not attribute_group
                or not isinstance(tool_id, str) or not tool_id):
            raise ValueError("A solid-pair namespace and tool ID are required.")
        self.attribute_group = attribute_group
        self.tool_id = tool_id

    def _require_design(self, design):
        if threading.current_thread() is not threading.main_thread():
            raise ValueError("Run the tool on Fusion's main thread.")
        _, fusion = _api()
        if not _valid(design) or design.designType != fusion.DesignTypes.ParametricDesignType:
            raise ValueError("Use a parametric Design document with history enabled.")
        if design.timeline.markerPosition != refresh_context.end(design):
            raise ValueError("Move the history marker to the end before using this tool.")

    def _attribute(self, entity, name, value):
        if entity.attributes.add(self.attribute_group, name, value) is None:
            raise ValueError("Fusion could not save the tool ownership record.")

    def _stamp(self, entity, feature_id, role=None):
        value = feature_id if role is None else json.dumps(
            {"feature_id": feature_id, "role": role}, separators=(",", ":"))
        self._attribute(entity, OWNER_NAME, value)

    def _owned(self, entity, feature_id, role=None):
        tag = entity.attributes.itemByName(self.attribute_group, OWNER_NAME)
        if tag is None:
            return False
        if role is None:
            return tag.value == feature_id
        try:
            return json.loads(tag.value) == {"feature_id": feature_id, "role": role}
        except (TypeError, ValueError):
            return False

    def _parse(self, raw):
        if not isinstance(raw, str) or len(raw) > 131072:
            raise ValueError("The saved solid-pair record is missing or too large.")
        try:
            recipe = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("The saved solid-pair record is damaged.") from error
        if (not isinstance(recipe, dict) or set(recipe) != KEYS
                or type(recipe["version"]) is not int or recipe["version"] != 1
                or recipe["tool"] != self.tool_id or not _identity(recipe["feature_id"])
                or not _valid_token(recipe["base_feature"])):
            raise ValueError("The saved solid-pair record has an unsupported structure.")
        for key, roles in (("targets", ROLES), ("tool_tokens", ROLES),
                           ("combines", COMBINE_ROLES)):
            values = recipe[key]
            if (not isinstance(values, dict) or set(values) != set(roles)
                    or not all(_valid_token(value) for value in values.values())):
                raise ValueError("The saved solid-pair references are damaged.")
        references = [recipe["base_feature"]] + [value for key in
            ("targets", "tool_tokens", "combines") for value in recipe[key].values()]
        if len(set(references)) != len(references):
            raise ValueError("The saved solid-pair references are not unique.")
        if (not isinstance(recipe["tool_roles"], list) or len(recipe["tool_roles"]) != 2
                or any(not isinstance(role, str) for role in recipe["tool_roles"])
                or set(recipe["tool_roles"]) != set(ROLES)):
            raise ValueError("The saved solid-pair tool roles are damaged.")
        results = recipe["results"]
        if not isinstance(results, dict) or set(results) != set(ROLES):
            raise ValueError("The saved solid-pair fingerprints are damaged.")
        for value in results.values():
            if (not isinstance(value, str) or len(value) != 64
                    or any(character not in "0123456789abcdef" for character in value)):
                raise ValueError("The saved solid-pair fingerprints are damaged.")
        return recipe

    def _targets(self, design, recipe):
        bodies = tuple(_body(_resolve(design, recipe["targets"][role]), design.rootComponent)
                       for role in ROLES)
        if bodies[0] == bodies[1]:
            raise ValueError("The two saved targets now identify the same body.")
        return bodies

    def _feature_set(self, design, recipe):
        _, fusion = _api()
        base = _resolve(design, recipe["base_feature"])
        if fusion.BaseFeature.cast(base) is None or not self._owned(base, recipe["feature_id"]):
            raise ValueError("The tool no longer owns its saved BaseFeature.")
        matches = [candidate for candidate in _items(design.rootComponent.features.baseFeatures)
                   if self._owned(candidate, recipe["feature_id"])]
        if matches != [base]:
            raise ValueError("The tool has ambiguous ownership history.")
        features = {}
        indices = []
        for role, feature in [(None, base)] + [(role, _resolve(design, recipe["combines"][role]))
                                              for role in COMBINE_ROLES]:
            if not _valid(feature) or feature.parentComponent != design.rootComponent:
                raise ValueError("The owned native history was moved or removed.")
            if role is not None:
                if (fusion.CombineFeature.cast(feature) is None
                        or not self._owned(feature, recipe["feature_id"], role)):
                    raise ValueError("The tool no longer owns its native Combine features.")
                features[role] = feature
            node = feature.timelineObject
            if node is None or node.index < 0:
                raise ValueError("The tool requires ungrouped native history features.")
            indices.append(node.index)
            _healthy(feature)
        if indices != list(range(indices[0], indices[0] + 5)):
            raise ValueError("Features were inserted inside the tool history. Preserve them before rebuilding.")
        for role, feature in features.items():
            with _history(design, feature):
                owner, action = role.split("_")
                expected = (fusion.FeatureOperations.JoinFeatureOperation if action == "join"
                            else fusion.FeatureOperations.IntersectFeatureOperation)
                target = _resolve(design, recipe["targets"][owner])
                tool = _resolve(design, recipe["tool_tokens"][owner])
                if (feature.targetBody != target or _items(feature.toolBodies) != (tool,)
                        or feature.operation != expected or feature.isKeepToolBodies != (action == "join")
                        or feature.isNewComponent):
                    raise ValueError("A native Combine definition was changed outside Partelier.")
        return base, features

    def _read_anchor(self, design, anchor, selected_body=None):
        tag = anchor.attributes.itemByName(self.attribute_group, PAIR_NAME)
        if tag is None:
            raise ValueError("Select a supported Partelier result to load its dimensions.")
        recipe = self._parse(tag.value)
        targets = self._targets(design, recipe)
        if selected_body is not None and selected_body not in targets:
            raise ValueError("The selected body does not belong to this tool result.")
        for role, body in zip(ROLES, targets):
            if (not self._owned(body, recipe["feature_id"], role)
                    or (_signature(body) != recipe["results"][role] and not refresh_context.authorized(design,anchor))):
                raise ValueError("The result bodies were edited after creation. Preserve those edits before rebuilding.")
        base, _ = self._feature_set(design, recipe)
        if base != anchor:
            raise ValueError("The saved record identifies another tool feature.")
        with _history(design, base):
            self._targets(design, recipe)
        return SolidPairRecord(base, recipe["feature_id"], targets, recipe)

    def read(self, design, selected):
        """Read one exact owned result; root selection requires a unique result."""
        self._require_design(design)
        _, fusion = _api()
        if selected is None or not _valid(selected):
            raise ValueError("Select a supported Partelier result to load its dimensions.")
        base = fusion.BaseFeature.cast(selected)
        body = fusion.BRepBody.cast(selected)
        if body is None:
            for kind in (fusion.BRepFace, fusion.BRepEdge):
                picked = kind.cast(selected)
                if picked is not None:
                    body = picked.body
                    break
        if base is None and body is None and selected != design.rootComponent:
            raise ValueError("Select a supported Partelier result to load its dimensions.")
        if base is None:
            candidates = []
            for candidate in _items(design.rootComponent.features.baseFeatures):
                tag = candidate.attributes.itemByName(self.attribute_group, PAIR_NAME)
                if tag is None:
                    continue
                recipe = self._parse(tag.value)
                if body is None or any(self._owned(body, recipe["feature_id"], role) for role in ROLES):
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise ValueError("Select one supported Partelier result; the current selection is missing or ambiguous.")
            base = candidates[0]
        return self._read_anchor(design, base, body)

    def _fresh(self, design, record):
        self._require_design(design)
        if not isinstance(record, SolidPairRecord):
            raise ValueError("Reopen Edit to load the saved solid pair.")
        current = self._read_anchor(design, record.anchor)
        if (current.feature_id != record.feature_id or current.recipe != record.recipe
                or current.targets != record.targets):
            raise ValueError("The saved result changed. Reopen Edit before rebuilding.")
        return current

    @contextmanager
    def input_scope(self, design, record):
        """Yield original targets BEFORE this tool, always restoring the marker."""
        current = self._fresh(design, record)
        with _history(design, current.anchor):
            yield self._targets(design, current.recipe)

    def _combine(self, design, target, tool, role, feature_id, created):
        core, fusion = _api()
        tools = core.ObjectCollection.create()
        if tools.add(tool) is False:
            raise ValueError("Fusion could not collect a boolean tool.")
        collection = design.rootComponent.features.combineFeatures
        spec = collection.createInput(target, tools)
        if spec is None:
            raise ValueError("Fusion could not define the in-place Combine.")
        spec.operation = (fusion.FeatureOperations.JoinFeatureOperation if role.endswith("_join")
                          else fusion.FeatureOperations.IntersectFeatureOperation)
        spec.isKeepToolBodies = role.endswith("_join")
        spec.isNewComponent = False
        feature = collection.add(spec)
        if not _valid(feature):
            raise ValueError("Fusion could not integrate the detail into its existing body.")
        created.append(feature)
        _healthy(feature)
        feature.name = "Partelier " + self.tool_id + " " + role.replace("_", " ")
        self._stamp(feature, feature_id, role)
        return feature

    def _record(self, design, base, feature_id, targets, tool_roles, tool_tokens, combines):
        recipe = {"version": 1, "tool": self.tool_id, "feature_id": feature_id,
                  "base_feature": _token(base),
                  "targets": {role: _token(body) for role, body in zip(ROLES, targets)},
                  "results": {role: _signature(body) for role, body in zip(ROLES, targets)},
                  "tool_roles": list(tool_roles), "tool_tokens": tool_tokens,
                  "combines": {role: _token(combines[role]) for role in COMBINE_ROLES}}
        self._parse(json.dumps(recipe))
        for role, body in zip(ROLES, targets):
            self._stamp(body, feature_id, role)
        self._stamp(base, feature_id)
        self._attribute(base, PAIR_NAME, json.dumps(recipe, separators=(",", ":")))

    def _pair(self, values, root=None):
        if not isinstance(values, (tuple, list)) or len(values) != 2:
            raise ValueError("This tool requires exactly two solid bodies.")
        pair = tuple(_body(body, root) for body in values)
        if pair[0] == pair[1]:
            raise ValueError("Select two different solid bodies.")
        return pair

    def _shape(self, actual, desired):
        _body(actual)
        if abs(float(actual.volume) - float(desired.volume)) > max(1e-8, abs(float(desired.volume)) * 1e-7):
            raise ValueError("The integrated solid volume does not match its preview.")
        for one, two in ((actual.boundingBox.minPoint, desired.boundingBox.minPoint),
                         (actual.boundingBox.maxPoint, desired.boundingBox.maxPoint)):
            if any(abs(float(getattr(one, axis)) - float(getattr(two, axis))) > 1e-6 for axis in "xyz"):
                raise ValueError("The integrated solid bounds do not match its preview.")

    def create(self, design, targets, finals, feature_id=None):
        """Create native history, modifying the SAME two selected solid bodies."""
        self._require_design(design)
        root = design.rootComponent
        targets = self._pair(targets, root)
        finals = self._pair(finals)
        if any(final in targets for final in finals):
            raise ValueError("Provide detached final shapes, preserving the selected sources.")
        feature_id = str(uuid.uuid4()) if feature_id is None else feature_id
        if not _identity(feature_id):
            raise ValueError("The tool ownership identity must be a canonical UUID.")
        if any(body.attributes.itemByName(self.attribute_group, OWNER_NAME) is not None for body in targets):
            raise ValueError("This body already belongs to this tool. Use Edit/Rebuild.")
        if any(self._owned(base, feature_id) for base in _items(root.features.baseFeatures)):
            raise ValueError("The tool ownership identity already exists.")
        tokens = tuple(_token(body) for body in targets)
        names = tuple(body.name for body in targets)
        visibility = tuple(body.isLightBulbOn for body in targets)
        before_count = root.bRepBodies.count
        base = None
        editing = False
        combines = {}
        created = []
        try:
            base = root.features.baseFeatures.add()
            if base is None or not base.startEdit():
                raise ValueError("Fusion could not start the tool BaseFeature.")
            editing = True
            base.name = "Partelier " + self.tool_id + " " + feature_id[:8]
            added = [(role, _body(root.bRepBodies.add(body, base))) for role, body in zip(ROLES, finals)]
            for role, body in added:
                body.name = "Partelier " + self.tool_id + " tool " + role
            order = self._map_tools(_items(base.bodies), added)
            if not base.finishEdit():
                raise ValueError("Fusion could not finish the tool BaseFeature.")
            editing = False
            tool_results = _items(base.bodies)
            if len(tool_results) != 2:
                raise ValueError("Fusion returned an unexpected native tool count.")
            tool_tokens = {role: _token(body) for role, body in zip(order, tool_results)}
            for index, owner in enumerate(ROLES):
                for suffix in ("join", "intersect"):
                    role = owner + "_" + suffix
                    combines[role] = self._combine(design, _resolve(design, tokens[index]),
                                                   _resolve(design, tool_tokens[owner]), role, feature_id, created)
            self._check_outputs(design, targets, finals, tokens, names, visibility, before_count)
            self._record(design, base, feature_id, targets, order, tool_tokens, combines)
            return base
        except Exception:
            if editing and _valid(base):
                base.finishEdit()
            # Caller transaction rolls back geometry/attributes; cleanup only owned history.
            for feature in reversed(created):
                if _valid(feature):
                    feature.deleteMe()
            if _valid(base):
                base.deleteMe()
            raise

    def _map_tools(self, bodies, named):
        order = []
        for body in bodies:
            matches = [role for role, source in named if body == source]
            if len(matches) != 1 or matches[0] in order:
                raise ValueError("Fusion could not map the editable tool roles.")
            order.append(matches[0])
        if len(order) != 2 or set(order) != set(ROLES):
            raise ValueError("Fusion returned an unexpected editable tool count.")
        return tuple(order)

    def _check_outputs(self, design, targets, finals, tokens, names, visibility, count):
        if design.rootComponent.bRepBodies.count != count:
            raise ValueError("The operation left unconsumed tools or duplicate bodies.")
        for index, target in enumerate(targets):
            current = _resolve(design, tokens[index])
            if current != target or current.name != names[index]:
                raise ValueError("Fusion replaced or renamed a selected body.")
            self._shape(current, finals[index])
            current.isLightBulbOn = visibility[index]

    def update(self, design, record, finals):
        """Rebuild the SAME two tool sources and preserve all native references."""
        current = self._fresh(design, record)
        finals = self._pair(finals)
        if any(final in current.targets for final in finals):
            raise ValueError("Provide detached final shapes, preserving the selected sources.")
        base, combines = self._feature_set(design, current.recipe)
        targets = current.targets
        tokens = tuple(_token(body) for body in targets)
        names = tuple(body.name for body in targets)
        visibility = tuple(body.isLightBulbOn for body in targets)
        count = design.rootComponent.bRepBodies.count
        editing = False
        with _history(design, base, before=False):
            try:
                before = _items(base.bodies)
                order = current.recipe["tool_roles"]
                if len(before) != 2 or any(body != _resolve(design, current.recipe["tool_tokens"][role])
                                           for role, body in zip(order, before)):
                    raise ValueError("The native tool role mapping changed outside Partelier.")
                if not base.startEdit():
                    raise ValueError("Fusion could not edit the tool BaseFeature.")
                editing = True
                sources = _items(base.bodies)
                if len(sources) != 2:
                    raise ValueError("Fusion changed the editable tool count.")
                desired = dict(zip(ROLES, finals))
                for role, source in zip(order, sources):
                    if not base.updateBody(source, desired[role]):
                        raise ValueError("Fusion could not update native tool " + role + ".")
                if not base.finishEdit():
                    raise ValueError("Fusion could not finish the rebuilt native tools.")
                editing = False
                results = _items(base.bodies)
                if len(results) != 2:
                    raise ValueError("Fusion returned an unexpected rebuilt tool count.")
                tool_tokens = {role: _token(body) for role, body in zip(order, results)}
            finally:
                if editing and _valid(base):
                    base.finishEdit()
        for feature in combines.values():
            _healthy(feature)
        self._check_outputs(design, targets, finals, tokens, names, visibility, count)
        self._record(design, base, current.feature_id, targets, order, tool_tokens, combines)
        return base
