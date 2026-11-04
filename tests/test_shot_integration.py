"""Portable shot/H5 integration with synthetic media; retained under work/."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

import av
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/tennisprism/scripts'))
import coach
from tennis_runtime import h5, media, main
from tennis_runtime.shot_store import observations_for
from tennis_runtime.store import Store
from test_skill import server as portable_server


def fresh_directory():
    path = ROOT / 'work/shot-integration-tests' / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def make_video(path, fps=30):
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('mpeg4', rate=fps)
        stream.width, stream.height, stream.pix_fmt = 320, 240, 'yuv420p'
        for i in range(fps * 2):
            frame = av.VideoFrame.from_image(Image.new('RGB', (320, 240), (i * 3 % 255, 80, 100)))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


@pytest.fixture(scope='module')
def source_video():
    path = fresh_directory() / 'synthetic-source.mp4'
    make_video(path)
    return path


@pytest.fixture
def session(source_video):
    root = fresh_directory()
    store = Store(root)
    video = store.create('videos', {'filename': 'synthetic.mp4', 'status': 'ready', 'metadata': media.probe_video(source_video)})
    preview = store.path('videos', video['id']) / 'media/preview.mp4'
    preview.parent.mkdir()
    shutil.copy2(source_video, preview)
    manifest = {'evidence_id': uuid.uuid4().hex, 'window': {'start': 0, 'end': 2}, 'video': video['metadata'], 'sampling': {},
                'frames': [{'id': f'f{i}', 'timestamp': time, 'file': f'f{i}.jpg'} for i, time in enumerate([0, .5, 1])], 'sheets': []}
    report = {'schema_version': '3.0', 'evidence_id': manifest['evidence_id'], 'summary': 'NTRP 3.0 synthetic integration fixture',
              'player': {'description': 'Synthetic player'},
              'assessment': {'rating_system': 'NTRP', 'rating': 3, 'rating_status': 'video_estimate', 'label': 'Synthetic fixture', 'confidence': 'low', 'basis': 'Not an analysis', 'not_observed': ['Synthetic media']},
              'strengths': [{'title': 'Synthetic fixture', 'observation': 'Not an observed tennis action', 'interpretation': 'Test only', 'confidence': 'low',
                             'evidence': [{'frame_id': 'f1', 'timestamp': .5, 'description': 'Synthetic evidence'}]}],
              'priorities': [], 'limitations': ['Test only'], 'next_session_focus': ['Test only']}
    run = store.create('runs', {'video_id': video['id'], 'status': 'completed', 'target': {'position': 'near', 'description': ''},
                               'manifest': manifest, 'report': report, 'focus': '', 'provenance': {'model': 'synthetic fixture'}})
    evidence = store.path('runs', run['id']) / 'evidence'
    evidence.mkdir()
    with av.open(str(source_video)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            if i in (0, 15, 30):
                frame.to_image().save(evidence / f'f{i // 15}.jpg')
    (evidence / 'manifest.json').write_text(json.dumps(manifest))
    observations = {'schema_version': '1.0', 'evidence_id': manifest['evidence_id'], 'target': copy.deepcopy(run['target']), 'coverage': 'sampled',
                    'shots': [{'id': 'shot1', 'stroke': 'forehand', 'incoming_depth': 'deep', 'outgoing_depth': 'unknown',
                               'contact_height': 'hip_to_shoulder', 'split_step': 'unknown', 'contact_basis': 'visible', 'hitting_side': 'right',
                               'confidence': 'low', 'note': 'Synthetic test annotation, no real tennis judgment',
                               'evidence': [{'frame_id': f['id'], 'timestamp': f['timestamp'], 'description': 'Synthetic evidence'} for f in manifest['frames']],
                               'phases': {'preparation': 'f0', 'contact': 'f1', 'recovery': 'f2'}}]}
    return store, run, observations, preview


def test_cli_saves_observations_and_preserves_revisions(session, monkeypatch, capsys):
    store, run, observations, _ = session
    annotation = store.root / 'input.json'
    annotation.write_text(json.dumps(observations))
    monkeypatch.setattr(sys, 'argv', ['coach.py', 'shots', '--workspace', str(store.root), '--run', run['id'], '--observations', str(annotation)])
    assert coach.main() == 0
    first = json.loads(capsys.readouterr().out)
    first_raw = Path(first['observations']).read_bytes()
    revised = copy.deepcopy(observations)
    revised['shots'][0]['outgoing_depth'] = 'short'
    second = coach.save_shots(store, store.get('runs', run['id']), revised)
    assert first['revision'] != second['revision']
    assert Path(first['observations']).read_bytes() == first_raw
    assert observations_for(store, store.get('runs', run['id']))['shots'][0]['outgoing_depth'] == 'short'
    assert observations['shots'][0]['outgoing_depth'] == 'unknown'
    assert store.get('runs', run['id'])['h5_url'] is None


@pytest.mark.parametrize('blocked', ['superseded', 'building', 'unprepared', 'foreign'])
def test_shot_submission_rejects_unusable_run_without_artifacts(session, blocked):
    store, run, observations, _ = session
    if blocked == 'superseded':
        run['superseded_by'] = uuid.uuid4().hex
    elif blocked == 'building':
        run['h5_status'] = 'building'
    elif blocked == 'unprepared':
        run['status'] = 'preparing'
    else:
        observations['evidence_id'] = 'other-video'
    with pytest.raises(ValueError):
        coach.save_shots(store, run, observations)
    assert not (store.path('runs', run['id']) / 'shots').exists()
    assert 'shots_id' not in store.get('runs', run['id'])


def load_page_data(directory):
    raw = (Path(directory) / 'data.js').read_text()
    return json.loads(raw.removeprefix('window.TENNIS_REPORT=').removesuffix(';\n'))


def test_h5_recalculates_shots_and_ignores_tampered_metric_cache(session):
    store, run, observations, preview = session
    before = h5.sha(preview)
    saved = coach.save_shots(store, run, observations)
    Path(saved['metrics']).write_text('{"summary":{"shot_count":999},"shots":[]}')
    result = h5.build(store, store.get('runs', run['id']))
    data = load_page_data(result['directory'])
    assert data['shots']['summary']['shot_count'] == 1
    assert data['shots']['summary']['outgoing_depth']['unknown'] == 1
    assert data['shots']['shots'][0]['metrics']['preparation_to_contact_s'] == .5
    assert json.loads((Path(result['directory']) / 'shots.json').read_text()) == data['shots']
    assert 'shots.json' in store.get('runs', run['id'])['h5_files']
    assert h5.sha(preview) == before


def test_h5_without_shots_retains_legacy_contract(session):
    store, run, _, _ = session
    result = h5.build(store, run)
    data = load_page_data(result['directory'])
    assert 'shots' not in data
    assert not (Path(result['directory']) / 'shots.json').exists()
    assert data['report']['assessment']['rating'] == 3
    assert len(data['timestamps']) == 60
    assert (Path(result['directory']) / data['events'][0]['image']).exists()


def test_h5_revalidates_stored_annotations(session):
    store, run, observations, _ = session
    saved = coach.save_shots(store, run, observations)
    observations['target']['position'] = 'far'
    Path(saved['observations']).write_text(json.dumps(observations))
    with pytest.raises(ValueError):
        h5.build(store, store.get('runs', run['id']))
    assert not (store.path('runs', run['id']) / 'h5').exists()


def test_pose_metrics_use_actual_preview_bounds(session):
    store, run, observations, preview = session
    points = [[100., 100., .9, .9] for _ in range(33)]
    for index, coordinates in {11: (100, 50), 12: (200, 50), 14: (200, 100), 16: (250, 100),
                               23: (120, 150), 24: (180, 150), 27: (100, 220), 28: (250, 220)}.items():
        points[index][:2] = coordinates
    pose = {'reviewed': True, 'preview_sha256': h5.sha(preview), 'target': run['target'], 'frames': [{'time': .5, 'landmarks': points}]}
    pose_path = store.path('runs', run['id']) / 'pose.json'
    pose_path.write_text(json.dumps(pose))
    first = coach.save_shots(store, run, observations)
    assert first['summary']['metrics']['elbow_angle_2d_deg']['median'] == 90
    # Within source width in this artificial manifest, outside actual preview.
    run['manifest']['video']['width'] = 2000
    pose['frames'][0]['landmarks'][16][0] = 400
    pose_path.write_text(json.dumps(pose))
    second = coach.save_shots(store, run, observations)
    assert second['summary']['metrics']['elbow_angle_2d_deg']['median'] is None
    assert second['summary']['metrics']['wrist_height_torso_2d']['median'] is None
    assert second['summary']['metrics']['stance_shoulder_ratio_2d']['median'] == 1.5


@pytest.mark.parametrize('fps', [12, 30])
def test_dense_sampling_uses_real_source_frames_and_preserves_original(fps):
    folder = fresh_directory()
    source = folder / 'synthetic.mp4'
    make_video(source, fps)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = media.prepare_evidence(source, folder / 'dense', focus_times=[1], detail_fps=30)
    with av.open(str(source)) as container:
        actual = {round(float(frame.time), 6) for frame in container.decode(video=0)}
    assert manifest['sampling']['sequence_fps'] == min(fps, 30)
    stamps = [frame['timestamp'] for frame in manifest['frames']]
    assert len(stamps) == len(set(stamps))
    assert set(stamps) <= actual
    assert all((folder / 'dense' / frame['file']).is_file() for frame in manifest['frames'])
    assert len(stamps) > 8
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.parametrize('fps', [0, 7, 31, True])
def test_invalid_dense_rate_refused_without_output(source_video, fps):
    destination = fresh_directory() / 'evidence'
    with pytest.raises(media.MediaError):
        media.prepare_evidence(source_video, destination, detail_fps=fps)
    assert not destination.exists()


def test_dense_api_contract_propagates_rate(portable_server, monkeypatch):
    client, headers, app, run = portable_server
    calls = []
    original = main.media.prepare_evidence
    def capture(source, out, **kwargs):
        calls.append(kwargs['detail_fps'])
        return original(source, out, **kwargs)
    monkeypatch.setattr(main.media, 'prepare_evidence', capture)
    response = client.post('/api/videos/' + run['video_id'] + '/runs', json={'detail_fps': 30}, headers=headers)
    assert response.status_code == 202
    assert calls == [30]
    assert app.state.store.get('runs', response.json()['id'])['detail_fps'] == 30
    assert client.post('/api/videos/' + run['video_id'] + '/runs', json={'detail_fps': 20}, headers=headers).status_code == 422


def test_h5_does_not_publish_a_stale_shot_revision(session, monkeypatch):
    store, run, observations, _ = session
    coach.save_shots(store, run, observations)
    current = store.get('runs', run['id'])
    copy_file = h5.shutil.copy2
    changed = False
    def concurrent_revision(source, destination):
        nonlocal changed
        if not changed:
            changed = True
            store.update('runs', run['id'], shots_id=uuid.uuid4().hex)
        return copy_file(source, destination)
    monkeypatch.setattr(h5.shutil, 'copy2', concurrent_revision)
    with pytest.raises(ValueError, match='changed during this build'):
        h5.build(store, current)
    assert store.get('runs', run['id']).get('h5_url') is None
