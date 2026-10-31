import potrace, json, sys
import numpy as np
from PIL import Image
def trace(mask, scale):
    bm = potrace.Bitmap(np.array(mask)<128)
    pl = bm.trace(turdsize=8, alphamax=1.0, opticurve=True, opttolerance=0.2)
    f = lambda p: f"{p.x/scale:.2f} {p.y/scale:.2f}"
    d=[]
    for c in pl:
        d.append("M"+f(c.start_point))
        for s in c.segments:
            d.append(("L"+f(s.c)+" L"+f(s.end_point)) if s.is_corner else ("C"+f(s.c1)+" "+f(s.c2)+" "+f(s.end_point)))
        d.append("Z")
    return " ".join(d)
out={}
D=sys.argv[1]
for n in ['leaf-top-left','leaf-bottom-right','swoop-top-right','swoop-bottom-left','wordmark']:
    a=Image.open(f"{D}/{n}.png").getchannel('A'); out[n]=trace(a,4); print(n,len(out[n]))
im=Image.open('board.png').convert('RGB')
def colour_masks(box,S=8):
    c=im.crop(box).resize(((box[2]-box[0])*S,(box[3]-box[1])*S),Image.LANCZOS)
    px=c.load(); W,H=c.size
    mar=Image.new('L',(W,H),0); ink=Image.new('L',(W,H),0); mp=mar.load(); ip=ink.load()
    for y in range(H):
        for x in range(W):
            r,g,b=px[x,y]; lum=(r+g+b)/3
            if r-g>45 and lum<190: mp[x,y]=255
            elif lum<110 and abs(r-g)<30: ip[x,y]=255
    return mar,ink
for name,box in {'search':(305,590,410,705),'ask':(420,590,528,705)}.items():
    mar,ink=colour_masks(box)
    out[name+'-maroon']=trace(mar,8); out[name+'-ink']=trace(ink,8)
    print(name, [v/8 for v in mar.getbbox()], [v/8 for v in ink.getbbox()])
json.dump(out,open('paths.json','w'))
