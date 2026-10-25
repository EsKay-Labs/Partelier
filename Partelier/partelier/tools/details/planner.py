"""Bounded rectangle-ring, matching-pin and evenly spaced rib dimensions."""

import math


def rectangle(bounds,inset=0):
    lo,hi,bottom,top=bounds;lo+=inset;hi-=inset;bottom+=inset;top-=inset
    if hi-lo<=.2 or top-bottom<=.2:raise ValueError('The inset/width leaves no closed rectangular region.')
    return ((lo,bottom),(hi,bottom),(hi,top),(lo,top))


def pins(bounds,settings):
    radius=(settings.pin_diameter_mm+settings.pin_clearance_mm)/2+settings.lead_mm
    inset=settings.pin_inset_mm or radius+.5
    if inset<radius+.1:raise ValueError(f'Pin centres need at least {radius+.1:.2f} mm inset. Use 0 for Auto.')
    lo,hi,bottom,top=bounds
    if min(hi-lo,top-bottom)<=2*inset+2*radius+.2:raise ValueError('The selected face is too small for separated pins and receiving holes.')
    points=((lo+inset,bottom+inset),(hi-inset,top-inset))
    if settings.pin_count==4:points+=((lo+inset,top-inset),(hi-inset,bottom+inset))
    return points


def rib_positions(length,width,count,margin):
    if (not all(math.isfinite(v) for v in (length,width,margin)) or length<=0 or width<=0 or margin<0
            or type(count) is not int or not 1<=count<=32):raise ValueError('Use finite rib dimensions and 1–32 ribs.')
    available=length-2*margin-width
    if available<0:raise ValueError('End margins and rib width exceed the common support edge.')
    if count==1:return (length/2,)
    step=available/(count-1)
    if step<width+.2:raise ValueError('Ribs overlap. Reduce count/width/end margins or choose a longer edge.')
    return tuple(margin+width/2+i*step for i in range(count))


def socket_depth(height,gap,axial):
    if gap< -1e-4:raise ValueError('The selected mating faces overlap. Choose faces facing each other across a nonnegative gap.')
    if height-gap<.2:raise ValueError(f'Height must exceed the {gap:.2f} mm face gap by at least 0.2 mm.')
    return height-max(0,gap)+axial
