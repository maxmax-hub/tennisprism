"""Bounded, timestamp-grounded video evidence preparation.

Original media is read only. Outputs are created in a new run directory; this
module never deletes files or replaces an existing prepared artifact.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import av
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageOps


MAX_DURATION_SECONDS = 6 * 60 * 60
MAX_PIXELS = 36_000_000
MAX_FRAME_EDGE = 1600
MAX_OVERVIEW_FRAMES = 18
MAX_SEQUENCES = 4
SEQUENCE_FRAMES = 8
SEQUENCE_FPS = 8
MAX_DECODE_PER_SEEK = 1800
PREVIEW_TIMEOUT_SECONDS = 60 * 60
Progress = Callable[[int, str], None]


class MediaError(ValueError):
    """An invalid or unsupported video, rather than a programming error."""


def _emit(progress: Progress | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(percent, message)


def _source(path: Path) -> Path:
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise MediaError("请选择一个视频文件。")
    if path.stat().st_size == 0:
        raise MediaError("视频文件为空。")
    return path


def _stream(container):
    streams = list(container.streams.video)
    if not streams:
        raise MediaError("文件中没有可解码的视频轨道。")
    stream = streams[0]
    stream.codec_context.thread_count = 2
    width, height = stream.codec_context.width, stream.codec_context.height
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise MediaError("视频尺寸无效或过大；当前支持最高约 8K 分辨率。")
    return stream


def _origin(stream) -> float:
    return float(stream.start_time * stream.time_base) if stream.start_time is not None else 0.0


def _rotation(frame, stream) -> int:
    # Modern PyAV exposes display-matrix rotation on decoded frames. Older
    # files may instead carry rotate metadata. PIL uses counterclockwise angles.
    value = getattr(frame, "rotation", None)
    if value is None:
        try:
            value = -float(stream.metadata.get("rotate", "0"))
        except (TypeError, ValueError):
            value = 0
    return int(round(float(value))) % 360


def _image(frame, stream) -> Image.Image:
    result = frame.to_image().convert("RGB")
    rotation = _rotation(frame, stream)
    if rotation:
        result = result.rotate(rotation, expand=True)
    result.thumbnail((MAX_FRAME_EDGE, MAX_FRAME_EDGE), Image.Resampling.LANCZOS)
    return result


def probe_video(path: Path) -> dict:
    """Read video-track metadata and prove that at least one frame decodes."""
    path = _source(path)
    try:
        with av.open(str(path)) as container:
            stream = _stream(container)
            duration = (
                float(stream.duration * stream.time_base)
                if stream.duration is not None
                else float(container.duration / av.time_base) if container.duration is not None else 0
            )
            if not math.isfinite(duration) or duration <= 0:
                raise MediaError("无法读取有效的视频时长，请先导出为普通 MP4 或 MOV。")
            if duration > MAX_DURATION_SECONDS:
                raise MediaError("当前原型支持不超过 6 小时的视频。")
            frame = next(container.decode(stream), None)
            if frame is None or frame.pts is None:
                raise MediaError("无法解码带时间戳的视频帧。")
            fps = float(stream.average_rate or stream.base_rate or 0)
            if not math.isfinite(fps) or fps <= 0:
                raise MediaError("无法读取有效的视频帧率。")
            width, height = frame.width, frame.height
            rotation = _rotation(frame, stream)
            if rotation in (90, 270):
                width, height = height, width
            return {
                "duration": round(duration, 6),
                "width": width,
                "height": height,
                "fps": round(fps, 6),
                "has_audio": bool(container.streams.audio),
                "codec": stream.codec_context.name,
            }
    except MediaError:
        raise
    except (av.error.FFmpegError, StopIteration, OSError, ValueError) as exc:
        raise MediaError("无法读取这个视频；请确认文件完整，且格式为 MP4、MOV 等常见视频。") from exc


def _output_file(output_dir: Path, name: str) -> Path:
    path = output_dir / name
    if path.exists():
        raise MediaError(f"输出已存在，请创建新的分析记录：{name}")
    return path


def _nearest_frame(container, stream, target: float, start: float, end: float):
    """Seek cheaply; return the closest real decoded PTS within the window."""
    origin = _origin(stream)
    offset = int((target + origin) / float(stream.time_base))
    container.seek(offset, stream=stream, backward=True, any_frame=False)
    best = None
    deadline = time.monotonic() + 20
    for index, frame in enumerate(container.decode(stream)):
        if index >= MAX_DECODE_PER_SEEK or time.monotonic() > deadline:
            raise MediaError("视频关键帧间隔过大或解码过慢，请导出为普通 MP4 后重试。")
        if frame.pts is None:
            continue
        timestamp = float(frame.pts * frame.time_base) - origin
        if timestamp < start - 1e-7:
            continue
        if timestamp > end + 1e-7:
            break
        if best is None or abs(timestamp - target) < abs(best[0] - target):
            best = (timestamp, frame)
        if timestamp >= target:
            break
    return best


def prepare_video(source: Path, output_dir: Path, progress: Progress | None = None) -> dict:
    """Create a browser-compatible preview and thumbnail without changing source."""
    source = _source(source)
    metadata = probe_video(source)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preview = _output_file(output_dir, "preview.mp4")
    thumbnail = _output_file(output_dir, "thumbnail.jpg")
    _emit(progress, 5, "已读取视频，正在生成浏览器预览")
    fps = min(metadata["fps"], 30)
    # No shell, no overwrite flag, and no cleanup command. setpts makes preview
    # seek times use the same first-video-stream origin as evidence timestamps.
    video_filter = (
        "setpts=PTS-STARTPTS,"
        f"fps={fps:.6f}:eof_action=pass,"
        "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
        "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-threads", "2", "-c:a", "aac", "-b:a", "96k", "-af", "asetpts=PTS-STARTPTS",
        "-movflags", "+faststart", "-map_metadata", "-1", str(preview),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=PREVIEW_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("预览转换超过一小时，已停止；原视频未更改。请使用更短的录像重试。") from exc
    except OSError as exc:
        raise MediaError("无法启动本地视频转换工具。") from exc
    if result.returncode != 0 or not preview.exists() or preview.stat().st_size == 0:
        raise MediaError("无法转换这个视频为浏览器预览；请检查文件是否完整或导出为 H.264 MP4。")
    _emit(progress, 90, "正在生成缩略图")
    try:
        with av.open(str(source)) as container:
            stream = _stream(container)
            selected = _nearest_frame(container, stream, min(metadata["duration"] / 3, 3), 0, metadata["duration"])
            if selected is None:
                raise MediaError("视频中没有可用缩略图。")
            picture = _image(selected[1], stream)
            picture.thumbnail((640, 640), Image.Resampling.LANCZOS)
            with thumbnail.open("xb") as file:
                picture.save(file, format="JPEG", quality=86)
    except (av.error.FFmpegError, OSError) as exc:
        raise MediaError("预览已生成，但缩略图解码失败。") from exc
    _emit(progress, 100, "视频已准备好")
    return metadata


def _font(size: int):
    # Pillow's bundled default font is always available; avoid host-specific
    # font paths. Sheet labels use ASCII to remain portable and readable.
    return ImageFont.load_default(size=size)


def _time_label(timestamp: float) -> str:
    milliseconds = int(round(timestamp * 1000))
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _make_sheet(output_dir: Path, name: str, frames: list[dict], title: str, columns: int) -> dict:
    tile_w, tile_h, caption_h, padding, header_h = 480, 300, 38, 14, 64
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (padding + columns * (tile_w + padding), header_h + padding + rows * (tile_h + caption_h + padding)), "#101b22")
    draw = ImageDraw.Draw(sheet)
    draw.text((padding, 10), title, fill="#eff8f4", font=_font(23))
    draw.text((padding, 39), "Sampled frames only | ID + video timestamp | not hit detection", fill="#aab9bf", font=_font(16))
    for index, frame in enumerate(frames):
        x = padding + (index % columns) * (tile_w + padding)
        y = header_h + padding + (index // columns) * (tile_h + caption_h + padding)
        with Image.open(output_dir / frame["file"]) as original:
            thumbnail = ImageOps.contain(original, (tile_w, tile_h), Image.Resampling.LANCZOS)
            sheet.paste(thumbnail, (x + (tile_w - thumbnail.width) // 2, y + (tile_h - thumbnail.height) // 2))
        draw.text((x + 4, y + tile_h + 4), f"{frame['id']}  |  {_time_label(frame['timestamp'])}", font=_font(22), fill="#ddf89a")
    with _output_file(output_dir, name).open("xb") as file:
        sheet.save(file, "JPEG", quality=90)
    return {"file": name, "frame_ids": [frame["id"] for frame in frames]}


def _finite_number(value, label: str) -> float:
    if isinstance(value, bool):
        raise MediaError(f"{label}必须为有限数字。")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaError(f"{label}必须为有限数字。") from exc
    if not math.isfinite(result):
        raise MediaError(f"{label}必须为有限数字。")
    return result


def _sampling_groups(start: float, end: float, fps: float, focus_times: list[float]) -> list[tuple[str, list[float]]]:
    span = end - start
    last = max(start, end - min(0.5 / fps, span / 2))
    count = min(MAX_OVERVIEW_FRAMES, max(2, math.ceil(span * 2)))
    groups = [("overview", [start + (last - start) * i / (count - 1) for i in range(count)])]
    centers = focus_times or [start + span * fraction / (MAX_SEQUENCES + 1) for fraction in range(1, MAX_SEQUENCES + 1)]
    duration = min((SEQUENCE_FRAMES - 1) / SEQUENCE_FPS, last - start)
    for index, center in enumerate(centers):
        burst_start = min(max(center - duration / 2, start), last - duration)
        groups.append((f"sequence_{index + 1}", [burst_start + duration * i / (SEQUENCE_FRAMES - 1) for i in range(SEQUENCE_FRAMES)]))
    return groups


def prepare_evidence(
    source: Path,
    output_dir: Path,
    start: float = 0,
    end: float | None = None,
    focus_times: list[float] | None = None,
    progress: Progress | None = None,
) -> dict:
    """Sample an explicit video window and write a reproducible evidence manifest."""
    source = _source(source)
    metadata = probe_video(source)
    start = _finite_number(start, "开始时间")
    end = metadata["duration"] if end is None else _finite_number(end, "结束时间")
    if start < 0 or end <= start or end > metadata["duration"] + 0.000001:
        raise MediaError("分析范围必须在视频时长内，且结束时间晚于开始时间。")
    focus_times = list(focus_times or [])
    if len(focus_times) > MAX_SEQUENCES:
        raise MediaError("最多指定 4 个重点观察时间点。")
    focus_times = [_finite_number(value, "重点观察时间") for value in focus_times]
    if any(value < start or value > end for value in focus_times):
        raise MediaError("重点观察时间必须位于所选分析范围内。")
    groups = _sampling_groups(start, end, metadata["fps"], focus_times)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _output_file(output_dir, "manifest.json")
    evidence_id = "ev_" + uuid.uuid4().hex
    frame_prefix = evidence_id[3:15]
    frame_lookup: dict[int, dict] = {}
    frames: list[dict] = []
    group_frames: dict[str, list[dict]] = {}
    missing = 0
    requests = sum(len(targets) for _, targets in groups)
    completed = 0
    _emit(progress, 3, "正在提取带真实时间戳的视频证据")
    try:
        with av.open(str(source)) as container:
            stream = _stream(container)
            for group_name, targets in groups:
                selected_frames = []
                for target in targets:
                    selected = _nearest_frame(container, stream, target, start, end)
                    completed += 1
                    _emit(progress, 5 + int(75 * completed / requests), f"正在提取证据 {completed}/{requests}")
                    if selected is None:
                        missing += 1
                        continue
                    timestamp, decoded = selected
                    key = round(timestamp * 1_000_000)
                    if key not in frame_lookup:
                        filename = f"F{len(frames) + 1:04d}.jpg"
                        frame_id = f"{frame_prefix}-F{len(frames) + 1:04d}"
                        with _output_file(output_dir, filename).open("xb") as file:
                            _image(decoded, stream).save(file, "JPEG", quality=90)
                        entry = {"id": frame_id, "timestamp": round(timestamp, 6), "file": filename, "group": group_name}
                        frame_lookup[key] = entry
                        frames.append(entry)
                    entry = frame_lookup[key]
                    if entry not in selected_frames:
                        selected_frames.append(entry)
                if selected_frames:
                    group_frames[group_name] = selected_frames
    except (av.error.FFmpegError, OSError) as exc:
        raise MediaError("提取视频证据失败；文件可能损坏或编码不受支持。已保留原视频。") from exc
    if not frames:
        raise MediaError("所选时间范围内没有可解码视频帧，请扩大分析范围。")
    _emit(progress, 85, "正在生成时间点索引图")
    sheets = []
    for group_name, selected_frames in group_frames.items():
        title = "VIDEO OVERVIEW" if group_name == "overview" else f"TEMPORAL {group_name.upper()} | sampled at up to {SEQUENCE_FPS} fps"
        sheets.append(_make_sheet(output_dir, f"{group_name}.jpg", selected_frames, title, columns=3 if group_name == "overview" else 4))
    warnings = [
        "这是一组稀疏概览帧与短时间序列，不是对所选范围内每一拍或整个视频的完整观察。",
        "连续序列由均匀位置或用户时间点选取，未检测击球、触球时刻或回合；可能包含休息、捡球或无效动作。",
        "短序列最多每秒采样 8 帧，快速挥拍和触球细节可能遗漏；不能据此测量球速、转速、精确拍面或落点判罚。",
    ]
    if min(metadata["width"], metadata["height"]) < 720:
        warnings.append("视频分辨率偏低，人体、球拍和网球细节可能不足；细微动作判断应保留。")
    if end - start > 120:
        warnings.append("所选范围超过两分钟，固定数量的样本覆盖比例较低，不能由这些片段统计整段表现或失误率。")
    if metadata["fps"] < 24:
        warnings.append("原视频帧率较低，快速动作的时间顺序与触球细节可能无法判断。")
    if missing:
        warnings.append(f"有 {missing} 个采样目标未能取得范围内的有效帧，报告须考虑证据缺失。")
    manifest = {
        "version": "1.0",
        "evidence_id": evidence_id,
        "video": {key: metadata[key] for key in ("duration", "width", "height", "fps")},
        "window": {"start": start, "end": end},
        "sampling": {
            "description": f"最多 {MAX_OVERVIEW_FRAMES} 张均匀概览帧及 {MAX_SEQUENCES} 组短序列，每组最多 {SEQUENCE_FRAMES} 帧；时间来自解码帧 PTS 并以视频轨道起点归零。",
            "coverage_note": " ".join(warnings),
            "warnings": warnings,
            "method": "uniform_overview_and_temporal_bursts",
            "sequence_fps": SEQUENCE_FPS,
            "focus_times": focus_times,
            "requested_frame_count": requests,
            "decoded_unique_frame_count": len(frames),
            "missing_frame_count": missing,
            "max_frame_edge": MAX_FRAME_EDGE,
            "audio_included": False,
        },
        "frames": frames,
        "sheets": sheets,
    }
    with _output_file(output_dir, "manifest.json").open("x", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2, allow_nan=False)
    _emit(progress, 100, f"已准备 {len(frames)} 张证据帧和 {len(sheets)} 张索引图")
    return manifest
