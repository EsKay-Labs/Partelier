"""Versioned face sources and one-body Create/Edit/Rebuild ownership."""

from dataclasses import dataclass, replace
import json
import math

from .settings import PatternSettings
from .store import PatternStore
from . import fusion, colour_store


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
            or type(value['version']) is not int or value['version'] not in (1,2,3,4,5,6,7,8,9)
            or value['tool']!='surface_pattern' or value['feature_id']!=record.feature_id):
        raise ValueError("The saved pattern recipe has an unsupported structure.")
    sources=value['sources']
    if (not isinstance(sources,dict) or set(sources)!={'body','faces'}
            or not isinstance(sources['body'],str) or not 0<len(sources['body'])<=16384
            or not isinstance(sources['faces'],list) or not 1<=len(sources['faces'])<=100
            or not all(isinstance(token,str) and 0<len(token)<=16384 for token in sources['faces'])
            or len(set(sources['faces']))!=len(sources['faces'])):
        raise ValueError("The saved pattern face references are damaged.")
    supplied=value['settings'];defaults=PatternSettings().to_dict();injected={}
    # Exact schemas remain distinct. Inject only fields absent in that version;
    # a legacy recipe carrying a newer field is damaged, not a partial upgrade.
    introduced={2:{'layout_mode':'fixed'},3:{'edge_mode':'whole'},
        4:{'density':'balanced','size_locked':False},5:{'louver_angle_deg':45},
        6:{'grille_profile':'flat','grille_height_mm':3},
        7:{name:defaults[name] for name in ('mount_mode','mount_screw','mount_clearance_mm',
            'mount_head_extra_percent','mount_head_mm','mount_inset_mm')}}
    for version,fields in introduced.items():
        if value['version']<version:injected.update(fields)
    if not isinstance(supplied,dict) or set(supplied)!=set(defaults)-set(injected):
        raise ValueError('The saved pattern settings are damaged.')
    if value['version']<=3 and supplied.get('layout_mode') not in (None,'fixed','fit','fill','balanced'):
        raise ValueError('The saved legacy layout is unsupported.')
    proposed={**injected,**supplied}
    if value['version']<8:
        angle=proposed['louver_angle_deg']
        if isinstance(angle,bool) or not isinstance(angle,(int,float)) or not 0<=angle<=60 or not math.isfinite(angle):
            raise ValueError('The saved louver tilt is damaged.')
        # Old raised geometry always used 45 regardless of the dormant value.
        # Keep the raw recipe untouched for ownership validation. A legacy flat
        # angle above the new limit proposes 45 only for the next Rebuild.
        proposed['louver_angle_deg']=(45 if proposed['pattern']=='grille_louver'
            and proposed['grille_profile']!='flat' else min(angle,45))
    settings=PatternSettings.from_dict(proposed)
    if value['version']<5 and (settings.mode=='inlay' or settings.pattern.startswith('grille_')):
        raise ValueError('The saved legacy pattern mode is unsupported.')
    return value,settings


def edit_notice(target):
    saved=target.recipe['settings']
    notices=[]
    if target.recipe['version']<9 and target.settings.mount_mode!='off':
        notices.append('Mounting now sets a minimum border from the screw/head size. Review the new preview before Rebuild; the existing body is unchanged.')
    if (target.recipe['version']<8 and saved.get('louver_angle_deg',45)>45
            and saved.get('grille_profile','flat')=='flat'):
        notices.append('Legacy tilt exceeds the new 45° limit. Edit proposes 45° for Rebuild; the existing body is unchanged.')
    return ' '.join(notices)


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
    record=STORE.read(design,colour_store.selection_anchor(selected,GROUP))
    colour_store.read(design,STORE,record)
    recipe,settings=_read(record.anchor,record)
    with STORE.input_scope(design,record) as body:
        _faces(design,recipe['sources'],body)
    return EditTarget(record.anchor,record,settings,recipe)


def prepare_edit_pattern(design,target,settings):
    if not isinstance(target,EditTarget) or _read(target.anchor,target.record)[0]!=target.recipe:
        raise ValueError("The saved pattern changed. Reopen Edit.")
    if settings.selection_scope!=target.settings.selection_scope:
        raise ValueError("Start a new pattern to change the selection scope.")
    colour_store.read(design,STORE,target.record)
    with STORE.input_scope(design,target.record) as body:
        prepared=fusion.prepare_pattern(design,_faces(design,target.recipe['sources'],body),settings,_historical=True)
    return replace(prepared,record=target.record,saved_recipe=target.recipe)


def _cut_tool(prepared):
    if not prepared.settings.pattern.startswith('grille_') or prepared.settings.mode != 'through':
        raise ValueError('This grille history supports grille types only. Preserve it before changing to another tool.')
    _,native=fusion._api();manager=native.TemporaryBRepManager.get()
    expected=float(prepared.body.volume)-float(prepared.result_body.volume)
    if not math.isfinite(expected) or expected<=1e-10:
        raise ValueError('The grille has no material to remove.')
    cutter=manager.copy(prepared.body)
    if (cutter is None or not cutter.isTemporary or
            manager.booleanOperation(cutter,prepared.result_body,native.BooleanTypes.DifferenceBooleanType) is False
            or not cutter.isValid or not cutter.isSolid or cutter.lumps.count<1
            or not math.isfinite(float(cutter.volume))
            or abs(float(cutter.volume)-expected)>max(1e-8,expected*1e-7)):
        raise ValueError('Fusion could not isolate the grille cutting material.')
    return cutter


def validate_preview_sources(prepared, *, make_cut=False):
    if prepared.record is None:
        fusion.validate_sources(prepared)
        return _cut_tool(prepared) if make_cut else None
    else:
        colour_store.read(prepared.design,STORE,prepared.record)
        if _read(prepared.record.anchor,prepared.record)[0]!=prepared.saved_recipe:
            raise ValueError("The saved pattern changed. Reopen Edit.")
        with STORE.input_scope(prepared.design,prepared.record):
            fusion.validate_sources(prepared,_historical=True)
            return _cut_tool(prepared) if make_cut else None


def _save(anchor,record,prepared):
    value={'version':9,'tool':'surface_pattern','feature_id':record.feature_id,
           'settings':prepared.settings.to_dict(),'sources':prepared.source_tokens}
    raw=json.dumps(value,separators=(',',':'))
    _parse(raw,record)
    if anchor.attributes.add(GROUP,'recipe',raw) is None:
        raise ValueError("Fusion could not save the pattern settings; the command must roll back.")


def create_pattern(design,prepared):
    cutter=validate_preview_sources(prepared,make_cut=prepared.settings.pattern.startswith('grille_') and prepared.settings.grille_profile=='flat')
    if design!=prepared.design or prepared.record is not None:
        raise ValueError("Use Create on the current new-pattern preview.")
    anchor=(STORE.create(design,prepared.body,prepared.result_body) if cutter is None
            else STORE.create(design,prepared.body,prepared.result_body,cut_tool=cutter))
    record=STORE.read(design,anchor)
    colour_store.apply(design,STORE,record,getattr(prepared,"colour_body",None))
    _save(anchor,record,prepared)
    return anchor


def rebuild_pattern(design,target,prepared):
    raised=prepared.settings.pattern.startswith('grille_') and prepared.settings.grille_profile!='flat'
    promote=raised and prepared.record is not None and prepared.record.recipe['version']==2
    cutter=validate_preview_sources(prepared,make_cut=prepared.record is not None and prepared.record.recipe['version']==2 and not raised)
    if (design!=prepared.design or not isinstance(target,EditTarget)
            or prepared.record!=target.record or prepared.saved_recipe!=target.recipe):
        raise ValueError("Reopen Edit to rebuild the current pattern.")
    previous=colour_store.read(design,STORE,target.record)
    if previous is None and getattr(prepared,"colour_body",None) is not None:
        if target.anchor.timelineObject.index+3!=design.timeline.count:
            raise ValueError("Flat colour conversion requires the pattern at the end of the timeline.")
    if previous is not None and getattr(prepared,"colour_body",None) is None:
        if previous[0].timelineObject.index!=design.timeline.count-1:
            raise ValueError("Move/remove later features before changing Flat colour to another mode.")
    anchor=(STORE.promote(design,target.record,prepared.result_body) if promote else
            STORE.update(design,target.record,prepared.result_body) if cutter is None
            else STORE.update(design,target.record,prepared.result_body,cut_tool=cutter))
    record=STORE.read(design,anchor)
    colour_store.apply(design,STORE,record,getattr(prepared,"colour_body",None),previous)
    _save(anchor,record,prepared)
    return anchor
