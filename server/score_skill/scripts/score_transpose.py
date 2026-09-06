"""Inspect a score PDF, or run a hash-bound, reviewed A-to-Bb adapter.
New scores need their own reviewed extraction/adapter. Filename matches are never used.
"""
from pathlib import Path
import argparse, hashlib, importlib, json, shutil, subprocess, sys, tempfile
from pypdf import PdfReader

SKILL=Path(__file__).resolve().parent.parent
def sha256(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def catalog():return json.loads((SKILL/'references'/'known-scores.json').read_text(encoding='utf8'))
def match(path):return next((p for p in catalog() if p['sha256']==sha256(path)),None)

def inspect_score(source,work):
    from vector_paths import parse_paths
    work.mkdir(parents=True,exist_ok=True)
    r=PdfReader(source);report={'source':str(source),'sha256':sha256(source),'pages':len(r.pages),'known_adapter':match(source),'page_details':[]}
    for i,p in enumerate(r.pages):
        fonts={k:{'name':str(f.get_object().get('/BaseFont','')),'subtype':str(f.get_object().get('/Subtype',''))} for k,f in p.get('/Resources',{}).get('/Font',{}).items()}
        detail={'page':i+1,'size':[float(z) for z in p.mediabox],'fonts':fonts,'text':p.extract_text(),'images':sum(v.get_object().get('/Subtype')=='/Image' for v in p.get('/Resources',{}).get('/XObject',{}).values())}
        try:
            ops,paths=parse_paths(p,r)
            detail['path_count']=len(paths)
            (work/f'paths-{i+1}.json').write_text(json.dumps([{k:v for k,v in q.items() if k!='commands'} for q in paths],ensure_ascii=False,indent=2),encoding='utf8')
        except (AssertionError,KeyError,ValueError,TypeError) as error:
            detail['path_parser_limitation']=str(error) or type(error).__name__
        if any('emmentaler' in f['name'].lower() for f in fonts.values()):detail['route']='inspect LilyPond music glyphs'
        elif detail.get('path_count',0)>50:detail['route']='inspect vector outlines and glyphs'
        elif detail['images']:detail['route']='raster/scan: OMR or manual notation reconstruction'
        else:detail['route']='inspect rendered score before choosing an extraction method'
        report['page_details'].append(detail)
    (work/'inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'pages':report['pages'],'known_adapter':report['known_adapter'],'inspection':str(work/'inspection.json'),'routes':[p['route'] for p in report['page_details']]},ensure_ascii=False,indent=2))

def run(source,dest,work,force=False):
    if source.resolve()==dest.resolve():raise ValueError('Input and output must be different files.')
    profile=match(source)
    if profile is None:raise ValueError('No reviewed adapter matches this PDF. Use inspect, then follow SKILL.md and references/new-score.md. Do not reuse another score\'s coordinates.')
    if dest.exists() and not force:raise FileExistsError(f'Output already exists: {dest}; use a new filename or --force for this output only.')
    work.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='score-run-',dir=work) as folder:
        stage=Path(folder);candidate=stage/'candidate.pdf';name=profile['adapter']
        if name=='wanquan':
            subprocess.run([sys.executable,'-X','utf8',str(SKILL/'scripts'/'wanquan_adapter.py'),'--input',str(source),'--output',str(candidate),'--work-dir',str(stage)],check=True)
            verification=json.loads((stage/'verification.json').read_text(encoding='utf8'))
        else:
            module=importlib.import_module(f'{name}_adapter')
            module.SOURCE=source;module.DEST=candidate;module.OUT=stage;module.make()
            verifier=SKILL/'scripts'/f'{name}_verify.py'
            exec(compile(verifier.read_text(encoding='utf8'),str(verifier),'exec'),dict(vars(module)))
            verification=json.loads((stage/'verification-result.json').read_text(encoding='utf8'))
        if verification['notes_verified']!=profile['notes']:raise ValueError('Verified note count differs from the reviewed source inventory.')
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(candidate,dest)
        for audit in stage.glob('*.json'):shutil.copyfile(audit,work/audit.name)
    manifest={'adapter':profile['adapter'],'source_sha256':sha256(source),'output_sha256':sha256(dest),'mode':'A clarinet to B-flat clarinet; sounding pitch preserved',
        'written_semitones':-1,'written_diatonic_steps':-1,'notes_verified':verification['notes_verified'],'visual_review':'pending','output':str(dest)}
    (work/'run-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

def main():
    if not __debug__:raise RuntimeError('Do not use Python -O; verification assertions are required.')
    ap=argparse.ArgumentParser(description=__doc__);sp=ap.add_subparsers(dest='command',required=True)
    a=sp.add_parser('inspect');a.add_argument('input',type=Path);a.add_argument('--work-dir',type=Path,required=True)
    a=sp.add_parser('run');a.add_argument('input',type=Path);a.add_argument('--output',type=Path,required=True);a.add_argument('--work-dir',type=Path,required=True);a.add_argument('--mode',choices=['a-to-bb'],required=True);a.add_argument('--force',action='store_true')
    args=ap.parse_args()
    try:
        source=args.input.resolve(strict=True)
        if args.command=='inspect':inspect_score(source,args.work_dir.resolve())
        else:run(source,args.output.resolve(),args.work_dir.resolve(),args.force)
    except Exception as e:
        print(f'{type(e).__name__}: {e}',file=sys.stderr);return 2
    return 0

if __name__=='__main__':sys.exit(main())
