import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from clair_storage.exploration import explore,attach,batches
from clair_storage.scanner import scan
from clair_storage.report import describe
from clair_storage.ai import LocalAdvisor,Cancelled


class ExplorationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'Surf_Project'/'node_modules').mkdir(parents=True)
        (self.root/'Surf_Project'/'package.json').write_text('SECRET FILE CONTENT')
        (self.root/'Documents').mkdir()
        (self.root/'Documents'/'facture.pdf').write_bytes(b'x'*120)
        self.result=scan([self.root],threading.Event())

    def test_markers_names_sizes_without_content_read(self):
        with patch('builtins.open',side_effect=AssertionError('No content read')):
            evidence=explore(self.result,1)
        project=next(f for f in evidence['folders'] if f['name']=='Surf_Project')
        self.assertIn('package.json',[m['name'] for m in project['markers']])
        self.assertIn('node_modules',[c['name'] for c in project['children']])
        self.assertNotIn('SECRET FILE CONTENT',json.dumps(evidence))
        self.assertEqual(evidence['folder_count'],4)

    def test_names_opt_out_does_not_enumerate_files(self):
        with patch('clair_storage.exploration.os.scandir',side_effect=AssertionError('No listing')):
            evidence=explore(self.result,1,include_files=False)
        for folder in evidence['folders']:
            self.assertNotIn('sample_names',folder)
            self.assertNotIn('largest_files',folder)
            self.assertEqual(folder['markers'],[])

    def test_folder_and_name_limits_are_explicit(self):
        evidence=explore(self.result,1,max_nodes=2,per_directory=1)
        self.assertEqual(evidence['folder_count'],2)
        self.assertTrue(evidence['limited'])
        self.assertTrue(any('limité' in f.get('name_sample_note','') for f in evidence['folders']))

    def test_cancel_exploration(self):
        stop=threading.Event();stop.set()
        with self.assertRaises(Cancelled):explore(self.result,1,stop=stop)

    def test_multistage_analysis_sends_evidence_then_synthesis(self):
        snapshot=describe(self.result,1,include_files=True)
        snapshot=attach(snapshot,explore(self.result,1))
        advisor=LocalAdvisor();advisor.start=Mock();advisor.models=Mock(return_value=['local'])
        advisor.generate=Mock(return_value='Projet Node.js probable [D2], confiance moyenne, au vu de package.json.')
        progress=[]
        result=advisor.analyze('local',snapshot,progress=progress.append)
        self.assertEqual(advisor.generate.call_count,len(batches(snapshot['exploration']))+1)
        prompts=[c.args[1] for c in advisor.generate.call_args_list]
        self.assertIn('package.json',prompts[0])
        self.assertIn('hypothèses non vérifiées',prompts[-1])
        self.assertEqual(result['model_folder_count'],4)
        self.assertEqual(result['mode'],'multi_pass_metadata_no_actions')
        self.assertTrue(progress)
        self.assertEqual(result['snapshot']['snapshot_id'],snapshot['snapshot_id'])
