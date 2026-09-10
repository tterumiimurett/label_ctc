import json, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
from prolific.ctc_verification_app.activation import ActionJournal, ActivationController

class Ticket08Test(unittest.TestCase):
 def setup(self, production=False):
  d=tempfile.TemporaryDirectory(); root=Path(d.name); journal=ActionJournal(root/'actions.jsonl')
  trigger=Mock(); trigger.periodic.return_value={'report':{'status':'ok','writes_performed':False,'submissions':[]}}
  adapter=Mock(); adapter.reconcile.return_value={'status':'ok','submissions':[]}
  return d,root,ActivationController(trigger=trigger,store=Mock(),ledger=Mock(),adapter=adapter,journal=journal,study_id='STUDY',production_enabled=production)
 def test_provenance_is_durable_and_unknown_is_manual(self):
  d,r,c=self.setup(); self.assertEqual(c.derive_candidate_origin({'run_kind':'event','event_id':'E'}),'new'); self.assertEqual(c.derive_candidate_origin({'run_kind':'backfill','historical_snapshot':True}),'historical'); self.assertEqual(c.derive_candidate_origin({'run_kind':'manual'}),'unknown'); d.cleanup()
 def test_journal_is_intent_before_effect_and_kill_switch_is_shared(self):
  d,r,c=self.setup(); event=c.journal.begin('archive',{'session_id':'S'}); self.assertTrue(event); self.assertEqual(json.loads((r/'actions.jsonl').read_text())['kind'],'intent'); c.journal.disable('stop'); self.assertIsNone(c.journal.begin('archive',{})); d.cleanup()
 def test_production_requires_explicit_approval(self):
  d,r,c=self.setup(True)
  with self.assertRaises(PermissionError): c.execute(provenance_context={'run_kind':'event','event_id':'E'})
  d.cleanup()
 def test_preview_uses_actual_action_name(self):
  d,r,c=self.setup(); out=c.preview({'submissions':[{'session_id':'S','study_id':'STUDY','participant_id':'P','proposed_action':'release_claim_proposal'}]}); self.assertEqual(out['actions'][0]['action'],'release_claim'); d.cleanup()
if __name__=='__main__': unittest.main()
