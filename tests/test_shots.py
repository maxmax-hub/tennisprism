"""Shot evidence contracts and arithmetic; all inputs are synthetic, not coaching."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/tennisprism/scripts"))
from tennis_runtime.shots import ShotValidationError, build_metrics, validate_observations

TARGET = {"position": "near", "description": ""}


def fixture():
    manifest = {"evidence_id": "test-evidence", "window": {"start": 0, "end": 10}, "video": {"duration": 10},
                "frames": [{"id": f"f{i}", "timestamp": t} for i, t in enumerate([.5, 1, 1.75, 2.5, 3, 3.75])]}
    shot = {"id": "shot-1", "stroke": "forehand", "incoming_depth": "deep", "outgoing_depth": "unknown",
            "contact_height": "hip_to_shoulder", "split_step": "unknown", "contact_basis": "visible",
            "hitting_side": "right", "confidence": "medium", "note": "Synthetic labels, not actual observations",
            "evidence": [{"frame_id": f"f{i}", "timestamp": t, "description": "Synthetic evidence"} for i, t in enumerate([.5, 1, 1.75])],
            "phases": {"preparation": "f0", "contact": "f1", "recovery": "f2"}}
    data = {"schema_version": "1.0", "evidence_id": "test-evidence", "target": copy.deepcopy(TARGET), "coverage": "sampled", "shots": [shot]}
    return data, manifest


def pose_fixture():
    points = [[100., 100., .9, .9] for _ in range(33)]
    for i, xy in {11: (100, 100), 12: (200, 100), 14: (200, 150), 16: (250, 150),
                  23: (120, 250), 24: (180, 250), 27: (100, 400), 28: (250, 400)}.items():
        points[i][:2] = xy
    return {"reviewed": True, "preview_sha256": "fixture-hash", "target": copy.deepcopy(TARGET), "frames": [{"time": 1., "landmarks": points}]}


def second_shot(data):
    item = copy.deepcopy(data["shots"][0]); item["id"] = "shot-2"
    item["evidence"] = [{**ref, "frame_id": f"f{i + 3}", "timestamp": ref["timestamp"] + 2} for i, ref in enumerate(item["evidence"])]
    item["phases"] = {"preparation": "f3", "contact": "f4", "recovery": "f5"}
    data["shots"].append(item)
    return item


def test_normalization_is_deterministic_and_does_not_mutate_inputs():
    data, manifest = fixture()
    data["shots"][0]["evidence"][1]["timestamp"] += .0005
    before = copy.deepcopy(data)
    result = validate_observations(data, manifest, TARGET)
    assert result["shots"][0]["evidence"][1]["timestamp"] == 1
    assert data == before
    a = build_metrics(result, manifest)
    assert a == build_metrics(result, manifest)
    assert a["shots"][0]["metrics"]["preparation_to_contact_s"] == .5
    assert a["shots"][0]["metrics"]["contact_to_recovery_s"] == .75
    assert a["shots"][0]["metrics"]["wrist_height_torso_2d"] is None


@pytest.mark.parametrize("case", ["foreign", "target", "bad_frame", "bad_time", "nan", "bool_time", "missing", "extra", "wrong_type", "wrong_enum", "id_duplicate", "frame_duplicate", "phase_missing", "phase_order", "same_phase", "contact_missing", "unknown_height", "unknown_contact", "same_contact_time", "estimated_missing"])
def test_rejects_unbound_or_ambiguous_records(case):
    data, manifest = fixture(); shot = data["shots"][0]
    if case == "foreign": data["evidence_id"] = "other"
    elif case == "target": data["target"]["position"] = "far"
    elif case == "bad_frame": shot["evidence"][0]["frame_id"] = "fake"
    elif case == "bad_time": shot["evidence"][0]["timestamp"] += .1
    elif case == "nan": shot["evidence"][0]["timestamp"] = float("nan")
    elif case == "bool_time": shot["evidence"][0]["timestamp"] = True
    elif case == "missing": shot.pop("note")
    elif case == "extra": shot["ball_speed_kmh"] = 100
    elif case == "wrong_type": shot["confidence"] = 1
    elif case == "wrong_enum": shot["outgoing_depth"] = "winner"
    elif case == "id_duplicate": second_shot(data)["id"] = "shot-1"
    elif case == "frame_duplicate": shot["evidence"].append(copy.deepcopy(shot["evidence"][0]))
    elif case == "phase_missing": shot["phases"]["recovery"] = "f5"
    elif case == "phase_order": shot["phases"]["preparation"] = "f2"
    elif case == "same_phase": shot["phases"]["preparation"] = "f1"
    elif case == "contact_missing": shot["phases"]["contact"] = None
    elif case == "unknown_height": shot.update(contact_basis="unknown"); shot["phases"]["contact"] = None
    elif case == "unknown_contact": shot.update(contact_basis="unknown", contact_height="unknown")
    elif case == "estimated_missing": shot["contact_basis"] = "estimated"; shot["phases"]["contact"] = None
    elif case == "same_contact_time":
        other = copy.deepcopy(shot); other["id"] = "shot-2"; other["phases"] = {"preparation": None, "contact": "same-time", "recovery": None}
        other["evidence"] = [{"frame_id": "same-time", "timestamp": 1, "description": "Duplicate physical time"}]
        manifest["frames"].append({"id": "same-time", "timestamp": 1}); data["shots"].append(other)
    with pytest.raises(ShotValidationError): validate_observations(data, manifest, TARGET)


@pytest.mark.parametrize("case", ["nan_start", "outside", "duplicate_id", "boolean_time", "window_end"])
def test_rejects_corrupt_manifest(case):
    data, manifest = fixture()
    if case == "nan_start": manifest["window"]["start"] = float("nan")
    elif case == "outside": manifest["frames"][0]["timestamp"] = 11
    elif case == "duplicate_id": manifest["frames"].append(copy.deepcopy(manifest["frames"][0]))
    elif case == "boolean_time": manifest["frames"][0]["timestamp"] = False
    elif case == "window_end": manifest["window"]["end"] = 11
    with pytest.raises(ShotValidationError): validate_observations(data, manifest, TARGET)


def test_unknown_estimated_and_visible_have_separate_denominators():
    data, manifest = fixture()
    estimate = second_shot(data); estimate.update(contact_basis="estimated", contact_height="above_shoulder")
    unknown = copy.deepcopy(estimate); unknown.update(id="unknown", contact_basis="unknown", contact_height="unknown", incoming_depth="unknown", split_step="not_observed")
    unknown["phases"] = {"preparation": None, "contact": None, "recovery": None}; data["shots"].append(unknown)
    out = build_metrics(data, manifest)
    height = out["summary"]["contact_height"]
    assert (height["valid"], height["estimated"], height["unknown"], height["total"]) == (1, 1, 1, 3)
    assert height["counts"] == {"below_hip": 0, "hip_to_shoulder": 1, "above_shoulder": 0}
    assert out["summary"]["outgoing_depth"]["valid"] == 0
    assert out["summary"]["outgoing_depth"]["unknown"] == 3
    assert out["summary"]["split_step"]["valid"] == 1
    assert out["summary"]["metrics"]["preparation_to_contact_s"]["valid"] == 1
    assert out["shots"][1]["metrics"]["preparation_to_contact_s"] is None
    assert out["shots"][2]["time"] == 2.5


def test_empty_sample_is_unavailable_not_zero_measurement():
    data, manifest = fixture(); data["shots"] = []
    result = build_metrics(data, manifest)
    assert result["summary"]["shot_count"] == 0
    assert result["summary"]["metrics"]["wrist_height_torso_2d"] == {"median": None, "min": None, "max": None, "valid": 0, "total": 0, "unknown": 0}


def test_phase_dict_key_order_does_not_change_time_order():
    data, manifest = fixture(); data["shots"][0]["phases"] = {"recovery": "f2", "contact": "f1", "preparation": "f0"}
    assert build_metrics(data, manifest)["shots"][0]["metrics"]["contact_to_recovery_s"] == .75


def test_pose_measures_pixel_geometry_and_retains_proxy_names():
    data, manifest = fixture(); pose = pose_fixture()
    out = build_metrics(data, manifest, pose, "fixture-hash", (640, 480))
    m = out["shots"][0]["metrics"]
    assert m["wrist_height_torso_2d"] == pytest.approx(2/3, abs=1e-6)
    assert m["stance_shoulder_ratio_2d"] == 1.5
    assert m["elbow_angle_2d_deg"] == 90
    assert "击球高度" in out["metric_definitions"]["wrist_height_torso_2d"]["description"]
    # A change of uniform pixel scale cannot change any ratio or angle.
    for p in pose["frames"][0]["landmarks"]: p[0] *= 2; p[1] *= 2
    assert build_metrics(data, manifest, pose, "fixture-hash", (1280, 960))["shots"][0]["metrics"] == m


@pytest.mark.parametrize("case", ["unreviewed", "truthy_review", "wrong_hash", "missing_expected_hash", "wrong_target", "unordered", "bad_points", "nan_points", "bool_points"])
def test_pose_identity_and_shape_must_be_valid(case):
    data, manifest = fixture(); pose = pose_fixture(); expected = "fixture-hash"
    if case == "unreviewed": pose["reviewed"] = False
    elif case == "truthy_review": pose["reviewed"] = "true"
    elif case == "wrong_hash": pose["preview_sha256"] = "other"
    elif case == "missing_expected_hash": expected = None
    elif case == "wrong_target": pose["target"]["position"] = "far"
    elif case == "unordered": pose["frames"].append(copy.deepcopy(pose["frames"][0]))
    elif case == "bad_points": pose["frames"][0]["landmarks"] = []
    elif case == "nan_points": pose["frames"][0]["landmarks"][0][0] = float("nan")
    elif case == "bool_points": pose["frames"][0]["landmarks"][0][0] = False
    with pytest.raises(ShotValidationError): build_metrics(data, manifest, pose, expected, (640, 480))


@pytest.mark.parametrize("case", ["low_visibility", "low_presence", "missing_nearest", "too_far", "degenerate", "unknown_side", "estimated_contact"])
def test_pose_gaps_and_insufficient_points_stay_null(case):
    data, manifest = fixture(); pose = pose_fixture(); row = pose["frames"][0]
    if case == "low_visibility": row["landmarks"][16][2] = .64
    elif case == "low_presence": row["landmarks"][16][3] = .64
    elif case == "missing_nearest":
        row["time"] = .99; pose["frames"].append({"time": 1., "landmarks": None})
    elif case == "too_far": row["time"] = 1.051
    elif case == "degenerate": row["landmarks"][16][:2] = row["landmarks"][14][:2]
    elif case == "unknown_side": data["shots"][0]["hitting_side"] = "unknown"
    elif case == "estimated_contact": data["shots"][0]["contact_basis"] = "estimated"
    metrics = build_metrics(data, manifest, pose, "fixture-hash", (640, 480))["shots"][0]["metrics"]
    assert metrics["elbow_angle_2d_deg"] is None
    if case not in {"degenerate"}: assert metrics["wrist_height_torso_2d"] is None


def test_zero_is_retained_only_when_it_is_a_valid_computed_value():
    data, manifest = fixture(); pose = pose_fixture(); pose["frames"][0]["landmarks"][16][1] = 250
    metrics = build_metrics(data, manifest, pose, "fixture-hash", (640, 480))
    assert metrics["shots"][0]["metrics"]["wrist_height_torso_2d"] == 0
    assert metrics["summary"]["metrics"]["wrist_height_torso_2d"]["valid"] == 1


@pytest.mark.parametrize("size", [None, [], (640,), (True, 480), (640, 0), (640., 480)])
def test_pose_requires_actual_preview_coordinate_dimensions(size):
    data, manifest = fixture()
    with pytest.raises(ShotValidationError): build_metrics(data, manifest, pose_fixture(), "fixture-hash", size)


@pytest.mark.parametrize("point", [(640., 150.), (-1., 150.), (250., 480.), (250., -1.)])
def test_high_confidence_offscreen_wrist_cannot_be_measured(point):
    data, manifest = fixture(); pose = pose_fixture(); pose["frames"][0]["landmarks"][16][:2] = point
    metrics = build_metrics(data, manifest, pose, "fixture-hash", (640, 480))["shots"][0]["metrics"]
    assert metrics["elbow_angle_2d_deg"] is None
    assert metrics["wrist_height_torso_2d"] is None
    assert metrics["stance_shoulder_ratio_2d"] == 1.5
