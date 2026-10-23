"""Build a private, portable report from validated real evidence."""
import hashlib
import json
import shutil
import uuid
import math
from pathlib import Path
import av
from . import reporting

SKILL=Path(__file__).resolve().parents[2]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def build(store,run):
    if run['status']!='completed' or not run.get('report'):raise ValueError('A validated report is required first')
    report=reporting.validate_report(run['report'],run['manifest'])
    folder=store.path('runs',run['id']);video=store.get('videos',run['video_id'])
    preview=store.path('videos',video['id'])/'media/preview.mp4'
    with av.open(str(preview)) as c:
        stream=c.streams.video[0];origin=float(stream.start_time*stream.time_base) if stream.start_time else 0
        stamps=[float(f.pts*f.time_base)-origin for f in c.decode(stream) if f.pts is not None]
        width,height=stream.codec_context.width,stream.codec_context.height
    if not stamps:raise ValueError('No decodable preview frames')
    pose={'frames':[],'notes':['未运行姿态模型；不显示骨架或自动跟随。']}
    if (folder/'pose.json').exists():
        pose=json.loads((folder/'pose.json').read_text(encoding='utf-8'))
        if pose.get('preview_sha256')!=sha(preview) or pose.get('target')!=run['target'] or not pose.get('reviewed'):
            raise ValueError('Pose must match the preview and target and be visually reviewed')
        rows=pose.get('frames',[])
        if len(rows)!=len(stamps) or any(not math.isfinite(row['time']) or abs(row['time']-t)>.001 for row,t in zip(rows,stamps)):
            raise ValueError('Pose timestamps must match decoded preview frames')
        for row in rows:
            pts=row.get('landmarks')
            if pts is not None and (len(pts)!=33 or any(len(p)!=4 or not all(math.isfinite(x) for x in p) for p in pts)):
                raise ValueError('Invalid pose landmark data')
    build_id=uuid.uuid4().hex[:12];out=folder/'h5'/build_id;out.mkdir(parents=True)
    for name in ['index.html','style.css','app.js']:shutil.copy2(SKILL/'assets/report'/name,out/name)
    (out/'evidence').mkdir();shutil.copy2(preview,out/'preview.mp4')
    lookup={f['id']:f for f in run['manifest']['frames']}
    events=[]
    for i,finding in enumerate(report['strengths']+report['priorities']):
        e=finding['evidence'][0];frame=lookup[e['frame_id']]
        for ref in finding['evidence']:
            actual=lookup[ref['frame_id']];shutil.copy2(folder/'evidence'/actual['file'],out/'evidence'/actual['file'])
        events.append({'id':str(i),'time':e['timestamp'],'frame_id':e['frame_id'],'image':'evidence/'+frame['file'],'title':finding['title'],'observation':finding['observation'],'interpretation':finding['interpretation'],'kind':finding.get('kind','strength'),'confidence':finding['confidence']})
    data={'report':report,'events':events,'evidence':{k:{**f,'image':'evidence/'+f['file']} for k,f in lookup.items()},'timestamps':stamps,'video':{'filename':video['filename'],'duration':video['metadata']['duration'],'width':width,'height':height},'pose':pose,'provenance':run.get('provenance',{})}
    (out/'data.js').write_text('window.TENNIS_REPORT='+json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')+';\n',encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    files=[p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()]
    url=f"/reports/{run['id']}/{build_id}/index.html"
    store.update('runs',run['id'],h5_build=build_id,h5_files=files,h5_url=url,detail_requested=False)
    base=json.loads((store.root/'server.json').read_text()).get('url','') if (store.root/'server.json').exists() else ''
    return {'directory':str(out),'url':base+url if base else None,'start_server_if_url_missing':not bool(base),'private_media_included':True,'pose_reviewed':bool(pose.get('reviewed'))}
