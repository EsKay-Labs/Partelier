"""Bounded axial thread sections. Clearance is per-side radial allowance."""
from dataclasses import dataclass
import math

def depth(s):
    return s.depth_mm or s.pitch_mm*(17*math.sqrt(3)/48 if s.profile=='metric' else .35)

def allowance(s,internal=False):
    """Apply one radial allowance to the part actually being generated.

    Standalone External shrinks the male; standalone Internal enlarges its bore.
    Matched pair and coupon preserve the nominal male and enlarge only females,
    avoiding a doubled fit gap. Plan radii remain nominal stock dimensions.
    """
    return s.clearance_mm if internal else -s.clearance_mm if s.mode=='external' else 0.

def validate(s):
    if s.profile=='metric' and s.depth_mm:
        raise ValueError('Metric uses its nominal profile depth. Set Depth to Auto or choose a printable custom profile.')
    d=depth(s)
    male_radius=s.diameter_mm/2+allowance(s)
    if d>=male_radius-1:raise ValueError('Thread depth and clearance must leave at least a 2 mm core diameter.')
    crest=s.pitch_mm*(.125 if s.profile=='metric' else .2)
    slope=math.sqrt(3) if s.profile=='metric' else 1.
    if crest+2*d/slope>=s.pitch_mm*.98:raise ValueError('Thread depth overlaps adjacent turns. Reduce Depth or increase Pitch.')
    if s.lead_in_mm*2>=s.length_mm:raise ValueError('Lead-in must be less than half the thread length.')
    if s.lead_in_mm>=male_radius-.5:raise ValueError('Lead-in and clearance must leave at least a 1 mm tip diameter.')
    if s.length_mm/(s.pitch_mm*s.starts)>32:raise ValueError('Threads are limited to 32 turns per start. Increase Pitch or reduce Length.')
    if s.length_mm<s.pitch_mm:raise ValueError('Thread length must contain at least one pitch.')
    if s.mode=='coupon' and s.clearance_mm<s.coupon_clearance_step_mm:
        raise ValueError('Coupon clearance step cannot exceed the chosen radial clearance.')
    if s.mode=='coupon' and s.clearance_mm+s.coupon_clearance_step_mm>1:
        raise ValueError('The largest coupon clearance must not exceed 1 mm.')
    if s.mode=='coupon' and s.wall_mm<s.lead_in_mm+.8:
        raise ValueError('Coupon wall must leave at least 0.8 mm beyond the entry chamfer. Increase Wall or reduce Lead-in.')

@dataclass(frozen=True)
class Plan:
    major_radius_mm:float
    minor_radius_mm:float
    female_major_radius_mm:float
    female_minor_radius_mm:float
    length_mm:float
    lead_mm:float
    turns:float
    profile:tuple

def section(s):
    r=s.diameter_mm/2;d=depth(s);crest=s.pitch_mm*(.125 if s.profile=='metric' else .2)
    if s.profile=='metric' and not s.depth_mm:
        # External nominal ISO basic geometry: H=sqrt(3)*P/2, root radius H/6,
        # minor radius R-17H/24, root-circle centre R-13H/24. The tiny root-flat
        # interval prevents touching adjacent helix sweeps. Root arcs are bounded
        # chords, not a certified manufactured tolerance-class representation.
        P=s.pitch_mm;H=math.sqrt(3)*P/2;rho=H/6;center=r-13*H/24
        theta0=math.asin(.005*P/rho)
        left=tuple((center-rho*math.cos(theta0+(math.pi/3-theta0)*i/6),
                    -P/2+rho*math.sin(theta0+(math.pi/3-theta0)*i/6)) for i in range(7))
        return left+((r,-P/16),(r,P/16))+tuple((radius,-z) for radius,z in reversed(left))
    half=crest/2;run=d/(math.sqrt(3) if s.profile=='metric' else 1.)
    points=((r-d,-half-run),(r,-half),(r,half),(r-d,half+run))
    if s.profile!='rounded':return points
    # Round the two outer crest corners inside the proven V envelope. A bounded
    # quadratic Bezier stroke removes sharp tips without enlarging the ridge.
    result=[points[0]];trim=min(d*.22,crest*.35)
    for i in (1,2):
        p=points[i];a=points[i-1];b=points[i+1]
        la=math.dist(a,p);lb=math.dist(p,b)
        start=tuple(p[k]+(a[k]-p[k])*trim/la for k in (0,1))
        end=tuple(p[k]+(b[k]-p[k])*trim/lb for k in (0,1))
        for j in range(5):
            t=j/4
            result.append(tuple((1-t)**2*start[k]+2*t*(1-t)*p[k]+t*t*end[k] for k in (0,1)))
    result.append(points[3]);return tuple(result)

def plan(s):
    validate(s);r=s.diameter_mm/2;minor=r-depth(s);lead=s.pitch_mm*s.starts
    return Plan(r,minor,r+s.clearance_mm,minor+s.clearance_mm,s.length_mm,lead,
                s.length_mm/lead,section(s))
