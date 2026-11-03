"""Strict face-detail dimensions in millimetres."""

from dataclasses import dataclass,asdict

import math



KINDS=('notch','keyhole','stop','text','arrow','scale')

@dataclass(frozen=True)

class FinishingSettings:

    kind: str='notch'
    edge_side: str='top'

    width_mm: float=12.

    length_mm: float=20.

    depth_mm: float=2.

    shaft_mm: float=4.3

    height_mm: float=5.

    stroke_mm: float=.8

    offset_x_mm: float=0.

    offset_y_mm: float=0.

    rotation_deg: float=0.

    count: int=11

    major_every: int=5

    mode: str='engrave'

    text: str='PARTELIER'

    font: str='Arial'

    def to_dict(self):return asdict(self)

    @classmethod

    def from_dict(cls,value):

        if not isinstance(value,dict) or set(value)!=set(cls().to_dict()):raise ValueError('Unexpected face detail fields.')

        result=cls(**value);result.validate();return result

    def validate(self):

        if self.edge_side not in ('top','bottom','left','right'):raise ValueError('Choose one rectangular boundary side.')
        if self.kind not in KINDS or self.mode not in ('engrave','emboss'):raise ValueError('Choose a supported face detail and relief.')

        for key,value in self.to_dict().items():

            if key.endswith('_mm') or key=='rotation_deg':

                try:valid=type(value) in (int,float) and abs(value)<=1000 and math.isfinite(value)
                except (TypeError,OverflowError):valid=False
                if not valid:raise ValueError('Dimensions must be finite and at most 1000 mm.')

                if key not in ('offset_x_mm','offset_y_mm','rotation_deg') and value<=0:raise ValueError('Sizes must be positive.')

        if not -180<=self.rotation_deg<=180:raise ValueError('Direction must be between -180 and 180 degrees.')

        if type(self.count) is not int or not 2<=self.count<=101 or type(self.major_every) is not int or not 1<=self.major_every<=20:raise ValueError('Use 2–101 marks and a major interval of 1–20.')

        if type(self.text) is not str or not self.text.strip() or len(self.text)>80 or any(ord(c)<32 or c in '<>' for c in self.text):raise ValueError('Enter 1–80 printable text characters, without formatting tags.')

        if type(self.font) is not str or not self.font.strip() or len(self.font)>80:raise ValueError('Enter a font name installed on this computer.')

        if self.kind=='keyhole' and (self.shaft_mm>=self.width_mm or self.length_mm<=self.width_mm):raise ValueError('Keyhole head must be wider than the shaft and shorter than the total slot.')

        if self.kind in ('arrow','scale') and self.stroke_mm>=min(self.width_mm,self.length_mm)/2:raise ValueError('Reduce the marker stroke width.')

        if self.kind=='scale' and self.stroke_mm>=self.length_mm/(self.count-1):raise ValueError('Scale marks need a positive gap.')

    @property

    def additive(self):return self.kind=='stop' or self.kind in ('text','arrow','scale') and self.mode=='emboss'
