"""Host-neutral intake and local report-page generation."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

def attach(app, store, static):
    @app.get('/start')
    def entry():
        return FileResponse(static / 'index.html', headers={'Cache-Control':'no-store'})

    @app.get('/api/entry/pending')
    def pending():
        return {'runs':[r for r in store.list('runs') if r['status']=='awaiting_report' and not r.get('superseded_by')]}

    def generate_h5(identifier):
        from .h5 import build
        try:
            build(store,store.get('runs',identifier))
            store.update('runs',identifier,h5_status='completed',h5_error=None)
        except Exception as exc:
            store.update('runs',identifier,h5_status='error',h5_error=str(exc)[:1200],detail_requested=False)

    @app.post('/api/runs/{identifier}/request-h5')
    def request_h5(identifier: str):
        try:r=store.get('runs',identifier)
        except KeyError:raise HTTPException(404,'找不到任务')
        if r['status']!='completed':raise HTTPException(409,'请先完成初步分析')
        with store.lock:
            r=store.get('runs',identifier)
            if r.get('h5_url') or r.get('h5_status')=='building':return r
            store.update('runs',identifier,detail_requested=True,h5_status='building',h5_error=None)
            app.state.executor.submit(generate_h5,identifier)
        return store.get('runs',identifier)

    @app.get('/reports/{identifier}/{build}/{filename:path}')
    def report_file(identifier:str,build:str,filename:str):
        try:
            run=store.get('runs',identifier)
            if build != run.get('h5_build'):raise KeyError()
            folder=store.path('runs',identifier)/'h5'/build
            allowed=set(run.get('h5_files',[]))
            path=(folder/filename).resolve()
            if filename not in allowed or not path.is_relative_to(folder.resolve()) or not path.is_file():raise KeyError()
        except KeyError:raise HTTPException(404,'找不到报告资源')
        return FileResponse(path,headers={'Cache-Control':'no-store'})
