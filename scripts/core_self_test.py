import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from electionlab.core.simulation import ElectionEngine, SimulationConfig
from electionlab.core.simulation_archive import SimulationArchive
from electionlab.core.settings import SettingsManager
from electionlab.core.database import KnowledgeVault
from electionlab.core.campaigns import CampaignManager
from electionlab.core.campaign_engine import CampaignEngine
from electionlab.core.state_agents import StateAgentModel
from electionlab.core.diagnostics import SessionDiagnostics
from electionlab.core.rules import RULE_PRESETS, preset_rules, modified_from_preset, campaign_rules, enabled as rule_enabled
from electionlab.providers.openai_provider import OpenAIResearchProvider
from electionlab.data.seed_profiles import built_in_profiles, PRESIDENTS, PUBLIC_FIGURES
from electionlab.providers.photo_service import PhotoService

assert len(PRESIDENTS) == 45
assert len(PUBLIC_FIGURES) == 50
assert len(built_in_profiles()) == 95
engine = ElectionEngine()
assert sum(x['ev'] for x in engine.states) == 538
agents = StateAgentModel()
assert len(agents.states) == 51
assert agents.states['MO']['median_household_income'] > 0
assert agents.states['CA']['median_gross_rent'] > 0

map_asset = json.loads((Path(__file__).resolve().parents[1] / 'electionlab' / 'data' / 'us_map_paths.json').read_text(encoding='utf-8'))
map_codes = {item['code'] for item in map_asset['paths']}
state_codes = {x['code'] for x in engine.states}
assert len(map_codes) == 51
assert map_codes == state_codes
raster_root=Path(__file__).resolve().parents[1] / 'electionlab' / 'data' / 'map_raster_v2'
raster_manifest=json.loads((raster_root/'manifest.json').read_text(encoding='utf-8'))
assert set(raster_manifest['states']) == state_codes
assert set(raster_manifest['code_to_index']) == state_codes
assert set(raster_manifest['index_to_code'].values()) == state_codes
assert (raster_root/'state_indexed.bin').stat().st_size == raster_manifest['width'] * raster_manifest['height']
assert (raster_root/'outline.png').exists()
assert all((raster_root/'states'/f'{code}.png').exists() for code in state_codes)


# 0.11 game rules: official presets are independent deep copies and modified
# campaigns can disable major systems without changing global settings.
rules_a=preset_rules('Campaign'); rules_b=preset_rules('Campaign')
assert rules_a == rules_b and rules_a is not rules_b
rules_a['campaign']['debates']=False
assert modified_from_preset('Campaign', rules_a) and preset_rules('Campaign')['campaign']['debates'] is True
assert {'Arcade','Campaign','Simulation','Analytical','Forecast Lab'} <= set(RULE_PRESETS)
old_rules_save={'rules_preset':'Campaign','rules':{'campaign':{'debates':False}}}
merged_rules=campaign_rules(old_rules_save)
assert merged_rules['campaign']['debates'] is False and merged_rules['campaign']['media'] is True and merged_rules['campaign']['field'] is True
factors = {k: True for k in ['historical_baseline','candidate_personality','debates','experience','name_recognition','home_state','random_uncertainty']}
a = {'canonical_name':'Test A','display_name':'Test A / VP','party':'Democratic','home_state':'IL','vp_home_state':'MI','national_appeal':0,'charisma':50,'debate_skill':50,'experience':50,'name_recognition':50}
b = {'canonical_name':'Test B','display_name':'Test B / VP','party':'Republican','home_state':'FL','vp_home_state':'OH','national_appeal':0,'charisma':50,'debate_skill':50,'experience':50,'name_recognition':50}
cfg = SimulationConfig('Analytical 2', 500, 'SELF-TEST-SEED', factors)
progress=[]
r1 = engine.run(a,b,cfg,lambda pct,msg: progress.append((pct,msg))); r2 = engine.run(a,b,cfg)
assert r1['expected_ev_a'] == r2['expected_ev_a']
assert abs(r1['expected_ev_a'] + r1['expected_ev_b'] - 538) < 1e-9
assert r1['states'][0].get('reason')
assert r1.get('local_overview')
assert r1.get('insights',{}).get('closest_state')
assert r1.get('insights',{}).get('tipping_point')
assert progress and progress[-1][0] == 100
# State adjustments must actually feed the final election model.
base_pa = next(x for x in r1['states'] if x['code'] == 'PA')['avg_margin_a']
adj_cfg = SimulationConfig('Analytical 2', 500, 'SELF-TEST-SEED', factors, state_adjustments={'PA': 3.0})
adj_r = engine.run(a,b,adj_cfg)
adj_pa = next(x for x in adj_r['states'] if x['code'] == 'PA')['avg_margin_a']
assert 2.99 < (adj_pa - base_pa) < 3.01

# 0.4 persistence tests: deletions/tombstones, campaign deletion, debate ledger effect.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    config = root / 'portable_config.json'
    config.write_text(json.dumps({'data_root': str(root / 'data')}), encoding='utf-8')
    settings = SettingsManager(config)
    legacy_cfg=root/'legacy_config.json'; legacy_cfg.write_text(json.dumps({'data_root':str(root/'legacy-data'),'openai_model':'GPT-5.4-mini'}),encoding='utf-8')
    legacy_settings=SettingsManager(legacy_cfg)
    assert legacy_settings.settings.openai_model=='gpt-5.4-mini'
    legacy_settings.update(openai_model=' GPT-5.4-MINI ')
    assert legacy_settings.settings.openai_model=='gpt-5.4-mini'
    assert OpenAIResearchProvider('GPT-5.4-mini', api_key='test').model == 'gpt-5.4-mini'
    diag=SessionDiagnostics(settings.path_for('Logs'),'self-test')
    diag.set_ui_action('test-action'); diag.ui_heartbeat(999.0); diag.log('INFO','SELF_TEST_DIAGNOSTIC'); diag.close()
    log_text=(settings.path_for('Logs')/'latest_session.log').read_text(encoding='utf-8')
    assert 'SESSION_START' in log_text and 'SELF_TEST_DIAGNOSTIC' in log_text
    vault = KnowledgeVault(settings)
    archive = SimulationArchive(settings)
    saved_result = archive.save(r1, 'Self Test Election')
    assert Path(saved_result['_path']).exists()
    assert archive.list() and archive.list()[0]['result']['seed'] == 'SELF-TEST-SEED'
    assert archive.delete(archive.list()[0])
    vault.seed_profiles(built_in_profiles(), 'self-test-seed-1')
    assert vault.get_profile('Abraham Lincoln') is not None
    # 0.10 starter-pack upgrades may refresh starter-owned records but must not
    # replace a profile once the user/research pipeline owns it.
    madison=vault.get_profile('James Madison'); assert madison and madison['profile_status']=='starter_enriched'
    researched=dict(madison); researched['source_type']='openai_web_research'; researched['profile_status']='researched'; researched['charisma']=13
    vault.upsert_profile(researched)
    seed_update=next(dict(x) for x in built_in_profiles() if x['canonical_name']=='James Madison'); seed_update['charisma']=99
    vault.seed_profiles([seed_update], 'self-test-seed-1b')
    assert vault.get_profile('James Madison')['charisma']==13
    assert vault.delete_profile('Abraham Lincoln')
    assert vault.get_profile('Abraham Lincoln') is None
    # A later seed version must respect the user's deletion tombstone.
    vault.seed_profiles(built_in_profiles(), 'self-test-seed-2')
    assert vault.get_profile('Abraham Lincoln') is None
    # Explicitly re-adding clears the tombstone.
    lincoln = next(p for p in built_in_profiles() if p['canonical_name'] == 'Abraham Lincoln')
    vault.upsert_profile(lincoln)
    assert vault.get_profile('Abraham Lincoln') is not None

    campaigns = CampaignManager(settings)
    camp = campaigns.create('Self Test Campaign', {
        'seed':'TEST-CAMP','detail_level':'Weekly','agency':'Play Ticket A',
        'ticket_a':{'president':'Test A','vp':None}, 'ticket_b':{'president':'Test B','vp':None},
    })
    ce = CampaignEngine(); ce.ensure_state(camp)
    before_ga = camp['state_opinion']['GA']['support_delta_a']
    before_ca = camp['state_opinion']['CA']['support_delta_a']
    state_effect = ce.state_agents.apply_strategy(camp, 'A', {'region':'South','message':'Economy','tone':'Positive'})
    assert camp['state_opinion']['GA']['support_delta_a'] > before_ga
    assert camp['state_opinion']['CA']['support_delta_a'] == before_ca
    assert state_effect['states_touched'] >= 10
    constituent = ce.state_agents.constituent_context(camp, 'GA')
    assert constituent['state_code'] == 'GA' and constituent['issue']
    assert constituent.get('campaign_reaction') and 'Ticket A' in constituent['campaign_reaction']
    # 0.9 focused state operations must move only the chosen state and deduct funds.
    funds_before=camp['funds_a']; pa_before=camp['state_opinion']['PA']['support_delta_a']; ca_before=camp['state_opinion']['CA']['support_delta_a']
    op=ce.run_state_operation(camp,'A','PA','Town Hall','Economy')
    assert op['state']=='PA' and camp['funds_a'] < funds_before
    assert camp['state_opinion']['PA']['support_delta_a'] > pa_before
    assert camp['state_opinion']['CA']['support_delta_a'] == ca_before
    assert camp['timeline'][-1]['type']=='state_operation'
    # 0.12 campaign operations are deterministic save-local gameplay systems.
    funds_before=camp['funds_a']
    fundraiser=ce.run_campaign_operation(camp,'A','Fundraising Drive','National','Economy','Positive')
    assert fundraiser['type']=='campaign_operation' and fundraiser['funds_gained'] > 0 and camp['funds_a'] > funds_before
    ga_before=camp['state_opinion']['GA']['support_delta_a']; funds_before=camp['funds_a']
    media=ce.run_campaign_operation(camp,'A','Media Buy','South','Cost of living','Contrast')
    assert media['operation']=='Media Buy' and camp['funds_a'] < funds_before
    assert camp['state_opinion']['GA']['support_delta_a'] != ga_before
    assert camp['timeline'][-1]['type']=='campaign_operation'
    # Poll snapshots are deterministic noisy observations of the latent state pulse.
    poll1=ce.generate_poll_snapshot(camp,force=True)
    import copy as _copy
    poll_clone=_copy.deepcopy(camp)
    # Reset clone to the state before another manual snapshot, including sequence.
    poll_clone['polling_history']=poll_clone['polling_history'][:-1]
    poll_clone['poll_sequence']=poll1['sequence']-1
    poll2=ce.generate_poll_snapshot(poll_clone,force=True)
    assert poll1['polls']==poll2['polls'] and poll1['fictional_simulation_poll']
    assert all('poll_margin_a' in row and 'latent_margin_a' in row for row in poll1['polls'])
    before = camp['momentum_a']
    ce.apply_debate_result(camp, {
        'user_side':'A','user_momentum_delta':0.8,'question':'Test?','user_score':70,'opponent_score':60,
        'notable_moment':'Test debate','recorded_at':'2026-08-26T00:00:00+00:00'
    })
    assert camp['momentum_a'] > before
    assert camp['debates'] and camp['timeline'][-1]['type'] == 'debate_exchange'
    campaigns.save(camp)
    assert campaigns.delete(camp)

    # 0.5 seed contract: save UUID must not affect campaign randomness.
    base_payload = {
        'seed':'REPLAY-SEED','detail_level':'Weekly','agency':'Spectate',
        'ticket_a':{'president':'Test A','vp':'VP A'}, 'ticket_b':{'president':'Test B','vp':'VP B'},
    }
    c1 = campaigns.create('Replay One', dict(base_payload))
    c2 = campaigns.create('Replay Two', dict(base_payload))
    # The IDs are intentionally different; the generated universe should still match.
    assert c1['id'] != c2['id']
    ce.ensure_state(c1); ce.ensure_state(c2)
    e1 = ce.advance(c1, 'Weekly', {'region':'National','message':'Economy','tone':'Positive'})
    e2 = ce.advance(c2, 'Weekly', {'region':'National','message':'Economy','tone':'Positive'})
    assert e1['events'] == e2['events']
    assert c1['momentum_a'] == c2['momentum_a'] and c1['momentum_b'] == c2['momentum_b']

    # Timeline milestones should interrupt advancement and require resolution.
    scheduled = campaigns.create('Milestone Test', {
        'seed':'MILESTONE','detail_level':'Debate-to-Debate','agency':'Spectate',
        'ticket_a':{'president':'Test A','vp':None}, 'ticket_b':{'president':'Test B','vp':None},
    })
    ce.ensure_state(scheduled)
    ce.advance(scheduled, 'Debate-to-Debate', {'region':'National','message':'Economy','tone':'Positive'})
    assert scheduled.get('pending_event') and scheduled['pending_event']['type'] == 'debate'
    assert scheduled['status'] == 'event_pending'
    ce.skip_pending_event(scheduled)
    assert scheduled.get('pending_event') is None
    assert any(x.get('status') == 'skipped' for x in scheduled['schedule'])

    # 0.6 Instant Election policy: auto/skip can bypass all debates and reach Election Day.
    instant = campaigns.create('Instant Test', {
        'seed':'INSTANT-SEED','detail_level':'Instant Election','agency':'Spectate',
        'ticket_a':{'president':'Test A','vp':None}, 'ticket_b':{'president':'Test B','vp':None},
    })
    ce.ensure_state(instant)
    auto_records=ce.fast_forward_debate_policy(instant,'auto',a,b)
    assert len(auto_records) == 3
    ce.advance(instant,'Instant Election',{'region':'National','message':'Economy','tone':'Positive'})
    assert instant['status'] == 'election_day_ready'
    assert all(x['status'] != 'scheduled' for x in instant['schedule'] if x['type']=='debate')

    # 0.7 settings contract: campaign-history narration preference must persist.
    settings.update(campaign_history_provider="OpenAI — testing override")
    reloaded = SettingsManager(config)
    assert reloaded.settings.campaign_history_provider == "OpenAI — testing override"

    # 0.7 portrait disambiguation: a qualified identity page should beat an unrelated Drake page.
    drake_good = {"title":"Drake (musician)", "thumbnail":{"source":"https://example.invalid/drake.jpg"}}
    drake_bad = {"title":"Drake (surname)", "thumbnail":{"source":"https://example.invalid/surname.jpg"}}
    assert PhotoService._score_page("Drake", "musician", drake_good) > PhotoService._score_page("Drake", "musician", drake_bad)

    # 0.11 save-local rules: disabled debates must not interrupt time, disabled
    # polling must not create snapshots, and resources can be disabled per save.
    custom_rules=preset_rules('Campaign'); custom_rules['campaign']['debates']=False; custom_rules['campaign']['polling']=False; custom_rules['campaign']['resources']=False; custom_rules['campaign']['media']=False
    ruled = campaigns.create('Rules Test', {
        'seed':'RULES-SEED','detail_level':'Debate-to-Debate','agency':'Play Ticket A',
        'rules_preset':'Campaign','rules_modified':True,'rules':custom_rules,
        'ticket_a':{'president':'Test A','vp':None}, 'ticket_b':{'president':'Test B','vp':None},
    })
    ce.ensure_state(ruled)
    assert all(x.get('status')=='disabled' for x in ruled['schedule'] if x.get('type')=='debate')
    assert ce.generate_poll_snapshot(ruled, force=True).get('disabled')
    funds_before=ruled['funds_a']; ce.run_state_operation(ruled,'A','PA','Rally','Economy'); assert ruled['funds_a']==funds_before
    try:
        ce.run_campaign_operation(ruled,'A','Media Buy','South','Economy','Positive')
        raise AssertionError('disabled media buy should fail')
    except RuntimeError:
        pass
    assert rule_enabled(ruled,'campaign','debates',True) is False

    # Clean up remaining self-test campaigns.
    for saved in campaigns.list():
        campaigns.delete(saved)
    assert not campaigns.list()

print('ElectionLab core self-test PASSED')
print(f"Profiles: 95 | EV: 538 | map shapes: 51 | deterministic expected EV A: {r1['expected_ev_a']:.2f} | campaign replay + raster map + diagnostics + safe starter enrichment + state/campaign operations + polling + rulesets + result intelligence: OK")
