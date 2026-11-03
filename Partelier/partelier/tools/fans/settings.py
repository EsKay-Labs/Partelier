"""Independent strict fan settings; no changes to existing tool recipes."""

from dataclasses import dataclass,asdict,fields,replace
import math

STYLES=('axial','wide','slim','ring','prop2','prop3','prop4','blower')
PC_SIZES={'pc40':(40.,32.,10.),'pc60':(60.,50.,25.),'pc80':(80.,71.5,25.),
          'pc92':(92.,82.5,25.),'pc120':(120.,105.,25.),'pc140':(140.,124.5,25.)}
PROPS={'prop5030':(127.,76.2),'prop6040':(152.4,101.6),'prop8040':(203.2,101.6),'prop1045':(254.,114.3)}


@dataclass(frozen=True)
class FanSettings:
    style:str='axial'
    size_preset:str='pc120'
    diameter_mm:float=112.8
    blade_count:int=7
    hub_diameter_mm:float=36.
    hub_height_mm:float=14.
    shaft_diameter_mm:float=3.
    shaft_clearance_mm:float=.2
    shaft_shape:str='round'
    shaft_flat_mm:float=.5
    set_screw_diameter_mm:float=0.
    root_chord_mm:float=18.
    mid_chord_mm:float=22.
    tip_chord_mm:float=18.
    root_angle_deg:float=45.
    mid_angle_deg:float=30.
    tip_angle_deg:float=20.
    pitch_mode:str='twist'
    pitch_mm:float=70.
    sweep_deg:float=22.
    camber_percent:float=3.
    root_thickness_mm:float=1.8
    tip_thickness_mm:float=1.2
    root_fillet_mm:float=.6
    edge_round_mm:float=0.
    rotation:str='ccw'
    ring_width_mm:float=1.5
    ring_height_mm:float=10.
    tip_gap_mm:float=.6
    frame_width_mm:float=120.
    frame_depth_mm:float=25.
    mount_pitch_mm:float=105.
    mount_hole_mm:float=4.3
    axial_clearance_mm:float=1.
    guard_thickness_mm:float=2.
    guard_spoke_mm:float=2.
    guard_spokes:int=4
    output:str='rotor'
    outline_mode:str='generated'
    outline_scale_percent:float=100.
    blower_height_mm:float=10.
    blower_backplate_mm:float=1.6
    blower_vane_mm:float=1.2

    def __post_init__(self):
        enums={'style':STYLES,'size_preset':('custom',*PC_SIZES,*PROPS),'shaft_shape':('round','d'),
            'pitch_mode':('twist','pitch'),'rotation':('ccw','cw'),
            'output':('rotor','rotor_frame','rotor_guard','hub_test'),'outline_mode':('generated','sketch')}
        for name,choices in enums.items():
            if getattr(self,name) not in choices:raise ValueError('Choose a supported '+name.replace('_',' ')+'.')
        for name,lo,hi in [('blade_count',2,16),('guard_spokes',3,12)]:
            value=getattr(self,name)
            if type(value) is not int or not lo<=value<=hi:raise ValueError(f'{name.replace("_"," ")} must be a whole number from {lo} to {hi}.')
        numeric=set(asdict(self))-set(enums)-{'blade_count','guard_spokes'}
        for name in numeric:
            value=getattr(self,name)
            try:valid=type(value) in (float,int) and math.isfinite(value)
            except OverflowError:valid=False
            if not valid:raise ValueError('Fan dimensions must be finite numbers.')
            object.__setattr__(self,name,float(value))
        self.validate()

    def validate(self):
        bounds={'blower_height_mm':(2,60),'blower_backplate_mm':(.8,8),'blower_vane_mm':(.6,6),'diameter_mm':(15,500),'hub_diameter_mm':(5,180),'hub_height_mm':(2,100),'shaft_diameter_mm':(.8,60),
            'shaft_clearance_mm':(0,2),'shaft_flat_mm':(.05,20),'set_screw_diameter_mm':(0,12),
            'root_chord_mm':(2,160),'mid_chord_mm':(2,160),'tip_chord_mm':(2,160),
            'root_angle_deg':(0,75),'mid_angle_deg':(0,75),'tip_angle_deg':(0,75),
            'pitch_mm':(1,500),'sweep_deg':(-45,60),'camber_percent':(0,12),
            'root_thickness_mm':(.6,10),'tip_thickness_mm':(.6,10),'root_fillet_mm':(0,5),'edge_round_mm':(0,2),
            'ring_width_mm':(.6,12),'ring_height_mm':(1,60),'tip_gap_mm':(.2,5),
            'frame_width_mm':(20,520),'frame_depth_mm':(5,100),'mount_pitch_mm':(10,500),'mount_hole_mm':(1,12),
            'axial_clearance_mm':(.3,10),'guard_thickness_mm':(1,8),'guard_spoke_mm':(1,10),'outline_scale_percent':(10,300)}
        for name,(lo,hi) in bounds.items():
            if not lo<=getattr(self,name)<=hi:raise ValueError(f'{name.replace("_"," ")} must be {lo:g}–{hi:g}.')
        bore=self.shaft_diameter_mm+self.shaft_clearance_mm
        if self.hub_diameter_mm<=bore+3:raise ValueError('Hub diameter must leave at least 1.5 mm around the shaft hole.')
        if self.shaft_shape=='d' and self.shaft_flat_mm>=self.shaft_diameter_mm*.7:raise ValueError('D-shaft flat depth is too large for the shaft.')
        if self.set_screw_diameter_mm and (self.set_screw_diameter_mm<1 or self.set_screw_diameter_mm>self.hub_height_mm-2):
            raise ValueError('Set screw hole must be at least 1 mm and leave material above and below it.')
        if self.output=='hub_test':return
        if self.hub_diameter_mm>=self.diameter_mm-6:raise ValueError('Rotor diameter must be at least 6 mm larger than the hub.')
        if self.style=='blower':
            if self.output not in ('rotor','hub_test'):raise ValueError('The radial blower generates an impeller only. A volute housing is not implemented.')
            if self.outline_mode!='generated':raise ValueError('Blower vanes use the radial generator, not a sketch blade outline.')
            if self.blower_vane_mm>=self.hub_diameter_mm*math.sin(math.pi/self.blade_count):raise ValueError('Blower vanes overlap at the hub. Reduce vane thickness/count or enlarge Hub.')
            return
        if self.root_fillet_mm>min(self.hub_height_mm/3,(self.diameter_mm-self.hub_diameter_mm)/8):raise ValueError('Root fillet is too large for this hub/span.')
        if self.edge_round_mm>=self.tip_thickness_mm/2:raise ValueError('Tip edge radius must be smaller than half Tip thickness.')
        if max(self.root_thickness_mm,self.tip_thickness_mm)>=min(self.root_chord_mm,self.mid_chord_mm,self.tip_chord_mm)*.6:
            raise ValueError('Blade thickness must be smaller than 60% of its chord width.')
        if self.style=='ring' and 2*self.ring_width_mm>=self.diameter_mm-self.hub_diameter_mm-2:raise ValueError('Tip ring is too wide for the blade span.')
        if self.output in ('rotor_frame','rotor_guard'):
            opening=self.diameter_mm+2*self.tip_gap_mm
            if opening>self.frame_width_mm-4:raise ValueError('Frame must leave at least 2 mm outside the rotor opening. Reduce rotor diameter or enlarge Frame.')
            if not opening/2+self.mount_hole_mm/2+1<self.mount_pitch_mm/math.sqrt(2):raise ValueError('Mounting holes intersect the circular opening. Increase Mount pitch or reduce rotor diameter.')
            if self.mount_pitch_mm+self.mount_hole_mm+2>self.frame_width_mm:raise ValueError('Mounting holes need more space inside the frame edges.')

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)!={field.name for field in fields(cls)}:raise ValueError('Use the complete supported fan settings snapshot.')
        return cls(**value)


def preset(style='axial',size='pc120'):
    """Explicit preset application only; never silently overwrite Custom/Edit."""
    if style not in STYLES or size not in (*PC_SIZES,*PROPS,'custom'):raise ValueError('Choose a supported fan preset.')
    if size=='custom':return replace(preset('blower','pc120') if style=='blower' else FanSettings(),style=style,size_preset='custom')
    if style=='blower' and size in PROPS:raise ValueError('Choose a PC diameter preset or Custom for the blower.')
    if size in PC_SIZES:
        width,mount,depth=PC_SIZES[size];scale=width/120
        values=dict(style=style,size_preset=size,frame_width_mm=width,mount_pitch_mm=mount,frame_depth_mm=15 if style=='slim' and width==120 else depth,
            diameter_mm=width-6-1.2,hub_diameter_mm=max(10,36*scale),hub_height_mm=max(6,14*scale),
            root_chord_mm=max(4,18*scale),mid_chord_mm=max(5,22*scale),tip_chord_mm=max(4,18*scale),
            root_thickness_mm=max(.8,1.8*scale),tip_thickness_mm=max(.6,1.2*scale),root_fillet_mm=min(.6,.6*scale),
            ring_height_mm=max(4,10*scale),shaft_diameter_mm=2 if width<80 else 3)
        if style=='blower':values.update(blade_count=12,root_fillet_mm=0,edge_round_mm=0,sweep_deg=0,camber_percent=0,blower_height_mm=max(4,10*scale),blower_backplate_mm=max(.8,1.6*scale),blower_vane_mm=max(.6,1.2*scale))
        if style=='wide':values.update(blade_count=9,hub_diameter_mm=max(10,40*scale),mid_chord_mm=max(5,24*scale),tip_chord_mm=max(4,20*scale))
        if style=='slim':values.update(hub_diameter_mm=max(10,44*scale),blade_count=9,hub_height_mm=max(5,10*scale),root_chord_mm=max(4,16*scale),mid_chord_mm=max(5,20*scale),tip_chord_mm=max(4,15*scale),root_angle_deg=25,mid_angle_deg=18,tip_angle_deg=12,root_thickness_mm=max(.8,1.2*scale),tip_thickness_mm=max(.6,.9*scale))
        if style.startswith('prop'):values.update(blade_count=int(style[-1]),pitch_mode='pitch',pitch_mm=width*.6,sweep_deg=4)
        return FanSettings(**values)
    diameter,pitch=PROPS[size];ratio=diameter/127
    return FanSettings(style=style if style.startswith('prop') else 'prop2',size_preset=size,diameter_mm=diameter,
        blade_count=int(style[-1]) if style.startswith('prop') else 2,hub_diameter_mm=24*ratio,hub_height_mm=16*ratio,
        shaft_diameter_mm=5,root_chord_mm=18*ratio,mid_chord_mm=21*ratio,tip_chord_mm=10*ratio,
        pitch_mode='pitch',pitch_mm=pitch,sweep_deg=4,root_thickness_mm=2*ratio,tip_thickness_mm=max(.8,1*ratio),root_fillet_mm=.6)
