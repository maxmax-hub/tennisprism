"""Synthetic coaching-selection contracts, not a coaching-accuracy benchmark."""
import copy

import pytest

from test_skill import report as legacy_report, server
from tennis_runtime import reporting
from test_shot_integration import session, source_video, load_page_data


def current_report(manifest):
    body = legacy_report(manifest)
    body['schema_version'] = '3.1'
    p = body['priorities'][0]
    p['selection'] = {
        'role': 'trial', 'situation': 'Synthetic wide forehand',
        'pattern': 'single', 'phase_status': 'confirmed',
        'why_this_player': 'One selected movement, not a repeated weakness',
        'comparison': {'status': 'unavailable', 'note': 'No matched comparison', 'evidence': []},
        'outcome': {'status': 'unknown', 'note': 'Ball outcome is hidden', 'evidence': []},
        'preserve': 'Keep the existing swing',
    }
    p['drill']['test_variable'] = 'Record repeated comparable balls without changing technique'
    return body


@pytest.fixture
def manifest():
    return {'evidence_id': 'synthetic-coaching', 'window': {'start': 0, 'end': 8},
            'video': {'duration': 8}, 'sampling': {},
            'frames': [{'id': 'f1', 'timestamp': .5}, {'id': 'f2', 'timestamp': 4.0}]}


def test_single_unknown_outcome_can_have_a_trial_without_invented_comparison(manifest):
    result = reporting.validate_report(current_report(manifest), manifest)
    assert result['priorities'][0]['selection']['role'] == 'trial'
    assert result['priorities'][0]['selection']['comparison']['evidence'] == []
    assert '先验证' in reporting.render_markdown(result)


@pytest.mark.parametrize('missing', ['kind', 'pattern', 'phase', 'outcome'])
def test_focus_requires_confirmed_repeated_observation_and_visible_consequence(manifest, missing):
    body = current_report(manifest)
    p = body['priorities'][0]
    p['kind'] = 'observed'
    p['selection'].update(role='focus', pattern='repeated')
    p['selection']['outcome'] = {'status': 'observed', 'note': 'Synthetic consequence', 'evidence': copy.deepcopy(p['evidence'])}
    if missing == 'kind': p['kind'] = 'potential'
    if missing == 'pattern': p['selection']['pattern'] = 'single'
    if missing == 'phase': p['selection']['phase_status'] = 'unclear'
    if missing == 'outcome': p['selection']['outcome'] = {'status': 'unknown', 'note': 'Hidden', 'evidence': []}
    with pytest.raises(reporting.ReportValidationError):
        reporting.validate_report(body, manifest)


@pytest.mark.parametrize('location', ['comparison', 'outcome'])
@pytest.mark.parametrize('failure', ['foreign_frame', 'wrong_time', 'missing_evidence'])
def test_new_context_references_are_bound_to_current_video(manifest, location, failure):
    body = current_report(manifest)
    context = body['priorities'][0]['selection'][location]
    context.update(status='matched' if location == 'comparison' else 'observed',
                   evidence=[{'frame_id': 'f2', 'timestamp': 4.0, 'description': 'Synthetic counterexample'}])
    if failure == 'foreign_frame': context['evidence'][0]['frame_id'] = 'another-person-frame'
    if failure == 'wrong_time': context['evidence'][0]['timestamp'] = 7
    if failure == 'missing_evidence': context['evidence'] = []
    with pytest.raises(reporting.ReportValidationError):
        reporting.validate_report(body, manifest)


def test_context_timestamp_normalization_and_legacy_compatibility(manifest):
    body = current_report(manifest)
    body['priorities'][0]['selection']['comparison'] = {
        'status': 'context_only', 'note': 'Different incoming ball, not an improvement claim',
        'evidence': [{'frame_id': 'f2', 'timestamp': 4.05, 'description': 'Synthetic context'}]}
    result = reporting.validate_report(body, manifest)
    assert result['priorities'][0]['selection']['comparison']['evidence'][0]['timestamp'] == 4.0
    assert body['priorities'][0]['selection']['comparison']['evidence'][0]['timestamp'] == 4.05
    old = reporting.validate_report(legacy_report(manifest), manifest)
    assert old['schema_version'] == '3.0' and 'selection' not in old['priorities'][0]


def test_development_cannot_fill_the_focus_slot(manifest):
    body = current_report(manifest)
    body['priorities'][0]['kind'] = 'development'
    with pytest.raises(reporting.ReportValidationError):
        reporting.validate_report(body, manifest)
    body['priorities'][0]['selection']['role'] = 'optional'
    assert reporting.validate_report(body, manifest)['priorities'][0]['selection']['role'] == 'optional'


def test_report_may_have_no_individual_training_priority(manifest):
    body = current_report(manifest)
    body['priorities'] = []
    assert reporting.validate_report(body, manifest)['priorities'] == []


def test_declared_confirmed_focus_is_valid_without_forcing_a_comparison(manifest):
    body = current_report(manifest)
    p = body['priorities'][0]
    p['kind'] = 'observed'
    p['evidence'].append({'frame_id': 'f2', 'timestamp': 4.0, 'description': 'Second synthetic episode'})
    p['selection'].update(role='focus', pattern='repeated')
    p['selection']['outcome'] = {'status': 'observed', 'note': 'Synthetic visible effect', 'evidence': copy.deepcopy(p['evidence'])}
    assert reporting.validate_report(body, manifest)['priorities'][0]['selection']['role'] == 'focus'


def test_h5_packages_context_only_frames_and_retains_selection(session):
    from pathlib import Path
    from tennis_runtime import h5
    store, run, _, preview = session
    manifest = run['manifest']
    body = current_report(manifest)
    body['priorities'][0]['evidence'][0].update(frame_id='f1', timestamp=.5)
    body['priorities'][0]['selection']['comparison'] = {
        'status': 'context_only', 'note': 'Different conditions, no causal conclusion',
        'evidence': [{'frame_id': 'f2', 'timestamp': 1, 'description': 'Only present in comparison'}]}
    body = reporting.validate_report(body, manifest)
    run = store.update('runs', run['id'], report=body)
    before = h5.sha(preview)
    built = h5.build(store, run)
    data = load_page_data(built['directory'])
    assert (Path(built['directory']) / 'evidence/f2.jpg').exists()
    assert data['events'][0]['role'] == 'trial'
    assert data['report']['priorities'][0]['selection']['comparison']['status'] == 'context_only'
    assert h5.sha(preview) == before


def test_current_report_can_be_submitted_through_the_actual_web_route(server):
    client, headers, app, run = server
    manifest = client.get('/api/runs/' + run['id']).json()['manifest']
    result = client.post('/api/runs/' + run['id'] + '/report', json=current_report(manifest), headers=headers)
    assert result.status_code == 200
    saved = client.get('/api/runs/' + run['id']).json()
    assert saved['report']['priorities'][0]['selection']['role'] == 'trial'
