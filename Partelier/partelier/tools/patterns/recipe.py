"""Versioned face sources and one-body Create/Edit/Rebuild ownership."""

from dataclasses import dataclass, replace
import json

from .settings import PatternSettings
from .store import PatternStore
from . import fusion


GROUP="sktech_partelier_surface_pattern_23bc07a1"
STORE=PatternStore(GROUP,"surface_pattern")


@dataclass(frozen=True)
class EditTarget:
    anchor: object
    record: object
    settings: PatternSettings
    recipe: dict


def _read(anchor,record):
    tag=anchor.attributes.itemByName(GROUP,"recipe")
    if tag is None or len(tag.value)>131072:
        raise ValueError("The saved pattern recipe is missing or too large.")
    return _parse(tag.value,record)


def _parse(raw,record):
    if not isinstance(raw,str) or len(raw)>131072:
        raise ValueError("The saved pattern recipe is missing or too large.")
    try:
        value=json.loads(raw)
    except (ValueError,TypeError) as error:
        raise ValueError("The saved pattern recipe is damaged.") from error
    if (not isinstance(value,dict) or set(value)!={"version","tool","feature_id","settings","sources"}
            or type(value['version']) is not int or value['version'] not in (1,2)
            or value['tool']!='surface_pattern' or value['feature_id']!=record.feature_id):
        raise ValueError("The saved pattern recipe has an unsupported structure.")
    sources=value['sources']
    if (not isinstance(sources,dict) or set(sources)!={'body','faces'}
            or not isinstance(sources['body'],str) or not 0<len(sources['body'])<=16384
            or not isinstance(sources['faces'],list) or not 1<=len(sources['faces'])<=100
            or not all(isinstance(token,str) and 0<len(token)<=16384 for token in sources['faces'])
            or len(set(sources['faces']))!=len(sources['faces'])):
        raise ValueError("The saved pattern face references are damaged.")
    supplied=value['settings']
    if value['version']==1:
        legacy_fields=set(PatternSettings().to_dict())-{'layout_mode'}
        if not isinstance(supplied,dict) or set(supplied)!=legacy_fields:
            raise ValueError("The saved legacy pattern settings are damaged.")
        settings=PatternSettings.from_dict({**supplied,'layout_mode':'fixed'})
    else:
        settings=PatternSettings.from_dict(supplied)
    return value,settings


def _resolve(design,token):
    found=design.findEntityByToken(token)
    if found is None or len(found)!=1 or not found[0].isValid:
        raise ValueError("A saved pattern face is missing or split. Reselect the pattern sources.")
    return found[0]


def _faces(design,sources,body):
    import adsk.fusion as native
    if _resolve(design,sources['body'])!=body:
        raise ValueError("The pattern references another source body.")
    faces=tuple(native.BRepFace.cast(_resolve(design,token)) for token in sources['faces'])
    if any(face is None or face.body!=body for face in faces):
        raise ValueError("The pattern faces no longer belong to their saved source.")
    return faces


def read_edit_target(design,selected):
    record=STORE.read(design,selected)
    recipe,settings=_read(record.anchor,record)
    with STORE.input_scope(design,record) as body:
        _faces(design,recipe['sources'],body)
    return EditTarget(record.anchor,record,settings,recipe)


def prepare_edit_pattern(design,target,settings):
    if not isinstance(target,EditTarget) or _read(target.anchor,target.record)[0]!=target.recipe:
        raise ValueError("The saved pattern changed. Reopen Edit.")
    if settings.selection_scope!=target.settings.selection_scope:
        raise ValueError("Start a new pattern to change the selection scope.")
    with STORE.input_scope(design,target.record) as body:
        prepared=fusion.prepare_pattern(design,_faces(design,target.recipe['sources'],body),settings,_historical=True)
    return replace(prepared,record=target.record,saved_recipe=target.recipe)


def validate_preview_sources(prepared):
    if prepared.record is None:
        fusion.validate_sources(prepared)
    else:
        if _read(prepared.record.anchor,prepared.record)[0]!=prepared.saved_recipe:
            raise ValueError("The saved pattern changed. Reopen Edit.")
        with STORE.input_scope(prepared.design,prepared.record):
            fusion.validate_sources(prepared,_historical=True)


def _save(anchor,record,prepared):
    value={'version':2,'tool':'surface_pattern','feature_id':record.feature_id,
           'settings':prepared.settings.to_dict(),'sources':prepared.source_tokens}
    raw=json.dumps(value,separators=(',',':'))
    _parse(raw,record)
    if anchor.attributes.add(GROUP,'recipe',raw) is None:
        raise ValueError("Fusion could not save the pattern settings; the command must roll back.")


def create_pattern(design,prepared):
    validate_preview_sources(prepared)
    if design!=prepared.design or prepared.record is not None:
        raise ValueError("Use Create on the current new-pattern preview.")
    anchor=STORE.create(design,prepared.body,prepared.result_body)
    _save(anchor,STORE.read(design,anchor),prepared)
    return anchor


def rebuild_pattern(design,target,prepared):
    validate_preview_sources(prepared)
    if (design!=prepared.design or not isinstance(target,EditTarget)
            or prepared.record!=target.record or prepared.saved_recipe!=target.recipe):
        raise ValueError("Reopen Edit to rebuild the current pattern.")
    anchor=STORE.update(design,target.record,prepared.result_body)
    _save(anchor,STORE.read(design,anchor),prepared)
    return anchor
