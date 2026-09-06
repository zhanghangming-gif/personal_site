from pypdf import PdfReader
from pypdf.generic import ContentStream
from collections import Counter, defaultdict
from pathlib import Path
import copy, json, math


def raw(s):
    return s.original_bytes if hasattr(s, 'original_bytes') else bytes(s)

def parse(page, reader):
    ops = ContentStream(page.get_contents(), reader).operations
    fonts = page['/Resources']['/Font']
    maps = {}
    for k, ref in fonts.items():
        f=ref.get_object(); mapping={i:chr(i) for i in range(256)}
        enc=f.get('/Encoding'); enc=enc.get_object() if enc else None
        if isinstance(enc,dict):
            c=0
            for item in enc.get('/Differences',[]):
                if isinstance(item,int): c=item
                else: mapping[c]=str(item); c+=1
        maps[k]=mapping
    state={'sx':1.,'sy':1.,'tx':0.,'ty':0.,'font':None,'size':0.,'lw':1.}
    stack=[]; chars=[]; paths=[]; pending=[]; leading=0
    tm=[1,0,0,1,0,0]; lm=tm[:]
    def point(x,y):return [float(x)*state['sx']+state['tx'],float(y)*state['sy']+state['ty']]
    for oi,(a,op) in enumerate(ops):
        if op==b'q': stack.append(state.copy())
        elif op==b'Q': state=stack.pop()
        elif op==b'cm':
            assert a[1]==a[2]==0
            state['tx']+=float(a[4])*state['sx'];state['ty']+=float(a[5])*state['sy']
            state['sx']*=float(a[0]);state['sy']*=float(a[3])
        elif op==b'w':state['lw']=float(a[0])*state['sx']
        elif op==b'BT':tm=[1,0,0,1,0,0];lm=tm[:]
        elif op==b'Tf':state['font']=str(a[0]);state['size']=float(a[1])
        elif op==b'Tm':tm=list(map(float,a));lm=tm[:]
        elif op==b'Td':
            lm[4]+=float(a[0]);lm[5]+=float(a[1]);tm=lm[:]
        elif op==b'TL':leading=float(a[0])
        elif op==b'T*':lm[5]-=leading;tm=lm[:]
        elif op in (b'Tj',b'TJ'):
            ci=0
            for val in ([a[0]] if op==b'Tj' else a[0]):
                if isinstance(val,(int,float)):
                    tm[4]-=float(val)*state['size']/1000
                else:
                    for c in raw(val):
                        x,y=point(tm[4],tm[5])
                        f=fonts[state['font']].get_object()
                        width=float(f['/Widths'][c-int(f['/FirstChar'])])*state['size']/1000
                        chars.append({'id':len(chars),'op':oi,'ci':ci,'code':c,'glyph':maps[state['font']][c],
                                      'font':state['font'],'size':state['size'],'x':x,'y':y,'lx':tm[4],'ly':tm[5],
                                      'width':width*state['sx']*tm[0],'sx':state['sx'],'sy':state['sy']})
                        tm[4]+=width*tm[0];ci+=1
        elif op in (b'm',b'l',b'c',b're',b'h'):
            pending.append((oi,op,list(a),state.copy()))
        elif op in (b'S',b'f',b'f*',b'n',b'B',b'b'):
            if pending:
                pts=[]
                for ii,oo,aa,ss in pending:
                    if oo==b're':
                        xx,yy,ww,hh=map(float,aa); pairs=[(xx,yy),(xx+ww,yy+hh)]
                    else:pairs=list(zip(aa[::2],aa[1::2]))
                    pts.extend([[float(xx)*ss['sx']+ss['tx'],float(yy)*ss['sy']+ss['ty']] for xx,yy in pairs])
                if pts:
                    paths.append({'id':len(paths),'op':oi,'paint':op.decode(),'commands':pending,
                                  'bbox':[min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts)],
                                  'lw':state['lw']})
                pending=[]
    lines=[p for p in paths if len(p['commands'])==2 and [v[1] for v in p['commands']]==[b'm',b'l'] and p['bbox'][2]-p['bbox'][0]>400 and abs(p['bbox'][3]-p['bbox'][1])<0.01]
    lines.sort(key=lambda p:-p['bbox'][1]); assert len(lines)%5==0
    staves=[]
    for i in range(0,len(lines),5):
        group=lines[i:i+5];ys=[p['bbox'][1] for p in group];spacing=(ys[0]-ys[4])/4
        assert all(abs(ys[j]-ys[j+1]-spacing)<0.02 for j in range(4))
        staves.append({'id':i//5,'top':ys[0],'bottom':ys[4],'step':spacing/2,'x0':group[0]['bbox'][0],'x1':group[0]['bbox'][2],'lines':[p['id'] for p in group]})
    for c in chars:
        s=min(staves,key=lambda s:abs(c['y']-(s['top']+s['bottom'])/2)); c['staff']=s['id']
        if c['glyph'].startswith('/noteheads.'):
            c['pitch']=round((c['y']-s['bottom'])/s['step'])
            assert abs((c['y']-s['bottom'])/s['step']-c['pitch'])<0.004,c
    for s in staves:
        s['notes']=[c['id'] for c in chars if c['staff']==s['id'] and 'pitch' in c]
        bars=[]
        for p in paths:
            x0,y0,x1,y1=p['bbox']
            if len(p['commands'])==2 and abs(x0-x1)<0.01 and abs(y0-s['bottom'])<0.05 and abs(y1-s['top'])<0.05:
                bars.append(x0)
        s['bars']=sorted(set(round(x,4) for x in bars))
    return {'ops':ops,'chars':chars,'paths':paths,'staves':staves,'maps':maps}

def pitchname(step,alter=0):
    # step 0 is E4.
    n=4*7+2+step
    return 'CDEFGAB'[n%7]+{-2:'bb',-1:'b',0:'',1:'#',2:'##'}[alter]+str(n//7)

