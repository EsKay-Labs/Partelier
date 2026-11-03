"""Bounded independent mechanical pairs. Dimensions in millimetres."""
from dataclasses import dataclass, asdict, fields
import math

FAMILIES = ('slider', 'dovetail', 'bayonet', 'clevis', 'barrel', 'concealed', 'pip_hinge', 'pip_louver')


@dataclass(frozen=True)
class MechanismSettings:
    family: str = 'slider'
    length_mm: float = 40.
    width_mm: float = 18.
    height_mm: float = 8.
    wall_mm: float = 2.
    clearance_mm: float = .3
    diameter_mm: float = 32.
    pin_diameter_mm: float = 3.
    count: int = 3
    angle_deg: float = 30.
    end_stop: bool = True
    x_mm: float = 0.
    y_mm: float = 0.
    z_mm: float = 0.

    def __post_init__(self):
        if type(self.family) is not str or self.family not in FAMILIES:
            raise ValueError('Choose a supported mechanism family.')
        if type(self.end_stop) is not bool: raise ValueError('End stop must be true or false.')
        if type(self.count) is not int or not 2 <= self.count <= 9:
            raise ValueError('Count must be a whole number from 2 to 9.')
        for field in fields(self):
            if field.name in ('family','end_stop','count'): continue
            value = getattr(self,field.name)
            try:valid=type(value) in (int,float) and math.isfinite(value)
            except (TypeError,OverflowError):valid=False
            if not valid:
                raise ValueError('Mechanism dimensions must be finite numbers.')
            object.__setattr__(self,field.name,float(value))
        self.validate()

    def validate(self):
        for name, lo, hi in (('length_mm',12,300),('width_mm',6,150),('height_mm',3,100),
                ('wall_mm',.8,10),('clearance_mm',.1,2),('diameter_mm',12,150),
                ('pin_diameter_mm',1,30),('angle_deg',10,60),
                ('x_mm',-10000,10000),('y_mm',-10000,10000),('z_mm',-10000,10000)):
            if not lo <= getattr(self,name) <= hi: raise ValueError(f'{name.replace("_mm", "").replace("_", " ")} must be {lo:g}–{hi:g}.')
        w,t,h,g = self.width_mm,self.wall_mm,self.height_mm,self.clearance_mm
        if self.family in ('slider','dovetail'):
            if self.length_mm < 6*t+4*g: raise ValueError('Length must leave room for the carriage and stop.')
            if w < 2*t+2*g: raise ValueError('Rail width is too small for its wall and clearance.')
            if self.family == 'dovetail' and w <= 2*h*math.tan(math.radians(self.angle_deg))+2*t:
                raise ValueError('Dovetail angle/height leaves too little material at the neck. Increase width or reduce angle/height.')
        if self.family == 'bayonet':
            if self.diameter_mm < 6*t+4*g: raise ValueError('Bayonet diameter must leave a hollow centre and lug walls.')
            if h < 3*t+3*g: raise ValueError('Bayonet height needs three wall thicknesses plus clearance.')
            if self.angle_deg + 2*math.degrees((t+g)/(self.diameter_mm/2)) >= 360/self.count-5:
                raise ValueError('Bayonet rotation slots overlap. Reduce count or rotation.')
        if self.family == 'clevis':
            if w <= 4*t+4*g or h <= self.pin_diameter_mm+2*t:
                raise ValueError('Clevis width/height must retain material around the pin and tongue.')
            if self.length_mm <= w+2*g+2*t:
                raise ValueError('Clevis length must leave a back wall behind the circular tongue.')
        if self.family == 'pip_louver':
            r=self.pin_diameter_mm/2;rho=r+g
            if 2*math.sqrt(rho*rho-r*r) >= r*math.sqrt(2)-.02:
                raise ValueError('Pivot can escape its bed slot. Increase pivot diameter or reduce clearance.')
            if self.length_mm<=2*t+4 or t<=g+.7:
                raise ValueError('Frame needs thicker side walls for captive pivot sockets.')
            swept=math.hypot(r,t/4)
            pitch=(w-2*t)/self.count
            if pitch<=2*swept+g:raise ValueError('Vanes collide while turning. Increase frame width or reduce count/pivot diameter.')
            if h<r+math.sqrt(2)*rho+.5:raise ValueError('Frame height must leave material above the 45-degree socket roofs.')
        if self.family in ('barrel','concealed','pip_hinge'):
            if h <= self.pin_diameter_mm/2+g+t: raise ValueError('Barrel radius must leave a wall around its pin.')
            if self.length_mm/self.count <= 2*g+t: raise ValueError('Knuckles are too short for this count and clearance.')
            if self.family == 'pip_hinge' and self.count % 2 != 1:
                raise ValueError('Captive hinge needs an odd knuckle count, at least 3.')

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls,value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError('Mechanism settings are incomplete or unsupported.')
        return cls(**value)
