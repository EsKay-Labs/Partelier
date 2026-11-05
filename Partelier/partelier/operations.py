"""Named operations over existing native history; no custom-feature preview API.

Listing never rewrites geometry or legacy recipes. The native commit transaction
owns grouping, metadata and deletion. Recipe readers remain the edit authority.
"""

import json
import uuid

GROUP = 'sktech_partelier_operations_96f4d132'
RECIPES = (
    ('sktech_partelier_small_details_3cc4981e', 'record', 'detail'),
    ('sktech_partelier_hinge_8c319ce2', 'recipe', 'hinge'),
    ('sktech_veyra_hinge_8c319ce2', 'recipe', 'hinge'),
    ('sktech_partelier_snap_fit_389f7bf1', 'recipe', 'snap'),
    ('sktech_partelier_surface_pattern_23bc07a1', 'recipe', 'pattern'),
    ('sktech_partelier_fans_e46bf1a9', 'recipe', 'fan'),
    ('sktech_partelier_mechanisms_23d8c71a','recipe','mechanism'),
    ('sktech_partelier_finishing_912b4e71','record','finishing'),
    ('sktech_partelier_threads_61dba590','record','thread'),
    ('sktech_partelier_knurling_b23c9a71','record','knurling'),

)
TITLES = {'knurling':'Knob knurling','thread':'Printed thread','mechanism':'Mechanical pair','finishing':'Face detail','fan':'Fans & Propellers','lid': 'Lid lip & groove', 'alignment': 'Alignment pins',
          'ribs': 'Ribs & gussets', 'hinge': 'Pin hinge', 'snap': 'Snap-fit',
          'grilles': 'Grille', 'truss': 'Planar truss', 'honeycomb': 'Surface pattern',
          'perforation': 'Surface pattern', 'knurl': 'Surface texture'}


def _items(collection):
    return tuple(collection.item(i) for i in range(collection.count))


def _uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _data(tag):
    if tag is None or len(tag.value) > 131072:
        raise ValueError('The saved operation record is missing or too large.')
    value = json.loads(tag.value)
    if not isinstance(value, dict):
        raise ValueError('The saved operation record is invalid.')
    return value


def _alias(tool, settings):
    if tool == 'detail':
        return settings.get('kind')
    if tool != 'pattern':
        return tool
    pattern = settings.get('pattern', '')
    return ('grilles' if pattern.startswith('grille_') else 'truss' if pattern.startswith('truss_')
            else 'honeycomb' if pattern in ('hexagon','warren') else 'knurl' if settings.get('mode') == 'emboss' else 'perforation')


def records(design):
    """Small recipe records only: never traverse faces or hash body geometry."""
    values = []
    seen = set()
    for group, name, tool in RECIPES:
        for tag in design.findAttributes(group, name):
            anchor = tag.parent
            if anchor is None or not anchor.isValid:
                continue
            try:
                recipe = _data(tag)
                identity = recipe.get('id' if tool in ('detail','finishing','thread','knurling') else 'feature_id')
                settings = recipe.get('settings')
                if not _uuid(identity) or identity in seen or not isinstance(settings, dict):
                    continue
                alias = _alias(tool, settings)
                if alias not in TITLES:
                    continue
                meta_tag = anchor.attributes.itemByName(GROUP, 'operation')
                meta = _data(meta_tag) if meta_tag is not None else None
                if meta is not None and (meta.get('id') != identity or meta.get('tool') != tool):
                    raise ValueError('Operation ownership does not match its recipe.')
                title = TITLES[alias]
                pattern = settings.get('pattern', '')
                if tool == 'pattern':
                    title += ' · ' + pattern.replace('grille_', '').replace('truss_', '').replace('_', ' ').title()
                values.append({'id': identity, 'tool': tool, 'alias': alias, 'anchor': anchor,
                               'name': meta['name'] if meta else title + ' · ' + identity[:6],
                               'meta': meta, 'recipe': recipe})
                seen.add(identity)
            except (ValueError, TypeError, KeyError):
                # Damaged/unrecognized records must not become delete candidates.
                continue
    return values


def resolve(design, identity):
    if not _uuid(identity):
        raise ValueError('Choose a saved Partelier operation.')
    found = [record for record in records(design) if record['id'] == identity]
    if len(found) != 1:
        raise ValueError('This operation is no longer available. Refresh the list.')
    return found[0]


def expand(design):
    """Collapsed children have index -1. Expand only groups with our records."""
    groups = getattr(getattr(design, 'timeline', None), 'timelineGroups', None)
    if groups is None:
        return
    for group in _items(groups):
        if not group.isCollapsed:
            continue
        for item in _items(group):
            entity = item.entity
            if (entity is not None and getattr(entity, 'attributes', None) is not None
                    and (entity.attributes.itemByName(GROUP, 'owner') is not None or any(
                        entity.attributes.itemByName(g, n) is not None for g, n, _ in RECIPES))):
                group.isCollapsed = False
                break


def _members(design, record):
    meta = record['meta']
    if (meta is None or set(meta) != {'id', 'tool', 'name', 'features'}
            or not isinstance(meta['features'], list) or not 1 <= len(meta['features']) <= 256):
        raise ValueError('Use the Fusion timeline to delete this older operation.')
    values = []
    for token in meta['features']:
        if not isinstance(token, str) or not 0 < len(token) <= 16384:
            raise ValueError('The operation history references are invalid.')
        matches = design.findEntityByToken(token)
        if len(matches) != 1 or not matches[0].isValid:
            raise ValueError('The operation history was changed. Use the Fusion timeline.')
        entity = matches[0]
        owner = entity.attributes.itemByName(GROUP, 'owner')
        if (getattr(entity, 'timelineObject', None) is None or owner is None
                or _data(owner) != {'id': record['id']}):
            raise ValueError('The operation does not own every saved native feature.')
        values.append(entity)
    if len({entity.entityToken for entity in values}) != len(values):
        raise ValueError('The operation history contains duplicate references.')
    return tuple(values)


def snapshot(design):
    if design is None:
        return []
    items = []
    for record in records(design):
        items.append({key: record[key] for key in ('id', 'name', 'tool', 'alias')})
        items[-1]['canDelete'] = record['meta'] is not None
    return items


def _current_features(design, record):
    """Resolve native feature tokens only, including mode-conversion children."""
    recipe = record['recipe']
    anchor = record['anchor']
    group = next(g for g, n, tool in RECIPES if tool == record['tool'] and anchor.attributes.itemByName(g, n) is not None)
    if record['tool'] in ('snap', 'pattern'):
        recipe = _data(anchor.attributes.itemByName(group, 'pair' if record['tool'] == 'snap' else 'solid'))
    tokens = [recipe['base'] if record['tool'] in ('detail','finishing','thread','knurling') else recipe['base_feature']]
    combines = recipe.get('combines', {})
    if record['tool']=='mechanism' and recipe.get('attachment'):combines=recipe['attachment']['combines']
    tokens.extend(combines.values() if isinstance(combines, dict) else combines)
    colour = anchor.attributes.itemByName(group, 'flat_colour')
    if colour is not None:
        tokens.append(_data(colour)['feature'])
    features = []
    for token in tokens:
        found = design.findEntityByToken(token)
        if len(found) != 1 or not found[0].isValid or getattr(found[0], 'timelineObject', None) is None:
            raise ValueError('The saved operation history is incomplete.')
        features.append(found[0])
    # Independent hinge components also own their occurrence timeline row.
    if record['tool'] == 'hinge' and getattr(anchor, 'timelineObject', None) is None:
        occurrences = design.rootComponent.allOccurrencesByComponent(anchor)
        features.extend(_items(occurrences))
    return tuple(sorted(features, key=lambda entity: entity.timelineObject.index))


def capture(design, anchor, tool, settings, start, *, editing=False):
    """Called only after successful persistence, inside its native transaction."""
    if anchor is None:
        raise ValueError('The operation did not return its saved feature.')
    record = next((r for r in records(design) if r['anchor'] == anchor), None)
    if record is None or record['tool'] != tool:
        raise ValueError('The created operation has no matching saved recipe.')
    meta = record['meta']
    if editing:
        features = _current_features(design, record)
        if meta is None:
            # Adoption happens only in an explicit, successfully validated
            # Rebuild transaction, never while listing or opening the design.
            indices = [entity.timelineObject.index for entity in features]
            if indices != list(range(indices[0], indices[0] + len(indices))):
                return
            parents = [entity.timelineObject.parentGroup for entity in features]
            if any(parent is not None for parent in parents):
                return  # Preserve pre-existing user timeline organization.
            meta = {'features': []}
        previous = []
        for token in meta['features']:
            found = design.findEntityByToken(token)
            if len(found) == 1 and found[0].isValid:
                previous.append(found[0])
        if len(previous) == len(meta['features']) and tuple(previous) == features:
            _members(design, record)
            from .auto_refresh import capture as capture_update
            capture_update(design,anchor)
            return
        # Pattern mode conversions may add/remove their owned colour/Cut nodes.
        # Regroup only their current exact, consecutive recipe-owned features.
        groups = []
        for feature in previous:
            group = feature.timelineObject.parentGroup
            if group is not None and group not in groups:
                groups.append(group)
        for group in groups:
            children = tuple(item.entity for item in _items(group))
            if any(entity not in previous for entity in children):
                raise ValueError('A user feature was inserted in this operation group.')
            group.isCollapsed=True
            if group.deleteMe(False) is False:
                raise ValueError('Fusion could not update the operation group.')
        indices = [entity.timelineObject.index for entity in features]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise ValueError('The rebuilt operation history is no longer consecutive.')
        start, end = indices[0], indices[-1]
    else:
        end = design.timeline.count - 1
        if not 0 <= start <= end:
            raise ValueError('The operation produced no native history to group.')
        features = tuple(design.timeline.item(i).entity for i in range(start, end + 1))
    if any(entity is None or not getattr(entity, 'entityToken', None) for entity in features):
        raise ValueError('The operation contains unsupported timeline entries.')
    # Fusion needs at least two timeline entries for a group. A standalone
    # owned BaseFeature is already one coherent operation and gets the same
    # exact Edit/Delete metadata without an artificial second history entry.
    if start < end:
        group = design.timeline.timelineGroups.add(start, end)
        if group is None:
            raise ValueError('Fusion could not group the operation history.')
        group.name = 'Partelier · ' + record['name']
        group.isCollapsed = False
    value = {'id': record['id'], 'tool': tool, 'name': record['name'],
             'features': [entity.entityToken for entity in features]}
    for feature in features:
        if feature.attributes.add(GROUP, 'owner', json.dumps({'id': record['id']})) is None:
            raise ValueError('Fusion could not save native feature ownership.')
    if anchor.attributes.add(GROUP, 'operation', json.dumps(value, separators=(',', ':'))) is None:
        raise ValueError('Fusion could not save the operation history.')
    from .auto_refresh import capture as capture_update
    capture_update(design,anchor)


def delete(design, identity):
    """Delete an exact owned suffix only; source solids are never candidates."""
    expand(design)
    record = resolve(design, identity)
    features = _members(design, record)
    if design.timeline.markerPosition != design.timeline.count:
        raise ValueError('Move the timeline to the end before deleting an operation.')
    indices = [feature.timelineObject.index for feature in features]
    if indices != list(range(indices[0], design.timeline.count)):
        raise ValueError('This operation has later features. Use the Fusion timeline to review those dependencies before deleting it.')
    # Every child must still be the exact saved native feature in the same root
    # operation. Deletion is reversed and the caller aborts on any failed step.
    for feature in reversed(features):
        if feature.deleteMe() is False:
            raise ValueError('Fusion could not delete the complete operation. The transaction must roll back.')


class DeleteCommand:
    """One undoable native transaction, never a write in an HTML callback."""
    command_id = 'sktech_partelier_delete_operation_96f4d132'

    def __init__(self, completed):
        self.completed = completed
        self.definition = None
        self.created = None
        self.pending = None
        self.handlers = []

    @property
    def busy(self):
        return self.pending is not None or bool(self.handlers)

    def start(self, core=None):
        if core is None:
            import adsk.core as core
        self.core=core
        ui = core.Application.get().userInterface
        owner = self

        class Execute(core.CommandEventHandler):
            def notify(self, args):
                try:
                    if owner.pending is None:
                        return
                    design, identity = owner.pending
                    if core.Application.get().activeProduct != design:
                        raise ValueError('Return to the original design before deleting the operation.')
                    delete(design, identity)
                    owner.message = 'Operation deleted. Undo restores it.'
                except Exception as error:
                    args.executeFailed = True
                    args.executeFailedMessage = str(error)
                    owner.message = str(error)

        class Destroy(core.CommandEventHandler):
            def notify(self, args):
                owner.pending = None
                owner.handlers.clear()
                owner.completed(owner.message)

        class Created(core.CommandCreatedEventHandler):
            def notify(self, args):
                command = args.command
                command.isExecutedWhenPreEmpted = False
                command.isAutoExecute = True
                command.isOKButtonVisible = False
                for event, handler in ((command.execute, Execute()), (command.destroy, Destroy())):
                    if event.add(handler) is False:
                        raise RuntimeError('Fusion could not register operation deletion.')
                    owner.handlers.append(handler)

        self.definition = ui.commandDefinitions.itemById(self.command_id)
        if self.definition is None:
            self.definition = ui.commandDefinitions.addButtonDefinition(
                self.command_id, 'Partelier: Delete operation', 'Delete the explicitly chosen Partelier operation.')
        self.created = Created()
        if self.definition.commandCreated.add(self.created) is False:
            raise RuntimeError('Fusion could not register operation deletion.')

    def launch(self, design, identity):
        if self.busy:
            raise ValueError('Wait for operation deletion to finish.')
        record = resolve(design, identity)
        _members(design, record)
        self.pending = design, identity
        self.message = 'Operation deletion cancelled.'
        try:
            if self.definition.execute() is False:
                raise ValueError('Fusion could not start operation deletion.')
        except Exception:
            self.pending = None
            raise

    def cancel_palette(self):
        self.pending=None
        self.message='Feature deletion cancelled.'
        ui=self.core.Application.get().userInterface
        if ui.activeCommand==self.command_id:ui.terminateActiveCommand()

    def stop(self):
        ui = self.core.Application.get().userInterface
        if ui.activeCommand == self.command_id:
            ui.terminateActiveCommand()
        if self.definition is not None and self.definition.isValid:
            self.definition.commandCreated.remove(self.created)
            self.definition.deleteMe()
        self.definition = self.created = None
        self.pending = None
        self.handlers.clear()
