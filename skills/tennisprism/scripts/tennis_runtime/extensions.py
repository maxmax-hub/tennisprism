"""Host-neutral intake and explicit report-page requests."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

def attach(app, store, static):
    @app.get('/start')
    def entry():
        return FileResponse(static / 'index.html', headers={'Cache-Control':'no-store'})

    @app.get('/api/entry/pending')
    def pending():
        return {'runs':[r for r in store.list('runs') if r['status']=='awaiting_report'
                        or (r.get('detail_requested') and not r.get('h5_url'))]}

    @app.post('/api/runs/{identifier}/request-h5')
    def request_h5(identifier: str):
        try:r=store.get('runs',identifier)
        except KeyError:raise HTTPException(404,'找不到任务')
        if r['status']!='completed':raise HTTPException(409,'请先完成初步分析')
        return store.update('runs',identifier,detail_requested=True)

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
