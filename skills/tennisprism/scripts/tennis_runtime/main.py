"""Local-only video review and provider-independent analysis API."""
import hmac
import io
import json
import logging
import math
import os
import secrets
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import media, reporting
from .models import RunRequest
from .store import Store, now

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "assets" / "entry"
logger = logging.getLogger("tennisai")
UPLOAD_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def create_app(data_dir: Path | None = None) -> FastAPI:
    if data_dir is None or Path(data_dir).resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Choose a workspace outside the installed skill directory")
    store = Store(Path(data_dir))
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tennisai")
    csrf_token = secrets.token_urlsafe(32)
    max_upload = int(os.environ.get("TENNISAI_MAX_UPLOAD_BYTES", str(4 * 1024**3)))

    @asynccontextmanager
    async def lifespan(app):
        store.recover_interrupted()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="TennisAI", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.executor = executor
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, exc):
        # Pydantic's original input may contain the plaintext API key, including
        # when an unrelated model-level time-window validator rejects a request.
        messages = [error.get("msg", "输入无效") for error in exc.errors()]
        return JSONResponse({"detail": ("输入格式无效：" + "；".join(messages))[:1200]}, status_code=422)

    @app.middleware("http")
    async def local_mutation_guard(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.headers.get("x-tennisai-token", "")
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if not hmac.compare_digest(token, csrf_token) or (origin and origin != expected):
                return JSONResponse({"detail": "请求来源无效，请刷新本地页面后重试"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path == "/" or request.url.path.startswith("/entry-assets/"):
            # Local updates keep these asset URLs stable; avoid combining an
            # older cached page/style with a newer script after app changes.
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    def get(kind, identifier):
        try:
            return store.get(kind, identifier)
        except KeyError:
            raise HTTPException(404, "找不到这条记录")

    def public_video(record):
        return {key: value for key, value in record.items() if not key.startswith("_")}

    def source_path(video):
        return store.path("videos", video["id"]) / video["_source_file"]

    def progress(kind, identifier, phase, offset=0, scale=1):
        def update(value, message):
            store.update(kind, identifier, status=phase, progress=min(99, max(0, int(offset + value * scale))), message=str(message))
        return update

    def prepare_video(identifier):
        try:
            record = store.get("videos", identifier)
            metadata = media.prepare_video(source_path(record), store.path("videos", identifier) / "media", progress("videos", identifier, "preparing"))
            store.update("videos", identifier, status="ready", progress=100, message="视频已就绪", metadata=metadata, error=None)
        except Exception as exc:
            store.update("videos", identifier, status="error", message="视频处理失败", error=str(exc)[:1200])

    def run_analysis(identifier, config, mode):
        secret = config.get("api_key", "")
        try:
            run = store.get("runs", identifier)
            video = store.get("videos", run["video_id"])
            folder = store.path("runs", identifier)
            evidence_dir = folder / "evidence"
            manifest = media.prepare_evidence(source_path(video), evidence_dir, start=run["window"]["start"], end=run["window"]["end"], focus_times=run["focus_times"], progress=progress("runs", identifier, "preparing", scale=0.45))
            prompt = reporting.build_prompt(manifest, run["target"], run["focus"])
            (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
            store.update("runs", identifier, manifest=manifest, window=manifest["window"])
            if mode == "prepare":
                store.update("runs", identifier, status="awaiting_report", progress=100, message="证据包已就绪，可交给当前 Agent 对话分析，再导入报告")
                return
            raise ValueError("Analysis is performed by the current host Agent; use prepare mode")
        except Exception as exc:
            message = str(exc)
            if secret:
                message = message.replace(secret, "[已隐藏]")
            store.update("runs", identifier, status="error", message="分析未完成", error=message[:1600])
        finally:
            config.pop("api_key", None)

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"version": "0.1.0", "csrf_token": csrf_token, "providers": [{"kind":"agent","label":"当前 Agent","available":True,"message":"通过当前对话分析"}], "videos": [public_video(v) for v in store.list("videos")]}

    @app.get("/api/videos")
    def list_videos():
        return {"videos": [public_video(v) for v in store.list("videos")]}

    @app.post("/api/videos", status_code=202)
    async def upload_video(request: Request, filename: str):
        filename = filename.replace("\\", "/").split("/")[-1].strip()
        suffix = Path(filename).suffix.lower()
        if not filename or len(filename) > 255 or suffix not in UPLOAD_EXTENSIONS:
            raise HTTPException(400, "请选择 MP4、MOV、M4V、WebM、MKV 或 AVI 视频")
        if request.headers.get("content-type", "").startswith("multipart/"):
            raise HTTPException(415, "请直接上传视频文件内容")
        try:
            declared_size = int(request.headers.get("content-length", "0"))
        except ValueError:
            raise HTTPException(400, "文件长度无效")
        if declared_size > max_upload:
            raise HTTPException(413, f"文件超过本机当前上传上限（{max_upload // 1024**3} GB），可在启动配置中调整")
        record = store.create("videos", {"filename": filename, "size_bytes": 0, "status": "preparing", "progress": 0, "message": "正在接收视频", "metadata": None, "preview_url": "", "thumbnail_url": "", "error": None, "_source_file": "source" + suffix})
        identifier = record["id"]
        store.update("videos", identifier, preview_url=f"/api/videos/{identifier}/preview", thumbnail_url=f"/api/videos/{identifier}/thumbnail")
        total = 0
        try:
            with source_path(record).open("xb") as destination:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > max_upload:
                        raise HTTPException(413, "视频超过当前上传上限，已接收部分保留在本机")
                    destination.write(chunk)
            if total == 0:
                raise HTTPException(400, "视频文件为空")
            store.update("videos", identifier, size_bytes=total, message="正在检查视频并生成预览")
        except Exception as exc:
            store.update("videos", identifier, size_bytes=total, status="error", message="上传未完成", error=str(getattr(exc, "detail", exc))[:1000])
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(400, "上传中断，可重新选择文件上传")
        executor.submit(prepare_video, identifier)
        return public_video(store.get("videos", identifier))

    @app.get("/api/videos/{identifier}")
    def video_record(identifier: str):
        return public_video(get("videos", identifier))

    @app.get("/api/videos/{identifier}/preview")
    def video_preview(identifier: str):
        record = get("videos", identifier)
        path = store.path("videos", identifier) / "media" / "preview.mp4"
        if record["status"] != "ready" or not path.is_file():
            raise HTTPException(409, "视频预览尚未就绪")
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/videos/{identifier}/thumbnail")
    def video_thumbnail(identifier: str):
        get("videos", identifier)
        path = store.path("videos", identifier) / "media" / "thumbnail.jpg"
        if not path.is_file():
            raise HTTPException(404, "缩略图尚未就绪")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/videos/{identifier}/runs", status_code=202)
    def create_run(identifier: str, payload: RunRequest):
        video = get("videos", identifier)
        if video["status"] != "ready":
            raise HTTPException(409, "请等待视频准备完成")
        duration = video["metadata"]["duration"]
        end = payload.end if payload.end is not None else duration
        if payload.start >= duration or end > duration + 0.1 or any(not math.isfinite(t) or t >= end for t in payload.focus_times):
            raise HTTPException(400, "分析时间范围超出了视频长度")
        if payload.mode != "prepare":
            raise HTTPException(400, "请由当前 Agent 分析整理后的画面；此服务不调用模型 API")
        active = [r for r in store.list("runs") if r["status"] in {"queued", "preparing", "analyzing"}]
        if len(active) >= 4:
            raise HTTPException(429, "已有较多任务在运行，请稍后再试")
        record = store.create("runs", {"video_id": identifier, "status": "queued", "progress": 0, "message": "等待准备视频证据", "error": None, "provider": payload.provider.public(), "target": payload.target.model_dump(), "focus": payload.focus, "window": {"start": payload.start, "end": min(end, duration)}, "focus_times": payload.focus_times, "manifest": None, "report": None, "provenance": None})
        executor.submit(run_analysis, record["id"], payload.provider.runtime(), payload.mode)
        return record

    @app.get("/api/videos/{identifier}/runs")
    def video_runs(identifier: str):
        get("videos", identifier)
        return {"runs": [r for r in store.list("runs") if r["video_id"] == identifier]}

    @app.get("/api/runs/{identifier}")
    def run_record(identifier: str):
        return get("runs", identifier)

    def approved_evidence_path(run, filename):
        manifest = run.get("manifest") or {}
        approved = {entry["file"] for entry in manifest.get("frames", []) + manifest.get("sheets", [])}
        if filename not in approved:
            raise HTTPException(404, "找不到这张证据画面")
        directory = store.path("runs", run["id"]) / "evidence"
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise HTTPException(404, "证据画面不存在")
        return path

    @app.get("/api/runs/{identifier}/evidence/{filename:path}")
    def evidence_image(identifier: str, filename: str):
        return FileResponse(approved_evidence_path(get("runs", identifier), filename), media_type="image/jpeg")

    @app.post("/api/runs/{identifier}/report")
    async def import_report(identifier: str, request: Request):
        run = get("runs", identifier)
        if not run.get("manifest") or run["status"] in {"queued", "preparing", "analyzing"}:
            raise HTTPException(409, "请等待证据准备完成再导入报告")
        if run["status"] == "completed":
            raise HTTPException(409, "已有完成报告。请新建一次证据准备任务后导入，以保留历史记录")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 1024**2:
                raise HTTPException(413, "报告文件过大")
            body.extend(chunk)
        try:
            report = reporting.validate_report(json.loads(body), run["manifest"])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)[:1200])
        return store.update("runs", identifier, report=report, status="completed", progress=100, message="报告已导入并通过证据校验", error=None, provenance={"method": "imported", "provider": "current-chat", "model": "人工导入，未由应用验证模型身份", "generated_at": now()})

    @app.get("/api/runs/{identifier}/bundle")
    def evidence_bundle(identifier: str):
        run = get("runs", identifier)
        if not run.get("manifest"):
            raise HTTPException(409, "证据尚未就绪")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(run["manifest"], ensure_ascii=False, indent=2))
            archive.writestr("prompt.txt", reporting.build_prompt(run["manifest"], run["target"], run["focus"]))
            archive.write(reporting.SCHEMA_PATH, "report_schema.json")
            for entry in run["manifest"]["frames"] + run["manifest"]["sheets"]:
                archive.write(approved_evidence_path(run, entry["file"]), entry["file"])
            if run.get("status") == "completed" and run.get("report"):
                archive.writestr("report.json", json.dumps(run["report"], ensure_ascii=False, indent=2))
                archive.writestr("provenance.json", json.dumps(run["provenance"], ensure_ascii=False, indent=2))
        return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="tennisai-evidence-{identifier[:8]}.zip"'})

    @app.get("/api/runs/{identifier}/export")
    def export_report(identifier: str, format: str = "markdown"):
        run = get("runs", identifier)
        if run.get("status") != "completed" or not run.get("report"):
            raise HTTPException(409, "仅已完成的分析报告可以导出")
        if format == "json":
            content = json.dumps(run["report"], ensure_ascii=False, indent=2)
            mime, suffix = "application/json", "json"
        elif format == "markdown":
            content = reporting.render_markdown(run["report"])
            provenance = run.get("provenance") or {}
            video = get("videos", run["video_id"])
            content += f"\n\n---\n视频：{video['filename']}\n\n报告来源：{provenance.get('method', '')} / {provenance.get('provider', '')} / {provenance.get('model', '')}\n\n分析范围：{run['window']['start']:.2f}–{run['window']['end']:.2f} 秒\n\n生成时间：{provenance.get('generated_at', '')}\n"
            mime, suffix = "text/markdown; charset=utf-8", "md"
        else:
            raise HTTPException(400, "导出格式须为 json 或 markdown")
        return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="tennisai-report-{identifier[:8]}.{suffix}"'})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/entry-assets", StaticFiles(directory=STATIC), name="entry-assets")
    app.state.prepare_video = prepare_video
    app.state.run_analysis = run_analysis
    app.state.create_run = create_run
    app.state.source_path = source_path
    from .extensions import attach
    attach(app, store, STATIC)
    return app


