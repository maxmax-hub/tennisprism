"""Deterministic summaries of evidence-reviewed shot annotations, not a detector.

The host Agent supplies observations after actually viewing frames. This module
checks their provenance and computes arithmetic; it cannot verify a visual claim.
Pose quantities are image-plane proxies, never physical contact height or diagnoses.
"""
from __future__ import annotations

import copy
import bisect
import json
import math
import statistics
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("shot_schema.json")
SHOT_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
MIN_SEGMENT_PX = 1.0  # Reject degenerate image geometry, not a coaching threshold.
POSE_TIME_TOLERANCE_S = .05  # Matching tolerance, not estimated event accuracy.
METRIC_DEFINITIONS = {
    "preparation_to_contact_s": {
        "label": "已标注准备到触球间隔", "unit": "s",
        "description": "准备帧到可见触球帧的时间差；不是启动反应时间，精度受采样间隔限制。",
    },
    "contact_to_recovery_s": {
        "label": "已标注触球到回位间隔", "unit": "s",
        "description": "可见触球帧到标注回位帧的时间差；回位定义须在逐拍备注说明。",
    },
    "wrist_height_torso_2d": {
        "label": "击球手腕相对躯干高度（2D）", "unit": "ratio",
        "description": "(髋中点 y − 击球侧手腕 y) / (髋中点 y − 肩中点 y)，画面投影；不是球的击球高度或身高比例。",
    },
    "stance_shoulder_ratio_2d": {
        "label": "脚踝间距／肩宽（2D）", "unit": "ratio",
        "description": "画面中双脚踝距离 / 双肩距离；受朝向和透视影响，不是实际站距或稳定性评分。",
    },
    "elbow_angle_2d_deg": {
        "label": "击球侧肘夹角（2D）", "unit": "deg",
        "description": "肩—肘—腕在图像平面的内角；不代表三维关节角，不设通用理想值或伤病阈值。",
    },
}


class ShotValidationError(ValueError):
    """Invalid or foreign shot evidence; preserve prior accepted artifacts."""


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _check(value, schema, path="shots"):
    kind = schema["type"]
    if isinstance(kind, list):
        if value is None and "null" in kind:
            return
        kind = next(t for t in kind if t != "null")
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ShotValidationError(f"{path}: fields must exactly match shot_schema.json")
        for key, rule in schema["properties"].items():
            _check(value[key], rule, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            raise ShotValidationError(f"{path}: invalid array length")
        for i, item in enumerate(value):
            _check(item, schema["items"], f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(value, str) or not schema.get("minLength", 0) <= len(value.strip()) <= schema.get("maxLength", 4000):
            raise ShotValidationError(f"{path}: invalid text")
        if "enum" in schema and value not in schema["enum"]:
            raise ShotValidationError(f"{path}: unsupported value")
    elif kind == "number":
        if not _finite(value) or value < schema.get("minimum", -math.inf):
            raise ShotValidationError(f"{path}: must be a finite number")


def _frames(manifest):
    try:
        start, end = manifest["window"]["start"], manifest["window"]["end"]
        duration = manifest["video"]["duration"]
        rows = manifest["frames"]
        if not all(_finite(x) for x in (start, end, duration)) or not 0 <= start <= end <= duration + .12:
            raise ValueError("window")
        frames = {f["id"]: f for f in rows}
        if not frames or len(frames) != len(rows):
            raise ValueError("frames")
        for key, row in frames.items():
            if not isinstance(key, str) or not key or not _finite(row["timestamp"]) or not start - .0001 <= row["timestamp"] <= end + .0001:
                raise ValueError("timestamp")
        return frames
    except (KeyError, TypeError, ValueError) as exc:
        raise ShotValidationError("Invalid evidence manifest or frame timestamps") from exc


def validate_observations(data, manifest, target):
    """Bind observations to the current target and exact decoded evidence frames."""
    _check(data, SHOT_SCHEMA)
    if not manifest.get("evidence_id") or data["evidence_id"] != manifest["evidence_id"]:
        raise ShotValidationError("Shot observations belong to a different evidence package")
    if data["target"] != target:
        raise ShotValidationError("Shot target does not match this run")
    frames = _frames(manifest)
    result = copy.deepcopy(data)
    ids, contacts = set(), set()
    for shot in result["shots"]:
        if shot["id"] in ids:
            raise ShotValidationError("Duplicate shot ID")
        ids.add(shot["id"])
        refs = set()
        for ref in shot["evidence"]:
            frame = frames.get(ref["frame_id"])
            if frame is None or abs(ref["timestamp"] - frame["timestamp"]) > .00100001:
                raise ShotValidationError("Shot frame or timestamp does not match decoded evidence")
            if ref["frame_id"] in refs:
                raise ShotValidationError("Duplicate evidence reference in shot")
            refs.add(ref["frame_id"])
            ref["timestamp"] = frame["timestamp"]
        phases = shot["phases"]
        times = []
        for phase in ("preparation", "contact", "recovery"):
            frame_id = phases[phase]
            if frame_id is not None:
                if frame_id not in refs:
                    raise ShotValidationError("Every phase must cite evidence from this shot")
                times.append(frames[frame_id]["timestamp"])
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ShotValidationError("Preparation, contact and recovery must be distinct ordered frames")
        contact = phases["contact"]
        if shot["contact_basis"] == "unknown":
            if contact is not None or shot["contact_height"] != "unknown":
                raise ShotValidationError("Unknown contact must have no contact frame or contact height")
        elif contact is None:
            raise ShotValidationError("Visible or estimated contact requires a cited contact frame")
        if contact is not None:
            t = frames[contact]["timestamp"]
            if t in contacts:
                raise ShotValidationError("Two shots cannot claim the same contact time")
            contacts.add(t)
    return result


def _pose_rows(pose, target, preview_sha256, duration):
    if pose is None:
        return []
    if not preview_sha256 or pose.get("preview_sha256") != preview_sha256 or pose.get("target") != target or pose.get("reviewed") is not True:
        raise ShotValidationError("Pose must be reviewed and match this target and preview hash")
    rows = pose.get("frames")
    if not isinstance(rows, list):
        raise ShotValidationError("Pose frames must be an array")
    previous = -math.inf
    for row in rows:
        if not isinstance(row, dict) or not _finite(row.get("time")) or not 0 <= row["time"] <= duration + .12 or row["time"] <= previous:
            raise ShotValidationError("Pose timestamps must be finite, ordered and within the video")
        previous = row["time"]
        pts = row.get("landmarks")
        if pts is not None:
            if not isinstance(pts, list) or len(pts) != 33 or any(not isinstance(p, list) or len(p) != 4 or not all(_finite(v) for v in p) or not 0 <= p[2] <= 1 or not 0 <= p[3] <= 1 for p in pts):
                raise ShotValidationError("Invalid pose points; expected pixel x/y, visibility and presence")
    return rows


def _pose_metrics(points, hitting_side, preview_size):
    result = {k: None for k in METRIC_DEFINITIONS if not k.endswith("_s")}
    if points is None:
        return result
    width, height = preview_size
    def good(*ids):
        return all(points[i][2] >= .65 and points[i][3] >= .65 and 0 <= points[i][0] < width and 0 <= points[i][1] < height for i in ids)
    def dist(a, b):
        return math.hypot(points[a][0] - points[b][0], points[a][1] - points[b][1])
    if good(11, 12, 27, 28) and dist(11, 12) > MIN_SEGMENT_PX:
        result["stance_shoulder_ratio_2d"] = dist(27, 28) / dist(11, 12)
    if hitting_side != "unknown":
        shoulder, elbow, wrist = (11, 13, 15) if hitting_side == "left" else (12, 14, 16)
        if good(11, 12, 23, 24, wrist):
            shoulder_y = (points[11][1] + points[12][1]) / 2
            hip_y = (points[23][1] + points[24][1]) / 2
            if hip_y - shoulder_y > MIN_SEGMENT_PX:
                result["wrist_height_torso_2d"] = (hip_y - points[wrist][1]) / (hip_y - shoulder_y)
        if good(shoulder, elbow, wrist) and dist(shoulder, elbow) > MIN_SEGMENT_PX and dist(elbow, wrist) > MIN_SEGMENT_PX:
            u = [points[shoulder][i] - points[elbow][i] for i in (0, 1)]
            v = [points[wrist][i] - points[elbow][i] for i in (0, 1)]
            cosine = sum(a * b for a, b in zip(u, v)) / (dist(shoulder, elbow) * dist(elbow, wrist))
            result["elbow_angle_2d_deg"] = math.degrees(math.acos(max(-1, min(1, cosine))))
    return result


def _category(shots, key):
    choices = SHOT_SCHEMA["properties"]["shots"]["items"]["properties"][key]["enum"]
    counts = {c: 0 for c in choices if c != "unknown"}
    unknown, estimated = 0, 0
    for shot in shots:
        value = shot[key]
        if value == "unknown":
            unknown += 1
        elif key == "contact_height" and shot["contact_basis"] == "estimated":
            estimated += 1
        else:
            counts[value] += 1
    return {"counts": counts, "valid": sum(counts.values()), "total": len(shots), "unknown": unknown, "estimated": estimated}


def build_metrics(observations, manifest, pose=None, preview_sha256=None, preview_size=None):
    """Compute deterministic sample summaries; no generated or interpolated values."""
    normalized = validate_observations(observations, manifest, observations.get("target"))
    frames = _frames(manifest)
    if pose is not None and (not isinstance(preview_size, (tuple, list)) or len(preview_size) != 2 or not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in preview_size)):
        raise ShotValidationError("Pose metrics require the actual decoded preview width and height")
    pose_rows = _pose_rows(pose, normalized["target"], preview_sha256, manifest["video"]["duration"])
    shots = normalized["shots"]
    for shot in shots:
        phases = shot["phases"]
        contact = phases["contact"]
        shot["time"] = frames[contact]["timestamp"] if contact else min(ref["timestamp"] for ref in shot["evidence"])
        metrics = {key: None for key in METRIC_DEFINITIONS}
        if shot["contact_basis"] == "visible":
            t = shot["time"]
            if phases["preparation"]:
                metrics["preparation_to_contact_s"] = t - frames[phases["preparation"]]["timestamp"]
            if phases["recovery"]:
                metrics["contact_to_recovery_s"] = frames[phases["recovery"]]["timestamp"] - t
            # Never skip a missing nearest frame to select a farther convenient pose.
            index = bisect.bisect_left(pose_rows, t, key=lambda row: row["time"])
            nearby = pose_rows[max(0, index - 1):index + 1]
            nearest = min(nearby, key=lambda row: abs(row["time"] - t), default=None)
            if nearest is not None and abs(nearest["time"] - t) <= POSE_TIME_TOLERANCE_S + 1e-8:
                metrics.update(_pose_metrics(nearest.get("landmarks"), shot["hitting_side"], preview_size))
        shot["metrics"] = {key: round(value, 6) if value is not None and math.isfinite(value) else None for key, value in metrics.items()}
    counts = {k: 0 for k in SHOT_SCHEMA["properties"]["shots"]["items"]["properties"]["stroke"]["enum"]}
    for shot in shots:
        counts[shot["stroke"]] += 1
    summary = {"shot_count": len(shots), "stroke_counts": counts}
    summary.update({key: _category(shots, key) for key in ("contact_height", "incoming_depth", "outgoing_depth", "split_step")})
    summary["metrics"] = {}
    for key in METRIC_DEFINITIONS:
        values = [shot["metrics"][key] for shot in shots if shot["metrics"][key] is not None]
        summary["metrics"][key] = {"median": statistics.median(values) if values else None, "min": min(values) if values else None, "max": max(values) if values else None, "valid": len(values), "total": len(shots), "unknown": len(shots) - len(values)}
    return {**normalized, "summary": summary, "metric_definitions": copy.deepcopy(METRIC_DEFINITIONS), "notes": [
        "仅统计 Agent 实际查看并标注的样本，不是全场自动逐拍统计；校验通过不等于观察准确。",
        "未判断的项目保留 unknown / null，不计为零或失败；估计触球高度与可见触球分开。",
        "动作阶段时间差受证据采样限制，不是反应时间；2D 手腕、站距和肘角不是三维测量。",
        "整体中位数混合不同来球和动作；比较时应筛选相同击球、来球条件，前后差异本身不能证明疲劳或进步。",
    ]}
