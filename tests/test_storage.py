import json
import math
import os
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clair_storage import demo
from clair_storage.ai import LocalAdvisor, OllamaError
from clair_storage.layout import GIB, band, treemap
from clair_storage.report import describe, factual_report, validate_response, ai_report
from clair_storage.scanner import normalize_roots, scan


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'a').mkdir()
        (self.root/'a'/'nested').mkdir()
        (self.root/'b').mkdir()
        (self.root/'root.txt').write_bytes(b'x'*10)
        (self.root/'a'/'one.csv').write_bytes(b'x'*30)
        (self.root/'a'/'nested'/'two.csv').write_bytes(b'x'*20)
        (self.root/'b'/'image.png').write_bytes(b'x'*40)

    def tearDown(self):
        self.temp.cleanup()

    def run_scan(self, **kwargs):
        return scan([self.root], threading.Event(), **kwargs)

    def test_exact_sizes_nested_and_direct_files(self):
        result = self.run_scan()
        self.assertEqual(result.root.total_bytes, 100)
        self.assertEqual(result.root.files, 4)
        node = result.nodes[1]
        self.assertEqual(node.direct_bytes, 10)
        a = next(n for n in result.nodes if n.name == 'a')
        self.assertEqual(a.total_bytes, 50)
        self.assertEqual(a.direct_bytes, 30)
        self.assertTrue(a.complete)

    def test_extension_totals_and_counts(self):
        r = self.run_scan()
        self.assertEqual(r.root.extensions['.csv'], 50)
        self.assertEqual(r.root.extension_counts['.csv'], 2)
        self.assertEqual(sum(r.root.extensions.values()), 100)

    def test_parent_totals_are_partition_of_children_plus_direct(self):
        r = self.run_scan()
        for n in r.nodes:
            self.assertEqual(n.total_bytes, n.direct_bytes+sum(r.nodes[i].total_bytes for i in n.children))

    def test_scan_never_reads_file_content(self):
        with patch('builtins.open', side_effect=AssertionError('content opened')):
            r = self.run_scan()
        self.assertEqual(r.root.total_bytes, 100)

    def test_files_unchanged(self):
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_scan()
        after = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_cancel_returns_explicit_partial_result(self):
        stop = threading.Event()
        stop.set()
        r = scan([self.root], stop)
        self.assertEqual(r.reason, 'cancelled')
        self.assertFalse(r.root.complete)
        self.assertEqual(r.entries, 0)

    def test_entry_limit_is_partial(self):
        r = self.run_scan(max_entries=1)
        self.assertEqual(r.reason, 'entry_limit')
        self.assertFalse(r.root.complete)

    def test_directory_limit_is_partial(self):
        r = self.run_scan(max_directories=2)
        self.assertEqual(r.reason, 'directory_limit')
        self.assertFalse(r.root.complete)

    def test_time_limit_is_partial(self):
        r = self.run_scan(max_seconds=0)
        self.assertEqual(r.reason, 'time_limit')
        self.assertFalse(r.root.complete)

    def test_missing_root_is_not_an_empty_complete_folder(self):
        r = scan([self.root/'missing'], threading.Event())
        self.assertFalse(r.root.complete)
        self.assertEqual(r.root.errors, 1)
        self.assertTrue(r.error_examples)

    def test_access_denied_is_recorded(self):
        original = os.scandir
        def restricted(path):
            if os.fspath(path) == str(self.root/'a'):
                raise PermissionError('denied')
            return original(path)
        with patch('clair_storage.scanner.os.scandir', side_effect=restricted):
            r = self.run_scan()
        a = next(n for n in r.nodes if n.name == 'a')
        self.assertFalse(a.complete)
        self.assertEqual(a.errors, 1)
        self.assertEqual(r.root.total_bytes, 50)

    @unittest.skipIf(os.name == 'nt', 'Symlink privileges differ on Windows')
    def test_symlink_loops_resolve_without_double_counting(self):
        (self.root/'a'/'loop').symlink_to(self.root, target_is_directory=True)
        r = self.run_scan()
        self.assertEqual(r.root.total_bytes, 100)
        self.assertEqual(r.root.skipped, 0)
        self.assertTrue(r.root.complete)

    @unittest.skipIf(os.name == 'nt', 'Symlink privileges differ on Windows')
    def test_accessible_root_symlink_followed(self):
        with tempfile.TemporaryDirectory() as other:
            link = Path(other)/'link'
            link.symlink_to(self.root, target_is_directory=True)
            r = scan([link], threading.Event())
            self.assertEqual(r.root.total_bytes, 100)
            self.assertTrue(r.root.complete)

    def test_nested_roots_not_double_counted(self):
        self.assertEqual(normalize_roots([self.root/'a',self.root,self.root]),[str(self.root)])
        self.assertEqual(scan([self.root,self.root/'a'],threading.Event()).root.total_bytes,100)

    def test_largest_files_bounded(self):
        for i in range(25):
            (self.root/f'{i}.bin').write_bytes(b'x'*i)
        r = self.run_scan()
        self.assertEqual(len(r.nodes[1].largest_files),12)
        self.assertEqual(r.nodes[1].largest_files[0][0],24)

    def test_empty_folder_complete_with_zero_bytes(self):
        with tempfile.TemporaryDirectory() as empty:
            r=scan([empty],threading.Event())
            self.assertTrue(r.root.complete)
            self.assertEqual(r.root.total_bytes,0)


class GeometryTests(unittest.TestCase):
    def test_colors_have_absolute_thresholds(self):
        self.assertEqual(band(10*GIB)[0],'#e95a64')
        self.assertEqual(band(GIB)[0],'#ef9a46')
        self.assertEqual(band(100*1024**2)[0],'#d7bd49')
        self.assertEqual(band(1)[0],'#43a890')

    def test_rectangles_partition_area_without_overlap(self):
        rng=random.Random(9)
        for count in (1,2,5,20,50):
            items=[(str(i),rng.randint(1,10_000_000)) for i in range(count)]
            rects=treemap(items,0,0,700,330)
            self.assertEqual(len(rects),count)
            self.assertAlmostEqual(sum(w*h for _,x,y,w,h in rects),700*330,places=5)
            for i,(_,x,y,w,h) in enumerate(rects):
                self.assertGreater(w,0)
                self.assertGreater(h,0)
                self.assertLessEqual(x+w,700+1e-7)
                self.assertLessEqual(y+h,330+1e-7)
                for _,a,b,c,d in rects[i+1:]:
                    overlap=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
                    self.assertLess(overlap,1e-6)

    def test_rectangle_sizes_match_weights(self):
        items=[('a',10),('b',30),('c',60)]
        rects=treemap(items,0,0,100,100)
        areas={key:w*h for key,x,y,w,h in rects}
        self.assertAlmostEqual(areas['a'],1000)
        self.assertAlmostEqual(areas['b'],3000)
        self.assertAlmostEqual(areas['c'],6000)

    def test_empty_and_zero_weight(self):
        self.assertEqual(treemap([],0,0,10,10),[])
        self.assertEqual(treemap([('a',0)],0,0,10,10),[])
        self.assertEqual(treemap([('a',1)],0,0,0,10),[])


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.result=demo.example()
        self.snapshot=describe(self.result,1)

    def test_demo_label_and_partial_coverage_preserved(self):
        text=factual_report(self.snapshot)
        self.assertIn('données fictives',text)
        self.assertIn('PARTIEL',text)

    def test_file_names_opt_in(self):
        plain=json.dumps(self.snapshot,ensure_ascii=False)
        self.assertNotIn('exemple-fictif',plain)
        with_files=json.dumps(describe(self.result,1,True),ensure_ascii=False)
        self.assertIn('exemple-fictif',with_files)
        self.assertNotEqual(self.snapshot['snapshot_id'],describe(self.result,1,True)['snapshot_id'])

    def test_summary_bounded_and_references_exist(self):
        self.assertLessEqual(len(self.snapshot['folders']),12)
        self.assertLess(len(json.dumps(self.snapshot,ensure_ascii=False)),10000)
        for record in self.snapshot['folders']:
            node=self.result.nodes[int(record['id'][1:])]
            self.assertEqual(record['bytes'],node.total_bytes)
        self.assertTrue(self.snapshot['summary_limited'])

    def test_scope_root_is_not_exposed_as_absolute_path(self):
        self.assertEqual(self.snapshot['folders'][0]['folder'],'Dossier sélectionné')
        self.assertNotIn('C: (DÉMO)',self.snapshot['folders'][1]['folder'])

    def payload(self, entries=None, **changes):
        d={'snapshot_id':self.snapshot['snapshot_id'],'folders':entries or []}
        d.update(changes)
        return json.dumps(d)

    def entry(self, **changes):
        d={'id':self.snapshot['folders'][0]['id'],'hypothesis':'Les extensions suggèrent une composition mixte.', 'manual_check':'Examiner les sous-dossiers dominants pour préciser leur usage.'}
        d.update(changes)
        return d

    def test_valid_hypothesis_separated_from_measured_facts(self):
        v=validate_response(self.payload([self.entry()]),self.snapshot)
        self.assertEqual(len(v['accepted']),1)
        text=ai_report(self.snapshot,v)
        self.assertIn('HYPOTHÈSES NON VÉRIFIÉES',text)
        self.assertIn('BILAN MESURÉ',text)

    def test_unknown_folder_and_stale_snapshot_rejected(self):
        v=validate_response(self.payload([self.entry(id='D99999')]),self.snapshot)
        self.assertEqual(v['rejected'],1)
        self.assertFalse(validate_response(self.payload(snapshot_id='stale'),self.snapshot)['valid'])

    def test_generated_numbers_and_deletion_proposals_rejected(self):
        for fields in ({'hypothesis':'Il reste 42 Go.'},{'manual_check':'Supprimer les dossiers système.'},{'manual_check':'powershell Remove-Item dossier'}):
            v=validate_response(self.payload([self.entry(**fields)]),self.snapshot)
            self.assertEqual(v['accepted'],[])
            self.assertEqual(v['rejected'],1)

    def test_raw_invalid_answer_never_rendered(self):
        raw='FAUX CONSEIL MALVEILLANT'
        v=validate_response(raw,self.snapshot)
        self.assertNotIn(raw,ai_report(self.snapshot,v))

    def test_duplicate_entries_and_keys_rejected(self):
        entry=self.entry()
        self.assertEqual(validate_response(self.payload([entry,entry]),self.snapshot)['rejected'],1)
        raw=self.payload()[:-1]+',"snapshot_id":"bad"}'
        self.assertFalse(validate_response(raw,self.snapshot)['valid'])

    def test_extra_fields_or_wrong_types_rejected(self):
        for entry in (None,self.entry(command='exec'),self.entry(id=[]),self.entry(hypothesis=123)):
            self.assertEqual(validate_response(self.payload([entry]),self.snapshot)['rejected'],1)
        for raw in ('null','[]','x'*12001,'['*1200+']'*1200):
            self.assertFalse(validate_response(raw,self.snapshot)['valid'])

    def test_ai_transport_is_local_plain_text_and_has_no_tools(self):
        a=LocalAdvisor()
        content='Les extensions suggèrent une composition mixte ; vérifier l’usage des dossiers.'
        with patch.object(a,'start'),patch.object(a,'models',return_value=['local:8b']),patch.object(a,'request',return_value={'message':{'content':content}}) as request:
            r=a.analyze('local:8b',self.snapshot)
        self.assertEqual(r['interpretation'],content)
        payload=request.call_args.args[1]
        self.assertNotIn('tools',payload)
        self.assertEqual(payload['keep_alive'],0)
        self.assertNotIn('format',payload)
        self.assertFalse(payload['think'])

    def test_uninstalled_model_not_downloaded(self):
        a=LocalAdvisor()
        with patch.object(a,'start'),patch.object(a,'models',return_value=[]),patch.object(a,'request') as request:
            with self.assertRaises(OllamaError):a.analyze('remote:cloud',self.snapshot)
            request.assert_not_called()

    def test_close_kills_private_job_only(self):
        a=LocalAdvisor()
        job,process=Mock(),Mock()
        process.poll.return_value=None
        a.job,a.process=job,process
        a.close()
        job.close.assert_called_once()
        process.kill.assert_called_once()


class UIControllerTests(unittest.TestCase):
    def test_constructor_defers_widget_access_until_build(self):
        from clair_storage.app import StorageApp
        root=Mock()
        with patch.object(StorageApp,'styles'),patch.object(StorageApp,'build'):
            app=StorageApp(root)
        self.assertFalse(app.scanning)
        self.assertIsNone(app.result)
        root.after.assert_called_once()

    def test_new_scan_clears_old_scope_and_results(self):
        from clair_storage.app import StorageApp
        app=StorageApp.__new__(StorageApp)
        app.scanning=app.ai_busy=False
        app.rows={}
        app.stop_listing=threading.Event()
        app.list_generation=0
        app.list=Mock()
        app.title=Mock();app.summary=Mock();app.address=Mock()
        app.last_snapshot={'old':'data'}
        app.last_ai={'old':'answer'}
        app.card_values={'bytes':Mock()}
        for name in ('tree','table','detail_title','composition','detail_text','ai_text','preview_text','cancel_button','ai_button','export_button','progress','location','status'):
            setattr(app,name,Mock())
        app.tree.get_children.return_value=[]
        app.table.get_children.return_value=[]
        app.put=Mock()
        app.work=Mock()
        app.draw_map=Mock()
        app.begin_scan(['C:\\'])
        self.assertTrue(app.scanning)
        self.assertIsNone(app.result)
        self.assertIsNone(app.last_snapshot)
        self.assertEqual(app.visible,[])
        app.work.assert_called_once()

    def test_close_cancels_scan_and_private_ai(self):
        from clair_storage.app import StorageApp
        app=StorageApp.__new__(StorageApp)
        app.closed=False
        app.stop_scan=threading.Event()
        app.stop_listing=threading.Event()
        app.advisor=Mock()
        app.root=Mock()
        app.close()
        self.assertTrue(app.stop_scan.is_set())
        app.advisor.close.assert_called_once()
        app.root.destroy.assert_called_once()


class AdditionalReportTests(unittest.TestCase):
    def test_ce_pc_summary_uses_relative_names_for_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root'
            (root/'child').mkdir(parents=True)
            (root/'child'/'x.bin').write_bytes(b'abc')
            r=scan([root],threading.Event())
            data=describe(r,0)
            encoded=json.dumps(data,ensure_ascii=False)
            self.assertNotIn(folder,encoded)
            self.assertTrue(any('child' in f['folder'] for f in data['folders']))

    def test_known_numeric_extension_is_not_an_invented_quantity(self):
        r=demo.example()
        video=next(n for n in r.nodes if n.name=='Vidéos')
        snapshot=describe(r,video.id)
        raw=json.dumps({'snapshot_id':snapshot['snapshot_id'],'folders':[{
            'id':f'D{video.id}', 'hypothesis':'Les formats MP4 suggèrent des vidéos.',
            'manual_check':'Examiner les fichiers pour confirmer leur contenu.'}]})
        v=validate_response(raw,snapshot)
        self.assertEqual(len(v['accepted']),1)


if __name__=='__main__':
    unittest.main()
