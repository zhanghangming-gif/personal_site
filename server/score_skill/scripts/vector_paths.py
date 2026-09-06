from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from collections import Counter,defaultdict
import json, hashlib


def parse_paths(page,reader):
    ops=ContentStream(page.get_contents(),reader).operations
    state=[1.,1.,0.,0.];stack=[];pending=[];paths=[]
    for i,(a,op) in enumerate(ops):
        if op==b'q':stack.append(state[:])
        elif op==b'Q':state=stack.pop()
        elif op==b'cm':
            assert a[1]==a[2]==0
            sx,sy,tx,ty=state
            state=[sx*float(a[0]),sy*float(a[3]),tx+sx*float(a[4]),ty+sy*float(a[5])]
        elif op in [b'm',b'l',b'c',b'v',b'y',b'h',b're']:
            pending.append((i,op,list(map(float,a)),state[:]))
        elif op in [b'f',b'f*',b'S',b'n'] and pending:
            pts=[]
            for ii,oo,aa,ss in pending:
                sx,sy,tx,ty=ss
                if oo==b're':
                    x,y,w,h=aa; pairs=[(x,y),(x+w,y+h)]
                else:pairs=list(zip(aa[::2],aa[1::2]))
                pts += [(x*sx+tx,y*sy+ty) for x,y in pairs]
            bb=[min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts)]
            norm=[]
            for ii,oo,aa,ss in pending:
                sx,sy,tx,ty=ss
                if oo==b're':
                    v=[aa[0]*sx+tx-bb[0],aa[1]*sy+ty-bb[1],aa[2]*sx,aa[3]*sy]
                else:v=[z for x,y in zip(aa[::2],aa[1::2]) for z in (x*sx+tx-bb[0],y*sy+ty-bb[1])]
                norm.append((oo.decode(),[round(z,2) for z in v]))
            sig=hashlib.sha256(json.dumps(norm).encode()).hexdigest()[:10]
            paths.append({'id':len(paths),'paint':op.decode(),'op':i,'commands':pending,'bbox':bb,'sig':sig,'seq':''.join(v[1].decode()+' ' for v in pending)})
            pending=[]
    return ops,paths

