from vector_paths import *
from pypdf.generic import FloatObject, NameObject, DecodedStreamObject
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
import argparse

SOURCE=None
DEST=None
ROOT=Path(__file__).resolve().parent.parent/'assets'
STEP=2.48
NATURAL=[4,5,7,9,11,12,14]
def semi(p):return NATURAL[p%7]+12*(p//7)
def keyalt(p,fifths):
    letter='EFGABCD'[p%7]
    return (1 if letter in 'FCGDAEB'[:fifths] else 0) if fifths>=0 else (-1 if letter in 'BEADGCF'[:-fifths] else 0)

def analyze(reader):
    page=reader.pages[0];ops,paths=parse_paths(page,reader)
    stafflines=[p for p in paths if p['seq']=='re ' and p['bbox'][2]-p['bbox'][0]>450 and p['bbox'][3]-p['bbox'][1]<.6]
    stafflines.sort(key=lambda p:-sum(p['bbox'][1::2])/2)
    assert len(stafflines)==35
    staves=[]
    for i in range(7):
        lines=stafflines[i*5:i*5+5]
        bottom=sum(lines[-1]['bbox'][1::2])/2
        staves.append({'id':i,'bottom':bottom,'top':sum(lines[0]['bbox'][1::2])/2,'step':STEP,'lines':[p['id'] for p in lines]})
    notes=[]
    for p in paths:
        x0,y0,x1,y1=p['bbox'];w=x1-x0;h=y1-y0
        si=min(range(7),key=lambda k:abs((y0+y1)/2-(staves[k]['bottom']+staves[k]['top'])/2))
        p['staff']=si;p['kind']='unknown'
        if p['seq'] in ['m c c c c ','m c c c c h m c c c c '] and 4<w<7.2 and 3<h<5.6:
            pos=round(((y0+y1)/2-staves[si]['bottom'])/STEP)
            assert abs((y0+y1)/2-(staves[si]['bottom']+pos*STEP))<.18,(p,pos)
            p.update(kind='note',pitch=pos)
            fifths=-1 if si>4 or si==4 and x0>124 else 0
            n={'path_id':p['id'],'staff':si,'source_step':pos,'source_alter':keyalt(pos,fifths),'source_fifths':fifths,
               'target_step':pos-1,'target_fifths':fifths+5,'x':x0,'y':(y0+y1)/2,'width':w,'grace':w<5}
            n['target_alter']=semi(pos)+n['source_alter']-1-semi(pos-1)
            assert n['target_alter']==keyalt(pos-1,fifths+5)
            notes.append(n)
        elif p['seq']=='m c c c c ' and 1.7<w<2.1 and 1.7<h<2.1:p['kind']='dot'
        elif p['id']==0:p['kind']='header'
        elif p['id'] in [116,142,180,223,230,249,291]:p['kind']='clef'
        elif p['id'] in [232,250,292]:p['kind']='key'
        elif p['id'] in [120,148]:p['kind']='number_background'
        elif p['id'] in [117,118,119,145,146,147]:p['kind']='multirest'
        elif p['id'] in [19,20,21,22,97,98]:p['kind']='hairpin'
        elif p['id'] in [224,231]:p['kind']='accent'
        elif p['id']==306:p['kind']='fermata'
        elif p['id'] in [315,374,531,555,570,745]:p['kind']='flag'
        elif p['id']==568:p['kind']='grace_slash'
        elif p['seq']=='re ':
            if p['id'] in staves[si]['lines']:p['kind']='staff'
            elif w<.55 and h>6:p['kind']='stem'
            elif .6<w<3 and 19.5<h<20.2:p['kind']='barline'
            elif 5<w<12 and .4<h<.9:p['kind']='ledger'
            elif w>6 and 2.3<h<2.6:p['kind']='beam'
        elif p['seq']=='m l l l l ':p['kind']='beam'
        elif p['id']<313 and 'c' in p['seq']:p['kind']='curve'
        elif p['id']>=313 and (p['seq'].count('c')>=7 or 'y' in p['seq']):p['kind']='rest'
    assert not [p['id'] for p in paths if p['kind']=='unknown'],[(p['id'],p['seq'],p['bbox']) for p in paths if p['kind']=='unknown']
    return ops,paths,staves,notes

def layout(si,x):
    start=74.0 if si<5 else 81.0
    events=[(start,31.)] if si<4 else [(start,31.),(126.,18.)] if si==4 else [(start,22.)]
    ratio=1-sum(z[1] for z in events)/(552.72-start)
    if x<start:return x,1.
    return start+(x-start)*ratio+sum(d for at,d in events if x>=at),ratio

def main():
    global SOURCE,DEST,ROOT
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--font',type=Path,default=ROOT/'Bravura.otf')
    args=ap.parse_args();SOURCE=args.input;DEST=args.output;ROOT=args.work_dir;ROOT.mkdir(parents=True,exist_ok=True)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='67cb3cabef6f0aa8f4dcb6afa769bb97b94b53e4349273f25e6e2eaf54b89d88':
        raise ValueError('This adapter only accepts the reviewed Wanquan score. Run inspect and follow the skill for a new score.')
    r=PdfReader(SOURCE);assert len(r.pages)==1
    ops,paths,staves,notes=analyze(r);replacements={};omitted=set();kinds=Counter();path_dys={}
    for p in paths:
        si=p['staff'];kind=p['kind'];kinds[kind]+=1
        if kind in ['key','ledger']:
            for oi,oo,aa,ss in p['commands']:replacements[oi]=[]
            replacements[p['op']]=[];omitted.add(p['id']);continue
        dy=-STEP if kind in ['note','stem','beam','curve','flag','grace_slash','accent','fermata'] else 0.
        if kind=='dot':
            x0,y0,x1,y1=p['bbox'];cx=(x0+x1)/2;cy=(y0+y1)/2
            candidates=[n for n in notes if n['staff']==si and 5<cx-n['x']<14 and abs(cy-n['y'])<STEP+.2]
            assert candidates,(p,'dot attachment')
            n=min(candidates,key=lambda n:abs(cy-n['y']))
            want=n['target_step']+(1 if n['target_step']%2==0 else 0)
            dy=staves[si]['bottom']+want*STEP-cy
        path_dys[p['id']]=dy
        fixed=kind in ['staff','clef','header']
        for oi,oo,aa,ss in p['commands']:
            if oo==b'h':continue
            sx,sy,tx,ty=ss
            def xy(x,y):
                x=x*sx+tx;y=y*sy+ty
                if not fixed:x=layout(si,x)[0]
                return [(x-tx)/sx,(y+dy-ty)/sy]
            if oo==b're':
                q0=xy(aa[0],aa[1]);q1=xy(aa[0]+aa[2],aa[1]+aa[3]);bb=q0+[q1[0]-q0[0],q1[1]-q0[1]]
            else:bb=[z for x,y in zip(aa[::2],aa[1::2]) for z in xy(x,y)]
            replacements[oi]=[(list(map(FloatObject,bb)),oo)]
    # Expand Tm/Td into independent line matrices; keep each original show string byte-for-byte.
    state=[1.,1.,0.,0.];stack=[];lm=[1.,0.,0.,1.,0.,0.];tf=None
    for oi,(aa,oo) in enumerate(ops):
        if oo==b'q':stack.append(state[:])
        elif oo==b'Q':state=stack.pop()
        elif oo==b'cm':
            sx,sy,tx,ty=state;state=[sx*float(aa[0]),sy*float(aa[3]),tx+sx*float(aa[4]),ty+sy*float(aa[5])]
        elif oo==b'Tf':tf=str(aa[0])
        elif oo in [b'Tm',b'Td']:
            if oo==b'Tm':lm=list(map(float,aa))
            else:
                dx,dy=map(float,aa);lm[4]+=dx*lm[0]+dy*lm[2];lm[5]+=dx*lm[1]+dy*lm[3]
            sx,sy,tx,ty=state;x=lm[4]*sx+tx;y=lm[5]*sy+ty
            si=min(range(7),key=lambda k:abs(y-(staves[k]['bottom']+staves[k]['top'])/2))
            matrix=lm[:]
            if y<735 and x>=74:
                nx,ratio=layout(si,x);matrix[0]*=ratio;matrix[4]=(nx-tx)/sx
                # Dynamics remain outside the lowered note and slur region.
                if tf in ['/R10','/R30'] and y<staves[si]['bottom']:matrix[5]-=STEP/sy
            replacements[oi]=[(list(map(FloatObject,matrix)),b'Tm')]
    newops=[]
    for oi,item in enumerate(ops):newops.extend(replacements.get(oi,[item]))
    extras=[]
    # Embed sharp outlines from the licensed SMuFL font, independent of PDF font encodings.
    ft=TTFont(args.font);gs=ft.getGlyphSet();pen=RecordingPen();gs[ft.getBestCmap()[0xE262]].draw(pen)
    scale=19.84/ft['head'].unitsPerEm
    key_positions=[]
    for si,s in enumerate(staves):
        keys=[(74.,5)] if si<5 else [(74.,4)]
        if si==4:keys.append((layout(si,119.52)[0],4))
        for xx,count in keys:
            for j,pos in enumerate([8,5,9,6,3][:count]):
                x=xx+j*5.7;y=s['bottom']+pos*STEP
                extras.append(f'q {scale} 0 0 {scale} {x} {y} cm\n')
                for op,pts in pen.value:
                    if op=='moveTo':extras.append(f'{pts[0][0]} {pts[0][1]} m\n')
                    elif op=='lineTo':extras.append(f'{pts[0][0]} {pts[0][1]} l\n')
                    elif op=='curveTo':extras.append(' '.join(str(z) for p in pts for z in p)+' c\n')
                    elif op=='closePath':extras.append('h\n')
                    else:raise ValueError(op)
                extras.append('f Q\n');key_positions.append({'staff':si,'x':x,'y':y,'position':pos})
    # Merge shared chord ledgers at the same time and height.
    ledgers={}
    for n in notes:
        pos=n['target_step'];si=n['staff'];levels=range(10,pos+1,2) if pos>=10 else range(-2,pos-1,-2) if pos<=-2 else []
        for l in levels:
            key=(si,round(n['x'],1),l);ledgers[key]=(n['x']-(1.2 if n['grace'] else 1.8),n['x']+n['width']+(1.2 if n['grace'] else 1.8),staves[si]['bottom']+l*STEP,.48 if n['grace'] else .72)
    for (si,x,l),(x0,x1,y,h) in ledgers.items():
        a=layout(si,x0)[0];b=layout(si,x1)[0]
        extras.append(f'q 0 g {a} {y-h/2} {b-a} {h} re f Q\n')
    cs=ContentStream(None,r);cs.operations=newops;stream=DecodedStreamObject();stream.set_data(cs.get_data()+b'\n'+''.join(extras).encode())
    w=PdfWriter();w.add_page(r.pages[0]);w.pages[0][NameObject('/Contents')]=w._add_object(stream)
    w.add_metadata({'/Title':'万泉河水 - 单簧管 I、II - 降B调','/Subject':'A clarinet to B-flat clarinet, written down one semitone; original page and system layout retained.'})
    DEST.parent.mkdir(parents=True,exist_ok=True)
    with DEST.open('wb') as f:w.write(f)
    # Read final geometry from the saved PDF, not the planned coordinates.
    rr=PdfReader(DEST);outops,outpaths=parse_paths(rr.pages[0],rr)
    assert rr.pages[0].mediabox==r.pages[0].mediabox
    kept=[p for p in paths if p['id'] not in omitted]
    assert len(outpaths)==len(kept)+len(key_positions)+len(ledgers),(len(outpaths),len(kept),len(key_positions),len(ledgers))
    mapping={p['id']:outpaths[i] for i,p in enumerate(kept)}
    for n in notes:
        p=mapping[n['path_id']];cy=sum(p['bbox'][1::2])/2;s=staves[n['staff']]
        step=round((cy-s['bottom'])/STEP);assert step==n['target_step']
        sounding=semi(step)+keyalt(step,n['target_fifths'])
        assert sounding==semi(n['source_step'])+n['source_alter']-1
        n['verified_target_semitone']=sounding
    # Preserve every non-ledger/key shape's full topology and exact expected displacement.
    for p in kept:
        q=mapping[p['id']];assert p['seq']==q['seq'] and p['paint']==q['paint']
        assert abs(q['bbox'][1]-p['bbox'][1]-path_dys[p['id']])<.002
        assert abs(q['bbox'][3]-p['bbox'][3]-path_dys[p['id']])<.002
    show=lambda oo:[(str(a),op) for a,op in oo if op in [b'Tj',b'TJ']]
    assert show(ops)==show(outops),'Changed text/number content'
    assert r.pages[0].extract_text()==rr.pages[0].extract_text(),'Changed extracted annotations'
    def text_positions(sequence):
        state=[1.,1.,0.,0.];stack=[];lm=[1.,0.,0.,1.,0.,0.];result=[];font=None
        for aa,oo in sequence:
            if oo==b'q':stack.append(state[:])
            elif oo==b'Q':state=stack.pop()
            elif oo==b'cm':
                sx,sy,tx,ty=state;state=[sx*float(aa[0]),sy*float(aa[3]),tx+sx*float(aa[4]),ty+sy*float(aa[5])]
            elif oo==b'Tf':font=str(aa[0])
            elif oo==b'Tm':lm=list(map(float,aa))
            elif oo==b'Td':
                dx,dy=map(float,aa);lm[4]+=dx*lm[0]+dy*lm[2];lm[5]+=dx*lm[1]+dy*lm[3]
            elif oo in [b'Tj',b'TJ']:
                sx,sy,tx,ty=state;result.append((font,lm[4]*sx+tx,lm[5]*sy+ty))
        return result
    ta=text_positions(ops);tb=text_positions(outops);assert len(ta)==len(tb)
    fixed_text_count=0
    for a,b in zip(ta,tb):
        assert a[0]==b[0]
        if a[1]<74 or a[2]>735:
            assert abs(a[1]-b[1])<.0001 and abs(a[2]-b[2])<.0001,('Fixed label shifted',a,b)
            fixed_text_count+=1
    assert fixed_text_count>=8
    manifest={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),
       'pages':1,'systems':7,'notes_verified':len(notes),'grace_notes':sum(n['grace'] for n in notes),'source_path_counts':dict(kinds),'text_unchanged':True,
       'fixed_text_runs_verified':fixed_text_count,'visual_review':'pending','notes':notes,'keys':key_positions,'original_staves':staves,
       'paths':[{'id':p['id'],'kind':p['kind'],'staff':p['staff'],'sig':p['sig']} for p in paths]}
    ROOT.joinpath('verification.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ['notes','keys','original_staves','paths']},ensure_ascii=False,indent=2));print(DEST)

if __name__=='__main__':main()
