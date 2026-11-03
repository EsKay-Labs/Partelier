"""One existing solid updated by owned tool geometry and native Combines.

This is the single-target form of the validated SolidPairStore technique.
The caller MUST own a Fusion command transaction and abort it on failure.
Join(keep) followed by Intersect(consume) preserves the original body identity;
Rebuild updates that same one tool source, without backup or dummy bodies.
Version 2 stores subtractive grilles as one owned cutter and one consuming Cut;
version 1 full-shape Join/Intersect records remain supported unchanged.
Tool-specific settings and selected-face recipes belong to the caller.
"""

from ... import refresh_context
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import threading
import uuid


RECORD_NAME = "solid"
OWNER_NAME = "solid_owner"
COMBINE_ROLES = ("join", "intersect")
CUT_ROLES = ("cut",)
RECORD_KEYS = frozenset({"version", "tool", "feature_id", "base_feature",
                         "target", "result", "tool_token", "combines"})


@dataclass(frozen=True)
class PatternRecord:
    anchor: object
    feature_id: str
    target: object
    recipe: dict


Record = PatternRecord


def _api():
    import adsk.core
    import adsk.fusion
    return adsk.core, adsk.fusion


def _signature(body):
    from ..hinge.fusion import _body_signature
    return _body_signature(body)


def _cut_signature(body):
    from .fingerprint import signature
    try:
        return signature(body)
    except (OSError,ValueError,RuntimeError):
        # Unsupported versions, transforms or export permissions retain the
        # exact existing guard, with its original cost rather than a weaker hash.
        return _signature(body)


def _items(collection):
    return tuple(collection.item(index) for index in range(collection.count))


def _valid(entity):
    return entity is not None and getattr(entity, "isValid", False)


def _valid_token(token):
    return isinstance(token, str) and 0 < len(token) <= 16384


def _token(entity):
    value = entity.entityToken
    if not _valid_token(value):
        raise ValueError("Fusion did not provide a persistent pattern reference.")
    return value


def _identity(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _resolve(design, token):
    found = design.findEntityByToken(token)
    if found is None or len(found) != 1 or not _valid(found[0]):
        raise ValueError("A saved pattern solid or history reference is missing or split. Reopen Edit.")
    return found[0]


def _body(body, root=None, *, temporary=False):
    if (not _valid(body) or not body.isSolid or body.lumps.count != 1
            or not math.isfinite(float(body.volume)) or float(body.volume) <= 0):
        raise ValueError("The selected or generated pattern result must remain one valid solid.")
    if root is not None and (body.parentComponent != root or body.assemblyContext is not None
                             or body.isTemporary):
        raise ValueError("Select one native body in the root component.")
    if temporary and body.isTemporary is not True:
        raise ValueError("Provide one detached temporary final shape, preserving the selected body.")
    return body


def _healthy(feature):
    _, fusion = _api()
    if feature.healthState != fusion.FeatureHealthStates.HealthyFeatureHealthState:
        detail = feature.errorOrWarningMessage
        raise ValueError("An owned pattern feature could not compute cleanly." + (" " + detail if detail else ""))


def _tool(body):
    if (not _valid(body) or not body.isSolid or body.lumps.count < 1
            or not math.isfinite(float(body.volume)) or float(body.volume) <= 0):
        raise ValueError("The pattern cutter must contain valid solid material.")
    return body


def _roles(recipe):
    return CUT_ROLES if recipe['version'] == 2 else COMBINE_ROLES


@contextmanager
def _history(design, feature, *, before=True):
    if not _valid(feature) or feature.parentComponent != design.rootComponent:
        raise ValueError("The saved pattern history is missing.")
    node = feature.timelineObject
    if node is None or node.index < 0:
        raise ValueError("The pattern requires ungrouped native history features.")
    marker = design.timeline.markerPosition
    if not node.rollTo(before):
        raise ValueError("Fusion could not inspect the original pattern input.")
    try:
        yield
    finally:
        design.timeline.markerPosition = marker
        if design.timeline.markerPosition != marker:
            raise ValueError("Fusion could not restore the history marker. Restore it before continuing.")


class PatternStore:
    """Persistence isolated to one tool namespace and exactly one target body."""

    def __init__(self, group, tool_id="surface_pattern"):
        if not isinstance(group, str) or not group or not isinstance(tool_id, str) or not tool_id:
            raise ValueError("A pattern namespace and tool ID are required.")
        self.attribute_group = group
        self.group = group
        self.tool_id = tool_id

    def _require_design(self, design):
        if threading.current_thread() is not threading.main_thread():
            raise ValueError("Run the pattern tool on Fusion's main thread.")
        _, fusion = _api()
        if not _valid(design) or design.designType != fusion.DesignTypes.ParametricDesignType:
            raise ValueError("Use a parametric Design document with history enabled.")
        if design.timeline.markerPosition != refresh_context.end(design):
            raise ValueError("Move the history marker to the end before using the pattern tool.")

    def _attribute(self, entity, name, value):
        if entity.attributes.add(self.attribute_group, name, value) is None:
            raise ValueError("Fusion could not save the pattern ownership record.")

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
            raise ValueError("The saved pattern solid record is missing or too large.")
        try:
            recipe = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("The saved pattern solid record is damaged.") from error
        if (not isinstance(recipe, dict) or set(recipe) != RECORD_KEYS
                or type(recipe["version"]) is not int or recipe["version"] not in (1, 2)
                or recipe["tool"] != self.tool_id or not _identity(recipe["feature_id"])):
            raise ValueError("The saved pattern solid record has an unsupported structure.")
        combines = recipe["combines"]
        if (not isinstance(combines, dict) or set(combines) != set(_roles(recipe))
                or not all(_valid_token(value) for value in combines.values())):
            raise ValueError("The saved pattern Combine references are damaged.")
        refs = [recipe[name] for name in ("base_feature", "target", "tool_token")] + list(combines.values())
        if not all(_valid_token(value) for value in refs) or len(set(refs)) != len(refs):
            raise ValueError("The saved pattern references are missing or not unique.")
        signature = recipe["result"]
        if (not isinstance(signature, str) or len(signature) != 64
                or any(character not in "0123456789abcdef" for character in signature)):
            raise ValueError("The saved pattern result fingerprint is damaged.")
        return recipe

    def _target(self, design, recipe):
        return _body(_resolve(design, recipe["target"]), design.rootComponent)

    def _feature_set(self, design, recipe):
        _, fusion = _api()
        base = _resolve(design, recipe["base_feature"])
        if fusion.BaseFeature.cast(base) is None or not self._owned(base, recipe["feature_id"]):
            raise ValueError("The pattern no longer owns its BaseFeature.")
        owned = [candidate for candidate in _items(design.rootComponent.features.baseFeatures)
                 if self._owned(candidate, recipe["feature_id"])]
        if owned != [base]:
            raise ValueError("The pattern has ambiguous ownership history.")
        combines = {role: _resolve(design, recipe["combines"][role]) for role in _roles(recipe)}
        indices = []
        for role, feature in [(None, base)] + list(combines.items()):
            if not _valid(feature) or feature.parentComponent != design.rootComponent:
                raise ValueError("The owned pattern history was moved or removed.")
            if role is not None and (fusion.CombineFeature.cast(feature) is None
                                      or not self._owned(feature, recipe["feature_id"], role)):
                raise ValueError("The pattern no longer owns its Combine features.")
            node = feature.timelineObject
            if node is None or node.index < 0:
                raise ValueError("The pattern requires ungrouped native history features.")
            indices.append(node.index)
            _healthy(feature)
        if indices != list(range(indices[0], indices[0] + 1 + len(combines))):
            raise ValueError("Features were inserted inside the pattern history. Preserve them before rebuilding.")
        # Inspect inputs in timeline order and restore the end only once.
        # Restoring between each check needlessly recomputes both Combines on
        # dense grids. Every original ownership/definition check still runs.
        # A Cut's BaseFeature only adds the cutter: the original target is
        # unchanged immediately before Cut. Retain the active BaseFeature so
        # inspecting inputs does not repeatedly re-import its dense geometry.
        history_input = combines['cut'] if recipe['version'] == 2 else base
        with _history(design, history_input):
            self._target(design, recipe)
            for role, feature in combines.items():
                if not feature.timelineObject.rollTo(True):
                    raise ValueError("Fusion could not inspect the original pattern input.")
                target, tool = self._target(design, recipe), _resolve(design, recipe["tool_token"])
                expected = self._operation(fusion, role)
                if (feature.targetBody != target or target == tool or _items(feature.toolBodies) != (tool,)
                        or feature.operation != expected or feature.isKeepToolBodies != (role == "join")
                        or feature.isNewComponent):
                    raise ValueError("A native pattern Combine definition was changed outside Partelier.")
        return base, combines

    def _read_anchor(self, design, anchor, selected_body=None):
        tag = anchor.attributes.itemByName(self.attribute_group, RECORD_NAME)
        if tag is None:
            raise ValueError("Select a supported Partelier pattern result to load its dimensions.")
        recipe = self._parse(tag.value)
        target = self._target(design, recipe)
        if selected_body is not None and selected_body != target:
            raise ValueError("The selected body does not belong to this pattern.")
        digest = _cut_signature(target) if recipe['version'] == 2 else _signature(target)
        if not self._owned(target, recipe["feature_id"], "target") or (digest != recipe["result"] and not refresh_context.authorized(design,anchor)):
            raise ValueError("The pattern result was edited after creation. Preserve those edits before rebuilding.")
        base, _ = self._feature_set(design, recipe)
        if base != anchor:
            raise ValueError("The saved pattern record identifies another feature.")
        return PatternRecord(base, recipe["feature_id"], target, recipe)

    def read(self, design, selected):
        """Body, face, edge or BaseFeature; root selection must be unambiguous."""
        self._require_design(design)
        _, fusion = _api()
        if not _valid(selected):
            raise ValueError("Select a supported Partelier pattern result.")
        base, body = fusion.BaseFeature.cast(selected), fusion.BRepBody.cast(selected)
        if body is None:
            for kind in (fusion.BRepFace, fusion.BRepEdge):
                picked = kind.cast(selected)
                if picked is not None:
                    body = picked.body
                    break
        if base is None and body is None and selected != design.rootComponent:
            raise ValueError("Select a supported Partelier pattern result.")
        if base is None:
            candidates = []
            for candidate in _items(design.rootComponent.features.baseFeatures):
                tag = candidate.attributes.itemByName(self.attribute_group, RECORD_NAME)
                if tag is None:
                    continue
                recipe = self._parse(tag.value)
                if body is None or self._owned(body, recipe["feature_id"], "target"):
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise ValueError("Select one supported pattern; the current result is missing or ambiguous.")
            base = candidates[0]
        return self._read_anchor(design, base, body)

    def _fresh(self, design, record):
        self._require_design(design)
        if not isinstance(record, PatternRecord):
            raise ValueError("Reopen Edit to load the saved pattern.")
        current = self._read_anchor(design, record.anchor)
        if (current.feature_id != record.feature_id or current.recipe != record.recipe
                or current.target != record.target):
            raise ValueError("The saved pattern changed. Reopen Edit before rebuilding.")
        return current

    @contextmanager
    def input_scope(self, design, record):
        """Yield exactly one original body before this pattern, then restore."""
        current = self._fresh(design, record)
        history_input = (_resolve(design, current.recipe['combines']['cut'])
                         if current.recipe['version'] == 2 else current.anchor)
        with _history(design, history_input):
            yield self._target(design, current.recipe)

    def _combine(self, design, target, tool, role, feature_id, created):
        core, fusion = _api()
        tools = core.ObjectCollection.create()
        if tools.add(tool) is False:
            raise ValueError("Fusion could not collect the pattern tool.")
        collection = design.rootComponent.features.combineFeatures
        spec = collection.createInput(target, tools)
        if spec is None:
            raise ValueError("Fusion could not define the in-place pattern Combine.")
        spec.operation = self._operation(fusion, role)
        spec.isKeepToolBodies = role == "join"
        spec.isNewComponent = False
        feature = collection.add(spec)
        if not _valid(feature):
            raise ValueError("Fusion could not integrate the pattern into the existing body.")
        created.append(feature)
        _healthy(feature)
        feature.name = "Partelier " + self.tool_id + " " + role
        self._stamp(feature, feature_id, role)
        return feature

    @staticmethod
    def _operation(fusion, role):
        if role == 'cut':return fusion.FeatureOperations.CutFeatureOperation
        if role == 'join':return fusion.FeatureOperations.JoinFeatureOperation
        return fusion.FeatureOperations.IntersectFeatureOperation

    def _shape(self, actual, desired):
        _body(actual)
        if abs(float(actual.volume) - float(desired.volume)) > max(1e-8, abs(float(desired.volume)) * 1e-7):
            raise ValueError("The integrated pattern volume does not match its preview.")
        for one, two in ((actual.boundingBox.minPoint, desired.boundingBox.minPoint),
                         (actual.boundingBox.maxPoint, desired.boundingBox.maxPoint)):
            if any(abs(float(getattr(one, axis)) - float(getattr(two, axis))) > 1e-6 for axis in "xyz"):
                raise ValueError("The integrated pattern bounds do not match its preview.")

    def _outputs(self, design, target, final, token, name, visible, count):
        if design.rootComponent.bRepBodies.count != count:
            raise ValueError("The pattern left unconsumed tools or duplicate bodies.")
        current = _resolve(design, token)
        if current != target or current.name != name:
            raise ValueError("Fusion replaced or renamed the selected pattern body.")
        self._shape(current, final)
        current.isLightBulbOn = visible

    def _record(self, base, feature_id, target, tool_token, combines):
        roles = CUT_ROLES if set(combines) == set(CUT_ROLES) else COMBINE_ROLES
        recipe = {"version": 2 if roles == CUT_ROLES else 1, "tool": self.tool_id, "feature_id": feature_id,
                  "base_feature": _token(base), "target": _token(target),
                  "result": (_cut_signature(target) if roles == CUT_ROLES else _signature(target)), "tool_token": tool_token,
                  "combines": {role: _token(combines[role]) for role in roles}}
        raw = json.dumps(recipe, separators=(",", ":"))
        self._parse(raw)
        self._stamp(target, feature_id, "target")
        self._stamp(base, feature_id)
        self._attribute(base, RECORD_NAME, raw)

    def create(self, design, target, final, feature_id=None, *, cut_tool=None):
        """Preserve the target using a full-shape tool or an explicit Cut tool."""
        self._require_design(design)
        target = _body(target, design.rootComponent)
        final = _body(final, temporary=True)
        tool = final if cut_tool is None else _tool(cut_tool)
        if not tool.isTemporary or tool == target:
            raise ValueError("Provide a detached temporary pattern tool.")
        roles = COMBINE_ROLES if cut_tool is None else CUT_ROLES
        if target == final:
            raise ValueError("Provide a detached final pattern shape.")
        feature_id = str(uuid.uuid4()) if feature_id is None else feature_id
        if not _identity(feature_id):
            raise ValueError("The pattern identity must be a canonical UUID.")
        if target.attributes.itemByName(self.attribute_group, OWNER_NAME) is not None:
            raise ValueError("This body already belongs to this pattern tool. Use Edit/Rebuild.")
        if any(self._owned(base, feature_id) for base in _items(design.rootComponent.features.baseFeatures)):
            raise ValueError("The pattern ownership identity already exists.")
        token, name, visible = _token(target), target.name, target.isLightBulbOn
        count = design.rootComponent.bRepBodies.count
        base, editing, created = None, False, []
        try:
            base = design.rootComponent.features.baseFeatures.add()
            if base is None or not base.startEdit():
                raise ValueError("Fusion could not start the pattern BaseFeature.")
            editing = True
            base.name = "Partelier " + self.tool_id + " " + feature_id[:8]
            source = _tool(design.rootComponent.bRepBodies.add(tool, base))
            source.name = "Partelier pattern tool"
            if _items(base.bodies) != (source,):
                raise ValueError("Fusion returned an unexpected editable pattern tool.")
            if not base.finishEdit():
                raise ValueError("Fusion could not finish the pattern BaseFeature.")
            editing = False
            tools = _items(base.bodies)
            if len(tools) != 1:
                raise ValueError("Fusion returned an unexpected pattern tool count.")
            tool_token = _token(tools[0])
            combines = {}
            for role in roles:
                combines[role] = self._combine(design, _resolve(design, token),
                    _resolve(design, tool_token), role, feature_id, created)
            self._outputs(design, target, final, token, name, visible, count)
            self._record(base, feature_id, target, tool_token, combines)
            return base
        except Exception:
            if editing and _valid(base):
                base.finishEdit()
            for feature in reversed(created):
                if _valid(feature):
                    feature.deleteMe()
            if _valid(base):
                base.deleteMe()
            raise

    def promote(self, design, record, final):
        """Convert owned end-of-history Cut to full-shape Join/Intersect.

        Raised output adds material. Keep the existing base and target; replace
        only the validated last owned Cut with owned Join/Intersect features.
        The caller owns command rollback, including any failure mid-conversion.
        """
        current=self._fresh(design,record)
        if current.recipe['version']!=2:
            raise ValueError('Only an owned grille Cut can change to raised history.')
        final=_body(final,temporary=True)
        base,combines=self._feature_set(design,current.recipe)
        finish=combines['cut']
        if finish.timelineObject.index!=design.timeline.count-1:
            raise ValueError('Raised conversion requires this grille at the end of the timeline. Preserve later features first.')
        target=current.target
        token,name,visible=_token(target),target.name,target.isLightBulbOn
        count=design.rootComponent.bRepBodies.count
        editing=False
        try:
            # Fusion 2705 refuses changing this consuming Cut to Intersect after
            # its cutter becomes a full shape. Remove only the validated owned
            # last feature, then recreate its two full-shape operations.
            if not finish.deleteMe():raise ValueError('Fusion could not replace the owned grille Cut.')
            if not base.timelineObject.rollTo(False):
                raise ValueError('Fusion could not inspect the grille tool.')
            tools=_items(base.bodies)
            if len(tools)!=1 or tools[0]!=_resolve(design,current.recipe['tool_token']):
                raise ValueError('The editable grille tool changed outside Partelier.')
            if not base.startEdit():raise ValueError('Fusion could not edit the grille tool.')
            editing=True
            sources=_items(base.bodies)
            if len(sources)!=1 or not base.updateBody(sources[0],final):
                raise ValueError('Fusion could not update the raised grille source.')
            if not base.finishEdit():raise ValueError('Fusion could not finish the raised grille source.')
            editing=False
            tool_token=_token(_items(base.bodies)[0])
            join=self._combine(design,_resolve(design,token),_resolve(design,tool_token),'join',current.feature_id,[])
            finish=self._combine(design,_resolve(design,token),_resolve(design,tool_token),'intersect',current.feature_id,[])
        finally:
            if editing and _valid(base):base.finishEdit()
            design.timeline.markerPosition=design.timeline.count
        _healthy(join);_healthy(finish)
        self._outputs(design,target,final,token,name,visible,count)
        self._record(base,current.feature_id,target,tool_token,{'join':join,'intersect':finish})
        return base

    def update(self, design, record, final, *, cut_tool=None):
        """Update the same one tool source; native body/history identities stay."""
        current = self._fresh(design, record)
        final = _body(final, temporary=True)
        tool = final if current.recipe['version'] == 1 else _tool(cut_tool)
        if not tool.isTemporary or tool == current.target:
            raise ValueError("Provide a detached temporary pattern tool.")
        if final == current.target:
            raise ValueError("Provide a detached final pattern shape.")
        base, combines = self._feature_set(design, current.recipe)
        target = current.target
        token, name, visible = _token(target), target.name, target.isLightBulbOn
        count = design.rootComponent.bRepBodies.count
        editing = False
        with _history(design, base, before=False):
            try:
                tools = _items(base.bodies)
                if len(tools) != 1 or tools[0] != _resolve(design, current.recipe["tool_token"]):
                    raise ValueError("The editable pattern tool reference changed outside Partelier.")
                if not base.startEdit():
                    raise ValueError("Fusion could not edit the pattern BaseFeature.")
                editing = True
                sources = _items(base.bodies)
                if len(sources) != 1:
                    raise ValueError("Fusion changed the editable pattern tool count.")
                if not base.updateBody(sources[0], tool):
                    raise ValueError("Fusion could not update the pattern tool.")
                if not base.finishEdit():
                    raise ValueError("Fusion could not finish the rebuilt pattern tool.")
                editing = False
                tools = _items(base.bodies)
                if len(tools) != 1:
                    raise ValueError("Fusion returned an unexpected rebuilt pattern tool count.")
                tool_token = _token(tools[0])
            finally:
                if editing and _valid(base):
                    base.finishEdit()
        for feature in combines.values():
            _healthy(feature)
        self._outputs(design, target, final, token, name, visible, count)
        self._record(base, current.feature_id, target, tool_token, combines)
        return base
