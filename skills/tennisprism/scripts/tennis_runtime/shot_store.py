"""Bind optional shot annotations to one run; never trust saved aggregate values."""
import json
import re


def observations_for(store, run):
    revision = run.get('shots_id')
    if revision is None:
        return None
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{32}', revision):
        raise ValueError('Invalid shot revision')
    from .shots import validate_observations
    path = store.path('runs', run['id']) / 'shots' / revision / 'observations.json'
    return validate_observations(json.loads(path.read_text(encoding='utf-8')), run['manifest'], run['target'])


def compute(store, run, observations, pose=None):
    from .h5 import sha
    from .shots import build_metrics
    folder = store.path('runs', run['id'])
    if pose is None and (folder / 'pose.json').exists():
        pose = json.loads((folder / 'pose.json').read_text(encoding='utf-8'))
    preview = store.path('videos', run['video_id']) / 'media' / 'preview.mp4'
    size = None
    if pose:
        import av
        with av.open(str(preview)) as container:
            stream = container.streams.video[0]
            size = (stream.codec_context.width, stream.codec_context.height)
    return build_metrics(observations, run['manifest'], pose=pose,
                         preview_sha256=sha(preview) if pose else None, preview_size=size)
