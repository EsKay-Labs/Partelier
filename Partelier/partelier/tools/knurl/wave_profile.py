"""Pure C1 wave curves and Bernstein control-hull overhang bounds."""
import math


def profile(outer,root,half,depth):
    outside=.1;width=half*(depth+outside)/depth
    return ((root,0.),(outer+outside,-width),(outer+outside,width))


def spans(point,low,high,pitch,lean,radius):
    count=max(1,math.ceil((high-low)/pitch*8))
    if count>128:raise ValueError('Use larger Spacing or a shorter face for smooth Waves.')
    amplitude=math.tan(math.radians(lean))*pitch/(2*math.pi*radius)
    def frame(z):
        angle=amplitude*math.sin(2*math.pi*z/pitch)
        velocity=amplitude*2*math.pi/pitch*math.cos(2*math.pi*z/pitch)
        x=point[0]*math.cos(angle)-point[1]*math.sin(angle)
        y=point[0]*math.sin(angle)+point[1]*math.cos(angle)
        return (x,y,z),(-y*velocity,x*velocity,1.)
    levels=tuple(low+(high-low)*i/count for i in range(count+1))
    result=[]
    for a,b in zip(levels,levels[1:]):
        pa,da=frame(a);pb,db=frame(b);step=(b-a)/3
        result.append((pa,tuple(x+step*d for x,d in zip(pa,da)),tuple(x-step*d for x,d in zip(pb,db)),pb))
    return tuple(result),levels


def maximum_slope(outer,root,half,depth,height,pitch,angle):
    """Bound actual cubic ruled faces using Bernstein polynomial control hulls.

    The axial normal cross(E(t),P'(t)) has degree five. Its coefficient hull
    bounds the numerator; a positive projection of E's control hull bounds the
    horizontal normal from below. Both ruled-face endpoints bound all u values.
    """
    paths=[spans(point,-.1,height+.1,pitch,angle,outer)[0] for point in profile(outer,root,half,depth)]
    maximum=0.
    for i in range(3):
        j=(i+1)%3
        for one,two in zip(paths[i],paths[j]):
            edge=tuple((b[0]-a[0],b[1]-a[1]) for a,b in zip(one,two))
            centre=(sum(e[0] for e in edge),sum(e[1] for e in edge))
            length=math.hypot(*centre)
            if length<1e-9:raise ValueError('Wave groove orientation collapsed.')
            unit=(centre[0]/length,centre[1]/length)
            lower=min(e[0]*unit[0]+e[1]*unit[1] for e in edge)
            if lower<=1e-9:raise ValueError('Use a smaller Wave angle or larger Spacing.')
            dz=one[-1][2]-one[0][2]
            for points in (one,two):
                derivative=tuple((3*(b[0]-a[0]),3*(b[1]-a[1])) for a,b in zip(points,points[1:]))
                for k in range(6):
                    value=0.
                    for a in range(4):
                        b=k-a
                        if 0<=b<3:
                            cross=edge[a][0]*derivative[b][1]-edge[a][1]*derivative[b][0]
                            value+=math.comb(3,a)*math.comb(2,b)/math.comb(5,k)*cross
                    maximum=max(maximum,abs(value)/(dz*lower))
    return maximum
