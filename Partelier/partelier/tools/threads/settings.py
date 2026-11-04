"""Strict, host-independent printed-thread dimensions, in millimetres."""
from dataclasses import asdict, dataclass, fields, replace
import math

METRIC={'M6':(6.,1.),'M8':(8.,1.25),'M10':(10.,1.5),'M12':(12.,1.75),
        'M16':(16.,2.),'M20':(20.,2.5),'M24':(24.,3.),'M30':(30.,3.5),'M36':(36.,4.)}
BOUNDS={'diameter_mm':(6,160),'pitch_mm':(.5,12),'length_mm':(2,80),
        'depth_mm':(0,5),'clearance_mm':(0,1),'lead_in_mm':(0,5),
        'offset_mm':(0,100),'wall_mm':(1.2,12),'coupon_clearance_step_mm':(0,.3)}

@dataclass(frozen=True)
class ThreadSettings:
    profile:str='printable_v'
    mode:str='external'
    diameter_mm:float=24.
    pitch_mm:float=3.
    length_mm:float=12.
    depth_mm:float=0.
    clearance_mm:float=.25
    starts:int=1
    handedness:str='right'
    lead_in_mm:float=1.
    offset_mm:float=0.
    wall_mm:float=3.
    coupon_clearance_step_mm:float=.1

    def __post_init__(self):
        for name,choices in {'profile':('printable_v','metric','rounded'),
            'mode':('external','internal','pair','coupon'),'handedness':('right','left')}.items():
            if getattr(self,name) not in choices:raise ValueError('Choose a supported '+name.replace('_',' ')+'.')
        if type(self.starts) is not int or not 1<=self.starts<=3:raise ValueError('Thread starts must be an integer from 1 to 3.')
        for name,(low,high) in BOUNDS.items():
            value=getattr(self,name)
            try:valid=type(value) in (int,float) and math.isfinite(value) and low<=value<=high
            except OverflowError:valid=False
            if not valid:raise ValueError(name.replace('_',' ')+' must be '+str(low)+'–'+str(high)+' mm.')
        from .planner import validate
        validate(self)

    def validate(self):self.__post_init__();return self
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)!={f.name for f in fields(cls)}:
            raise ValueError('Thread settings must contain the complete current dimensions.')
        return cls(**value)

def preset(name):
    if name not in METRIC:raise ValueError('Choose a listed metric size.')
    diameter,pitch=METRIC[name]
    return ThreadSettings(profile='metric',diameter_mm=diameter,pitch_mm=pitch,
        length_mm=max(6,4*pitch),lead_in_mm=min(1,pitch/2))
