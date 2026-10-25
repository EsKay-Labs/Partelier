"""Atomic host-independent Small details inputs in millimetres."""

from dataclasses import dataclass,asdict,fields
import math


@dataclass(frozen=True)
class DetailSettings:
    kind: str = 'lid'
    lip_height_mm: float = 2.5
    lip_width_mm: float = 1.2
    lip_inset_mm: float = .8
    lip_clearance_mm: float = .25
    axial_clearance_mm: float = .3
    lead_mm: float = .2
    pin_diameter_mm: float = 2.5
    pin_height_mm: float = 4.
    pin_clearance_mm: float = .3
    pin_inset_mm: float = 0.
    pin_count: int = 2
    socket_floor_mm: float = .5
    rib_width_mm: float = 2.
    rib_height_a_mm: float = 12.
    rib_height_b_mm: float = 12.
    rib_count: int = 3
    rib_margin_mm: float = 5.
    rib_style: str = 'triangle'

    def __post_init__(self):
        for key,value in asdict(self).items():
            if key.endswith('_mm'):
                if isinstance(value,bool) or not isinstance(value,(float,int)) or not 0<=value<=1000 or not math.isfinite(value):
                    raise ValueError('Detail dimensions must be finite numbers from 0 to 1000 mm.')
                object.__setattr__(self,key,float(value))
        self.validate()

    def validate(self):
        if self.kind not in ('lid','alignment','ribs') or self.rib_style not in ('triangle','full'):
            raise ValueError('Choose Lid lip & groove, Alignment pins or Ribs & gussets.')
        if type(self.pin_count) is not int or self.pin_count not in (2,4):raise ValueError('Choose 2 or 4 alignment pins.')
        if type(self.rib_count) is not int or not 1<=self.rib_count<=32:raise ValueError('Use 1–32 ribs.')
        for key in ('lip_height_mm','lip_width_mm','pin_diameter_mm','pin_height_mm','socket_floor_mm','rib_width_mm','rib_height_a_mm','rib_height_b_mm'):
            if getattr(self,key)<.2:raise ValueError('Heights, widths, pin diameter and socket floor must be at least 0.2 mm.')
        if max(self.lip_clearance_mm,self.pin_clearance_mm,self.axial_clearance_mm)>2:
            raise ValueError('Clearances must be between 0 and 2 mm.')
        if self.kind=='lid' and (self.lead_mm*2>=self.lip_width_mm or self.lead_mm>=self.lip_height_mm):
            raise ValueError('The 45° lead-in must be smaller than half the lip width and its height.')
        if self.kind=='alignment' and (self.lead_mm>=self.pin_diameter_mm/2 or self.lead_mm>=self.pin_height_mm):
            raise ValueError('The 45° lead-in must be smaller than the pin radius and height.')

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)!={f.name for f in fields(cls)}:raise ValueError('Use exactly the supported Small details fields.')
        return cls(**value)
