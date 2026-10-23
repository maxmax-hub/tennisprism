#!/usr/bin/env python3
"""Portable, local-only helpers. The current host Agent supplies all judgments."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import sys
import time

SKILL=Path(__file__).resolve().parents[1]

def output(value):print(json.dumps(value,ensure_ascii=False,indent=2),flush=True)

def workspace(value):
    p=Path(value).expanduser().resolve()
    if p==SKILL or p.is_relative_to(SKILL):raise ValueError('Workspace must be outside the installed skill directory')
    return p

def info(store,r):
    folder=store.path('runs',r['id'])
    return {'run_id':r['id'],'status':r['status'],'target':r['target'],'focus':r['focus'],
            'run_dir':str(folder),'manifest':str(folder/'evidence/manifest.json'),
            'report_json':str(folder/'report.json') if (folder/'report.json').exists() else None,
            'report_markdown':str(folder/'report.md') if (folder/'report.md').exists() else None,
            'prompt':str(folder/'prompt.txt'),'schema':str(SKILL/'scripts/tennis_runtime/report_schema.json'),
            'sheets':[str(folder/'evidence'/s['file']) for s in (r.get('manifest') or {}).get('sheets',[])],
            'detail_requested':r.get('detail_requested',False),'h5_url':r.get('h5_url'),'error':r.get('error')}

def prepare(args):
    from tennis_runtime.main import create_app
    from tennis_runtime.models import RunRequest
    from tennis_runtime.media import probe_video
    app=create_app(workspace(args.workspace));store=app.state.store
    try:
        if args.command=='prepare':
            source=Path(args.video).expanduser().resolve(strict=True)
            probe_video(source)
            if source.suffix.lower() not in {'.mp4','.mov','.m4v','.webm','.mkv','.avi'}:raise ValueError('Unsupported video extension')
            v=store.create('videos',{'filename':source.name,'size_bytes':source.stat().st_size,'status':'preparing','progress':0,'message':'正在生成预览','metadata':None,'preview_url':'','thumbnail_url':'','error':None,'_source_file':'source'+source.suffix.lower()})
            shutil.copy2(source,app.state.source_path(v))
            store.update('videos',v['id'],preview_url=f"/api/videos/{v['id']}/preview",thumbnail_url=f"/api/videos/{v['id']}/thumbnail")
            app.state.prepare_video(v['id']);v=store.get('videos',v['id'])
            if v['status']!='ready':raise ValueError(v['error'])
        else:v=store.get('videos',args.video_id)
        payload=RunRequest(target={'position':args.target,'description':args.description},focus=args.focus,start=args.start,end=args.end,focus_times=args.focus_times,mode='prepare')
        r=app.state.create_run(v['id'],payload)
        app.state.executor.shutdown(wait=True)
        r=store.get('runs',r['id']);output({**info(store,r),'video_id':v['id']})
        if r['status']=='error':return 1
    finally:app.state.executor.shutdown(wait=True)
    return 0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    serve=sub.add_parser('serve');serve.add_argument('--workspace',required=True);serve.add_argument('--port',type=int,default=0)
    for cmd in ['prepare','sample']:
        p=sub.add_parser(cmd);p.add_argument('--workspace',required=True)
        p.add_argument('--video' if cmd=='prepare' else '--video-id',required=True)
        p.add_argument('--target',choices=['near','far','description'],default='near');p.add_argument('--description',default='');p.add_argument('--focus',default='');p.add_argument('--start',type=float,default=0);p.add_argument('--end',type=float);p.add_argument('--focus-times',type=float,nargs='*',default=[])
    p=sub.add_parser('inspect');p.add_argument('--workspace',required=True);p.add_argument('--run',required=True)
    p=sub.add_parser('wait');p.add_argument('--workspace',required=True);p.add_argument('--timeout',type=float,default=25);p.add_argument('--exclude',nargs='*',default=[])
    p=sub.add_parser('submit');p.add_argument('--workspace',required=True);p.add_argument('--run',required=True);p.add_argument('--report',required=True)
    p=sub.add_parser('h5');p.add_argument('--workspace',required=True);p.add_argument('--run',required=True)
    args=parser.parse_args()
    if args.command=='doctor':
        names=['fastapi','uvicorn','av','PIL','imageio_ffmpeg','pydantic']
        deps={n:importlib.util.find_spec(n) is not None for n in names}
        output({'python':sys.version.split()[0],'dependencies':deps,'ready':all(deps.values()),'optional_pose':importlib.util.find_spec('mediapipe') is not None,'requirements':str(SKILL/'scripts/requirements.txt'),'analysis':'current host Agent; requires actual image viewing; no built-in remote model call'})
        return 0 if all(deps.values()) else 1
    if args.command in {'prepare','sample'}:return prepare(args)
    root=workspace(args.workspace)
    if args.command=='serve':
        import uvicorn
        from tennis_runtime.main import create_app
        app=create_app(root)
        sock=socket.socket();sock.bind(('127.0.0.1',args.port));sock.listen(128)
        port=sock.getsockname()[1];url=f'http://127.0.0.1:{port}'
        (root/'server.json').write_text(json.dumps({'url':url,'port':port,'workspace':str(root)},ensure_ascii=False),encoding='utf-8')
        output({'url':url+'/start','workspace':str(root),'analysis':'host Agent; local preparation only'})
        uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning')).run(sockets=[sock]);return 0
    from tennis_runtime.store import Store,now
    store=Store(root)
    if args.command=='wait':
        if not 0<=args.timeout<=50:raise ValueError('timeout must be between 0 and 50 seconds')
        deadline=time.monotonic()+args.timeout
        while True:
            ready=[r for r in store.list('runs') if r['id'] not in args.exclude and (r['status']=='awaiting_report' or (r.get('detail_requested') and not r.get('h5_url')))]
            if ready or time.monotonic()>=deadline:
                output({'status':'ready' if ready else 'waiting','runs':[info(store,r) for r in ready]});return 0
            time.sleep(min(1,max(0,deadline-time.monotonic())))
    r=store.get('runs',args.run)
    if args.command=='inspect':output(info(store,r));return 0
    if args.command=='submit':
        from tennis_runtime import reporting
        if r['status']!='awaiting_report':raise ValueError('Only a prepared, uncompleted run accepts a report')
        report=reporting.validate_report(json.loads(Path(args.report).read_text(encoding='utf-8')),r['manifest'])
        folder=store.path('runs',r['id'])
        with (folder/'report.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        with (folder/'report.md').open('x',encoding='utf-8') as f:f.write(reporting.render_markdown(report))
        r=store.update('runs',r['id'],status='completed',progress=100,report=report,error=None,message='分析已保存',provenance={'method':'host-agent-import','provider':'current-agent','model':'宿主对话分析；工具不验证模型身份','generated_at':now()})
        output(info(store,r));return 0
    if args.command=='h5':
        from tennis_runtime.h5 import build
        output(build(store,r));return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:output({'error':str(exc),'command_failed':True});sys.exit(1)
