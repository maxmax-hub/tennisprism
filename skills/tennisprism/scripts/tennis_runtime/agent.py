"""Short, explicit leases for a host Agent that is actively running this task.

This is a local task mailbox, not an inference service or a chat wake-up API.
Browser polling never renews the lease. All state expires on server restart.
"""
import asyncio
import threading
import time

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


class WaitRequest(BaseModel):
    timeout: float = Field(default=25, ge=0, le=50)
    exclude: list[str] = Field(default_factory=list, max_length=200)


class HeartbeatRequest(BaseModel):
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class Connection:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.phase = 'offline'
        self.run_id = None
        self.expires_at = 0
        self.waiting = False
        self.epoch = 0

    def status(self):
        with self.lock:
            phase = self.phase
            if self.run_id:
                try:
                    run = self.store.get('runs', self.run_id)
                    if run['status'] in {'completed', 'error'} or run.get('superseded_by'):
                        phase = 'finished'
                except KeyError:
                    phase = 'offline'
            connected = time.monotonic() < self.expires_at and phase in {'waiting', 'reviewing'}
            return {'connected': connected, 'can_submit': connected and phase == 'waiting',
                    'phase': phase if connected else 'offline', 'run_id': self.run_id,
                    'lease_seconds': max(0, int(self.expires_at-time.monotonic())) if connected else 0}

    def require_listener(self):
        if not self.status()['can_submit']:
            raise HTTPException(409, '分析端尚未就绪或正在处理另一段视频。请等待连接恢复；已选视频会保留。')

    def touch(self, run_id):
        with self.lock:
            try:
                run = self.store.get('runs', run_id)
            except KeyError:
                raise HTTPException(404, '找不到任务')
            if run['status'] != 'awaiting_report' or run.get('superseded_by'):
                raise HTTPException(409, '该任务不在等待分析')
            status = self.status()
            if status['connected'] and self.phase == 'reviewing' and self.run_id != run_id:
                raise HTTPException(409, '请先完成已接收的任务')
            self.phase, self.run_id = 'reviewing', run_id
            self.expires_at = time.monotonic()+180
            return self.status()


def attach(app, store):
    agent = app.state.agent = Connection(store)

    @app.get('/api/agent/status')
    def status():
        return agent.status()

    @app.post('/api/agent/heartbeat')
    def heartbeat(payload: HeartbeatRequest):
        return agent.touch(payload.run_id)

    @app.post('/api/agent/disconnect')
    def disconnect():
        with agent.lock:
            agent.epoch += 1
            agent.expires_at = 0
            agent.phase = 'offline'
        return agent.status()

    @app.post('/api/agent/wait')
    async def wait(payload: WaitRequest, request: Request):
        with agent.lock:
            status = agent.status()
            if agent.waiting or (status['connected'] and status['phase'] == 'reviewing'):
                raise HTTPException(409, '已有 Agent 等待或正在复盘，请先完成当前任务')
            agent.waiting = True
            agent.phase, agent.run_id = 'waiting', None
            agent.expires_at = time.monotonic()+payload.timeout+45
            epoch = agent.epoch
        deadline = time.monotonic()+payload.timeout
        try:
            while True:
                if epoch != agent.epoch or await request.is_disconnected():
                    agent.expires_at = 0
                    return {'status': 'disconnected', 'runs': []}
                ready = [r for r in reversed(store.list('runs')) if r['id'] not in payload.exclude
                         and r['status'] == 'awaiting_report' and not r.get('superseded_by')]
                if ready:
                    run = ready[0]
                    agent.touch(run['id'])
                    return {'status': 'ready', 'runs': [run],
                            'next_action': 'View the real images, write and submit the report. Renew heartbeat while reviewing; do not ask the user to return to chat.'}
                if time.monotonic() >= deadline:
                    agent.expires_at = time.monotonic()+45
                    return {'status': 'waiting', 'runs': [],
                            'next_action': 'Call wait again now. This tool timeout is not task completion; keep the host turn active until submission, cancellation or a real host limit.'}
                await asyncio.sleep(min(.5, max(0, deadline-time.monotonic())))
        finally:
            agent.waiting = False
