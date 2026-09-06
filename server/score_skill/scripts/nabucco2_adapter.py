from score_pdf import *
from pypdf import PdfWriter
from pypdf.generic import FloatObject, NumberObject, ByteStringObject, NameObject, DecodedStreamObject, DictionaryObject, ArrayObject
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from io import BytesIO

SOURCE=None
OUT=None
DEST=None
BASE_OUT=Path(__file__).resolve().parent.parent/'assets'
NATURAL=[4,5,7,9,11,12,14] # semitones from C4, for staff E4..D5
def semi(step):
    return NATURAL[step%7]+12*(step//7)
def base_alter(step,key):
    letter=pitchname(step)[0]
    return -1 if letter in ('BEAD' if key==4 else 'B' if key==1 else '') else 0

font=TTFont(BASE_OUT/'Bravura.otf')
gs=font.getGlyphSet(); pen=RecordingPen();gs[font.getBestCmap()[0xE263]].draw(pen)
DOUBLE=pen.value
DOUBLE_WIDTH=gs[font.getBestCmap()[0xE263]].width*19.9253/font['head'].unitsPerEm

def double_font(writer):
    bounds=BoundsPen(gs);gs[font.getBestCmap()[0xE263]].draw(bounds)
    width=gs[font.getBestCmap()[0xE263]].width
    data=[f'{width} 0 '+ ' '.join(map(str,bounds.bounds))+' d1\n']
    for op,pts in DOUBLE:
        if op=='moveTo':data.append(f'{pts[0][0]} {pts[0][1]} m\n')
        elif op=='lineTo':data.append(f'{pts[0][0]} {pts[0][1]} l\n')
        elif op=='curveTo':data.append(' '.join(str(z) for pt in pts for z in pt)+' c\n')
        elif op=='closePath':data.append('h\n')
        else:raise ValueError(op)
    data.append('f\n');proc=DecodedStreamObject();proc.set_data(''.join(data).encode('ascii'))
    obj=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type3'),
        NameObject('/Name'):NameObject('/RDouble'),NameObject('/FontBBox'):ArrayObject(list(map(FloatObject,bounds.bounds))),
        NameObject('/FontMatrix'):ArrayObject(list(map(FloatObject,[1/font['head'].unitsPerEm,0,0,1/font['head'].unitsPerEm,0,0]))),
        NameObject('/CharProcs'):DictionaryObject({NameObject('/accidentals.doublesharp'):writer._add_object(proc)}),
        NameObject('/Encoding'):DictionaryObject({NameObject('/Type'):NameObject('/Encoding'),NameObject('/Differences'):ArrayObject([NumberObject(0),NameObject('/accidentals.doublesharp')])}),
        NameObject('/FirstChar'):NumberObject(0),NameObject('/LastChar'):NumberObject(0),NameObject('/Widths'):ArrayObject([NumberObject(width)]),NameObject('/Resources'):DictionaryObject()})
    return writer._add_object(obj)

def make():
    reader=PdfReader(SOURCE); writer=PdfWriter(); report=[];dfont=double_font(writer)
    for pi,page in enumerate(reader.pages):
        d=parse(page,reader); chars=d['chars']; paths=d['paths']; staves=d['staves']; ops=d['ops']
        omit=set(); changes={}; extras=[]; audit=[]
        for s in staves:
            si=s['id']; sc=[c for c in chars if c['staff']==si]
            clef=next(c for c in sc if c['glyph']=='/clefs.G')
            src_key=0 if pi==0 and si<3 else 4 if pi==0 else 1
            target_count={0:5,4:1,1:4}[src_key]
            s['src_key']=src_key;s['target_count']=target_count
            s['keyx']=clef['x']+18.0
            s['map_start']=clef['x']+16.8 if src_key==0 else clef['x']+26.0 if src_key==1 else clef['x']+47.0
            s['delta']=31.8 if src_key==0 else 17.0 if src_key==1 else 0.0
            s['ratio']=1-s['delta']/(s['x1']-s['map_start'])
            # Existing key signatures are identified by their position and the known source sections.
            keychars=[c for c in sc if c['glyph']=='/accidentals.flat' and (src_key and 49<c['x']<(66 if src_key==4 else 54))]
            assert len(keychars)==src_key,(pi,si,keychars)
            omit.update(c['id'] for c in keychars)
            # The end-of-line courtesy key before bar 54 and the key change at C.
            if pi==0 and si==2:
                courtesy=[c for c in sc if c['glyph'].startswith('/accidentals') and c['x']>530]
                assert len(courtesy)==4;omit.update(c['id'] for c in courtesy)
                extras.append(('key',s,533.66,1))
            if pi==0 and si==6:
                cancels=[c for c in sc if c['glyph'].startswith('/accidentals') and 299<c['x']<320]
                assert len(cancels)==4;omit.update(c['id'] for c in cancels)
                extras.append(('key',s,300.0,4))
            extras.append(('key',s,s['keyx'],target_count))
            # Attach every printed accidental to the note it modifies.
            ns=sorted([chars[i] for i in s['notes']],key=lambda c:c['x'])
            acc={}
            for c in sc:
                if not c['glyph'].startswith('/accidentals') or c['id'] in omit:continue
                candidates=[n for n in ns if 0<n['x']-c['x']<17 and abs(n['y']-c['y'])<0.06]
                assert candidates,(pi,si,c)
                n=min(candidates,key=lambda n:n['x']-c['x'])
                assert n['id'] not in acc
                acc[n['id']]=c
            bar=None;state={}
            for n in ns:
                bar_idx=sum(x<n['x'] for x in s['bars'])
                if bar_idx!=bar:state={};bar=bar_idx
                key=1 if pi==0 and si==6 and n['x']>294 else src_key
                a=acc.get(n['id'])
                alteration=state.get(n['pitch'],base_alter(n['pitch'],key))
                if a:alteration={'/accidentals.flat':-1,'/accidentals.natural':0,'/accidentals.sharp':1}[a['glyph']]
                state[n['pitch']]=alteration
                target_pitch=n['pitch']-1
                target_alter=semi(n['pitch'])+alteration-1-semi(target_pitch)
                assert target_alter in [-1,0,1,2]
                changes[n['id']]={'dy':-s['step']}
                audit.append({'id':n['id'],'staff':si,'bar_index':bar,'x':n['x'],'source_step':n['pitch'],'source_alter':alteration,
                              'target_step':target_pitch,'target_alter':target_alter,'accidental':a['id'] if a else None,
                              'source':pitchname(n['pitch'],alteration),'target':pitchname(target_pitch,target_alter),
                              'source_semitone':semi(n['pitch'])+alteration,'target_semitone':semi(target_pitch)+target_alter})
                if a:
                    if target_alter==2:
                        omit.add(a['id']); extras.append(('double',s,a['x']+a['width']-DOUBLE_WIDTH,a['y']-s['step']))
                    else:
                        code={-1:3,0:15,1:17}[target_alter]
                        f=page['/Resources']['/Font'][a['font']]
                        nw=float(f['/Widths'][code-int(f['/FirstChar'])])*a['size']/1000*a['sx']
                        changes[a['id']]={'dy':-s['step'],'dx':a['width']-nw,'code':code}
            for c in sc:
                if c['glyph'].startswith('/flags.'):
                    changes[c['id']]={'dy':-s['step']}
                elif c['glyph']=='/dots.dot':
                    if pi==2 and si==13 and 218<c['x']<406:
                        continue # The two dots in each one-bar repeat sign are not augmentation dots.
                    candidates=[n for n in ns if 3<n['x'].__rsub__(c['x'])<20 and -0.1<c['y']-n['y']<s['step']+0.1]
                    assert candidates,(pi,si,'dot',c)
                    n=max(candidates,key=lambda n:n['x'])
                    newpos=n['pitch']-1
                    # Augmentation dots remain in staff spaces.
                    y=s['bottom']+(newpos+(1 if newpos%2==0 else 0))*s['step']
                    changes[c['id']]={'dy':y-c['y']}
                elif c['glyph'] in ['/scripts.staccato','/scripts.sforzato']:
                    n=min(ns,key=lambda n:abs(n['x']+n['width']/2-c['x']))
                    assert abs(n['x']+n['width']/2-c['x'])<3.1,(pi,si,'articulation',c,n)
                    if c['y']<n['y']:
                        dy=-2*s['step'] if c['glyph']=='/scripts.staccato' and s['bottom']-0.1<c['y']<s['top']+0.1 else -s['step']
                        changes[c['id']]={'dy':dy}
                elif c['font']=='/R14' and c['code']==51 and c['size']<11:
                    changes[c['id']]={'dy':-s['step']}
            # New ledger lines from actual resulting staff positions.
            for n in ns:
                pp=n['pitch']-1
                ledger=list(range(10,pp+1,2)) if pp>=10 else list(range(-2,pp-1,-2)) if pp<=-2 else []
                for pos in ledger:extras.append(('ledger',s,n['x']-1.15,n['x']+n['width']+1.15,s['bottom']+pos*s['step']))
        def layout(s,x):
            if x<s['map_start']:return x,1.
            return s['map_start']+s['delta']+(x-s['map_start'])*s['ratio'],s['ratio']
        # Keep the original font and replace the two instrument-name characters with Si-flat.
        header=[c for c in chars if c['font']=='/R8' and c['y']>750 and c['glyph'] not in [' ']]
        # Work from complete same-baseline groups, so page numbers cannot be mistaken for labels.
        groups=defaultdict(list)
        for c in chars:
            if c['font']=='/R8':groups[round(c['y'],2)].append(c)
        for yy,cc in groups.items():
            cc=sorted(cc,key=lambda c:c['x']);word=''.join(c['glyph'] for c in cc)
            at=word.find('Clarinette 2 en La')
            if at>=0:
                L=cc[at+16];a=cc[at+17]
                assert L['code']==76 and a['code']==97
                changes[L['id']]={'code':83,'header':True};changes[a['id']]={'code':105,'header':True}
                extras.append(('headerflat',a['x']+a['size']*.315+0.35,a['y']+1.2))
        if pi==2:
            for c in chars:
                if c['font']=='/R10' and c['code']==70 and 45<c['x']<62 and c['y']>780:
                    changes[c['id']]={'dx':33.0,'fixed_x':True}
        # Rewrite each original path, preserving all barlines, rests, rehearsal boxes, hairpins and logos.
        replacement={};path_counts=Counter()
        stem_x=defaultdict(list)
        for p in paths:
            x0,y0,x1,y1=p['bbox'];w=x1-x0;h=y1-y0
            s=min(staves,key=lambda s:abs((y0+y1)/2-(s['bottom']+s['top'])/2))
            typ='other'
            if p['id'] in s['lines']:typ='staff'
            elif p['commands'][0][1]==b're' and abs(w-.249)<.015 and h>4:typ='stem'
            elif abs(w)<.005 and 4<h<20 and len(p['commands'])==2:
                ns=[chars[i] for i in s['notes']]
                for n in ns:
                    if abs(x0-(n['x']+n['width']-.25))<.5 and min(abs(y0-n['y']),abs(y1-n['y']))<.5:
                        typ='stem';break
            if typ=='stem':stem_x[s['id']].append((x0,y0,y1))
            p['staff']=s['id'];p['kind']=typ
        for p in paths:
            x0,y0,x1,y1=p['bbox'];w=x1-x0;h=y1-y0;s=staves[p['staff']];typ=p['kind']
            near_score=s['bottom']-28<(y0+y1)/2<s['top']+32
            if not near_score or p['paint']=='n' or typ=='staff':continue
            cmdtypes=[a[1] for a in p['commands']]
            if typ=='other':
                if b'c' in cmdtypes:typ='slur'
                elif cmdtypes[0]==b're' and abs(h-1.9925)<.02 and w>1:typ='beam'
                elif cmdtypes in [[b'm',b'l',b'l',b'l',b'h'],[b'm',b'l',b'l',b'l']]:
                    sx=stem_x[s['id']]
                    if abs(h-1.9925)<.02 or (any(abs(a-x0)<.4 for a,b,c in sx) and any(abs(a-x1)<.4 or abs(a+.249-x1)<.4 for a,b,c in sx)):typ='beam'
                elif len(cmdtypes)==2 and h<.005 and 5<w<20 and abs(p['lw']-.996)<.05:
                    typ='ledger'
                elif len(cmdtypes)==3 and cmdtypes==[b'm',b'l',b'l'] and h<4:
                    # Tuplet brackets have short vertical hooks.
                    nums=[c for c in chars if c['staff']==s['id'] and c['font']=='/R14' and c['code']==51]
                    if any(abs(c['y']-y0)<7 and x0-25<c['x']<x1+25 for c in nums):typ='tuplet'
                elif pi==2 and s['id']==1 and p['id'] in [104,105,106,107]:
                    typ='tuplet'
            p['kind']=typ;path_counts[typ]+=1
            if typ=='ledger':
                for ii,oo,aa,ss in p['commands']:replacement[ii]=[]
                replacement[p['op']]=[]
                continue
            dy=-s['step'] if typ in ['stem','beam','slur','tuplet'] else 0.
            rehearsal_f=pi==2 and s['id']==0 and 47<x0<=x1<62 and y0>780
            for ii,oo,aa,ss in p['commands']:
                if oo==b'h':continue
                bb=list(map(float,aa))
                def xy(x,y):
                    xx=x*ss['sx']+ss['tx'];yy=y*ss['sy']+ss['ty']
                    xx=xx+33.0 if rehearsal_f else layout(s,xx)[0]
                    return [(xx-ss['tx'])/ss['sx'],(yy+dy-ss['ty'])/ss['sy']]
                if oo==b're':
                    q0=xy(bb[0],bb[1]);q1=xy(bb[0]+bb[2],bb[1]+bb[3])
                    bb=q0+[q1[0]-q0[0],q1[1]-q0[1]]
                else:bb=[v for pair in zip(bb[::2],bb[1::2]) for v in xy(*pair)]
                replacement[ii]=[(list(map(FloatObject,bb)),oo)]
        # Text is emitted one glyph at a time at its measured source position.
        byop=defaultdict(list)
        for c in chars:byop[c['op']].append(c)
        for oi,cc in byop.items():
            out=[]
            for c in cc:
                if c['id'] in omit:continue
                s=staves[c['staff']];ch=changes.get(c['id'],{});x=c['x']+ch.get('dx',0);y=c['y']+ch.get('dy',0)
                ratio=1.
                is_score=s['bottom']-30<c['y']<s['top']+33 and c['glyph']!='/clefs.G'
                if is_score and not ch.get('fixed_x'):
                    # A word beginning to the left of the key area stays intact.
                    text_word=not any(q['glyph'].startswith('/') for q in cc)
                    if not text_word or min(q['x'] for q in cc)>=s['map_start']:
                        x,ratio=layout(s,x)
                out.extend([([FloatObject(ratio),NumberObject(0),NumberObject(0),NumberObject(1),FloatObject(x/c['sx']),FloatObject(y/c['sy'])],b'Tm'),
                            ([ByteStringObject(bytes([ch.get('code',c['code'])]))],b'Tj')])
            replacement[oi]=out
        newops=[]
        for oi,item in enumerate(ops):newops.extend(replacement.get(oi,[item]))
        cs=ContentStream(None,reader);cs.operations=newops
        appended=[]
        def glyph(code,size,x,y,ratio=1):
            appended.append(f'q BT /R12 {size:.7f} Tf {ratio:.7f} 0 0 1 {x:.7f} {y:.7f} Tm <{code:02x}> Tj ET Q\n')
        for e in extras:
            typ=e[0]
            if typ=='key':
                _,s,x,count=e
                # Mid-system key C fits in its original cancellation area.
                for i,step in enumerate([8,5,9,6,3][:count]):
                    xx=layout(s,x+i*5.5)[0] if x>100 and not (pi==0 and s['id']==0) else x+i*5.5
                    glyph(17,19.9253,xx,s['bottom']+step*s['step'])
            elif typ=='headerflat':glyph(3,12,e[1],e[2])
            elif typ=='ledger':
                _,s,x0,x1,y=e;x0=layout(s,x0)[0];x1=layout(s,x1)[0]
                appended.append(f'q 0 G .99625 w 0 J {x0:.7f} {y:.7f} m {x1:.7f} {y:.7f} l S Q\n')
            elif typ=='double':
                _,s,x,y=e;x,ratio=layout(s,x)
                appended.append(f'q BT /RDouble 19.9253 Tf {ratio:.7f} 0 0 1 {x:.7f} {y:.7f} Tm <00> Tj ET Q\n')
        stream=DecodedStreamObject();stream.set_data(cs.get_data()+b'\n'+''.join(appended).encode('ascii'))
        writer.add_page(page);writer.pages[-1][NameObject('/Contents')]=writer._add_object(stream)
        writer.pages[-1]['/Resources']['/Font'][NameObject('/RDouble')]=dfont
        report.append({'page':pi+1,'note_count':len(audit),'original_glyph_counts':dict(Counter(c['glyph'] for c in chars)),
                       'notes':audit,'path_counts':dict(path_counts),'double_sharps':sum(e[0]=='double' for e in extras),
                       'ledger_lines':sum(e[0]=='ledger' for e in extras),'staff_count':len(staves)})
        print('PAGE',pi+1,'notes',len(audit),'double_sharps',report[-1]['double_sharps'],'paths',path_counts)
        # Retain path classifications for a geometry audit.
        OUT.joinpath(f'path-audit-{pi+1}.json').write_text(json.dumps([{k:v for k,v in p.items() if k!='commands'} for p in paths],indent=2),encoding='utf8')
    writer.add_metadata({'/Title':'NABUCCO - Sinfonia - Clarinette 2 en Si bemol','/Subject':'Clarinet in A part transposed down one semitone for clarinet in B-flat; original systems and page numbers retained.'})
    with DEST.open('wb') as f:writer.write(f)
    OUT.joinpath('transposition-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('OUTPUT',DEST)

