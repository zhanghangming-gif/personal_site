
source=PdfReader(SOURCE);target=PdfReader(DEST)
assert len(source.pages)==len(target.pages)==3
tot=0;details=[]
for pi,(src,dst) in enumerate(zip(source.pages,target.pages)):
    a=parse(src,source);b=parse(dst,target)
    assert src.mediabox==dst.mediabox
    assert len(a['staves'])==len(b['staves'])
    # Compare every musical glyph whose identity is independent of pitch.
    keep=lambda c:c['glyph'].startswith(('/noteheads','/rests','/flags','/dots','/scripts','/timesig','/clefs')) or c['font'] in ['/R10','/R14','/R33'] or (c['font']=='/R12' and not c['glyph'].startswith('/accidentals'))
    assert Counter((c['font'],c['code']) for c in a['chars'] if keep(c))==Counter((c['font'],c['code']) for c in b['chars'] if keep(c))
    text_a=Counter(c['code'] for c in a['chars'] if c['font']=='/R8')
    text_b=Counter(c['code'] for c in b['chars'] if c['font']=='/R8')
    text_a[76]-=1;text_a[83]+=1;text_a[97]-=1;text_a[105]+=1
    assert text_a==text_b
    pc=0
    for sa,sb in zip(a['staves'],b['staves']):
        si=sa['id'];assert abs(sa['bottom']-sb['bottom'])<.001;assert len(sa['bars'])==len(sb['bars'])
        # Left-side measure numbers must be at exactly the same positions.
        left=lambda d,s:[(c['code'],round(c['x'],4),round(c['y'],4)) for c in d['chars'] if c['staff']==s['id'] and c['font']=='/R8' and c['x']<32]
        assert left(a,sa)==left(b,sb),(pi,si,left(a,sa),left(b,sb))
        ns=sorted([b['chars'][i] for i in sb['notes']],key=lambda c:c['x'])
        originals=sorted([a['chars'][i] for i in sa['notes']],key=lambda c:c['x'])
        assert len(ns)==len(originals)
        original_audit=json.loads(OUT.joinpath('transposition-audit.json').read_text())[pi]['notes']
        expected=sorted([n for n in original_audit if n['staff']==si],key=lambda n:n['x'])
        # Read the output's actual note positions and actual accidentals, including the added double-sharp font.
        acc={};clef=next(c for c in b['chars'] if c['staff']==si and c['glyph']=='/clefs.G')
        kc=5 if pi==0 and si<3 else 1 if pi==0 else 4
        keyxs=[clef['x']+18+i*5.5 for i in range(kc)]
        keys=[]
        for c in b['chars']:
            if c['staff']!=si or not c['glyph'].startswith('/accidentals'):continue
            if c['size']<18:continue # Instrument-name flat, above the staff.
            if any(abs(c['x']-xx)<.01 for xx in keyxs):keys.append(c);continue
            if pi==0 and si==2 and c['x']>530:continue
            if pi==0 and si==6 and 299<c['x']<322:continue
            candidates=[n for n in ns if 0<n['x']-c['x']<17 and abs(n['y']-c['y'])<.06]
            assert candidates,(pi,si,'orphan output accidental',c)
            n=min(candidates,key=lambda n:n['x']-c['x']);assert n['id'] not in acc
            acc[n['id']]=c
        assert len(keys)==kc,(pi,si,'key count',len(keys),kc)
        assert all(c['glyph']=='/accidentals.sharp' for c in keys)
        bar=None;state={}
        for n,orig,want in zip(ns,originals,expected):
            assert n['glyph']==orig['glyph'] and n['font']==orig['font']
            assert n['pitch']==orig['pitch']-1,(pi,si,'staff pitch',n,orig)
            bi=sum(x<n['x'] for x in sb['bars'])
            if bi!=bar:state={};bar=bi
            sharps='FCGD' if pi==0 and si==6 and n['x']>294 else 'FCGDA'[:kc]
            alt=state.get(n['pitch'],1 if pitchname(n['pitch'])[0] in sharps else 0)
            if n['id'] in acc:alt={'/accidentals.flat':-1,'/accidentals.natural':0,'/accidentals.sharp':1,'/accidentals.doublesharp':2}[acc[n['id']]['glyph']]
            state[n['pitch']]=alt
            assert semi(n['pitch'])+alt==want['source_semitone']-1,(pi,si,'wrong sounding pitch',n,want,alt)
            pc+=1
    tot+=pc;details.append({'page':pi+1,'systems':len(a['staves']),'notes_verified':pc,'same_rhythmic_glyphs':True,'same_left_numbers':True,'same_page_size':True})
assert tot==696
OUT.joinpath('verification-result.json').write_text(json.dumps({'notes_verified':tot,'pages':details},indent=2),encoding='utf8')
print(json.dumps({'notes_verified':tot,'pages':details},indent=2))
