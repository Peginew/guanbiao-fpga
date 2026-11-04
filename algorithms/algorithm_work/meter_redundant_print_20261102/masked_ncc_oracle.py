"""Small double-precision independent oracle for the pre-G masked NCC operator."""
import math
import numpy as np


def correlate(image,template,mask):
    image=np.asarray(image,np.float64);template=np.asarray(template,np.float64);mask=np.asarray(mask,bool)
    h,w=template.shape
    assert mask.shape==template.shape and mask.any()
    tt=template[mask];tt=tt-tt.mean();te=float(tt@tt)
    out=np.full((image.shape[0]-h+1,image.shape[1]-w+1),-np.inf,np.float64)
    if te<=1e-8:return out
    for y in range(out.shape[0]):
        for x in range(out.shape[1]):
            q=image[y:y+h,x:x+w][mask];q=q-q.mean();qe=float(q@q)
            if qe>1e-8:out[y,x]=float(q@tt)/math.sqrt(qe*te)
    return out


def mask_for_logo(width=13,radius=5):
    yy,xx=np.mgrid[:width,:width];center=(width-1)/2
    return (xx-center)**2+(yy-center)**2<=radius**2
