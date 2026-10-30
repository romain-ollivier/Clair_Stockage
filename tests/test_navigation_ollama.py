import json
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch,Mock

from clair_storage.ai import LocalAdvisor,OllamaError
from clair_storage.browse import Entry,Navigation,list_directory,sorted_entries
from clair_storage.scanner import scan
from clair_storage.demo import example
from clair_storage.report import describe


class BrowserTests(unittest.TestCase):
    def test_back_forward_and_new_branch(self):
        n=Navigation(1)
        n.visit(2);n.visit(3)
        self.assertEqual(n.back(),2)
        self.assertEqual(n.forward(),3)
        n.back();n.visit(4)
        self.assertEqual(n.history,[1,2,4])
        self.assertEqual(n.forward(),4)

    def test_same_location_does_not_duplicate_history(self):
        n=Navigation(0);n.visit(0)
        self.assertEqual(n.history,[0])
        self.assertEqual(n.back(),0)

    def test_listing_contains_all_direct_files_not_only_top_twelve(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for i in range(35):(root/f'{i}.bin').write_bytes(b'x'*i)
            (root/'child').mkdir()
            r=scan([root],threading.Event())
            entries,note=list_directory(r,1,threading.Event())
            self.assertEqual(len([e for e in entries if e.kind=='file']),35)
            self.assertEqual(len([e for e in entries if e.kind=='folder']),1)
            self.assertFalse(note)

    def test_new_file_or_folder_since_scan_is_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);r=scan([root],threading.Event())
            (root/'new.txt').write_bytes(b'abc');(root/'newdir').mkdir()
            entries,_=list_directory(r,1,threading.Event())
            self.assertEqual({e.name for e in entries},{'new.txt','newdir'})
            new=next(e for e in entries if e.kind=='folder')
            self.assertIsNone(new.size);self.assertIsNone(new.node_id)

    def test_listing_limit_and_no_content_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for i in range(5):(root/str(i)).write_bytes(b'x')
            r=scan([root],threading.Event())
            with patch('builtins.open',side_effect=AssertionError('content read')):
                entries,note=list_directory(r,1,threading.Event(),limit=3)
            self.assertEqual(len(entries),3)
            self.assertIn('limitée',note)

    def test_sort_has_folders_first_and_numeric_sizes(self):
        entries=[Entry('1','small',2,'file',''),Entry('2','large',100,'file',''),Entry('3','folder',1,'folder',''),Entry('4','unknown',None,'folder','')]
        self.assertEqual([e.name for e in sorted_entries(entries)],['folder','unknown','large','small'])
        self.assertEqual([e.name for e in sorted_entries(entries,'LAR')],['large'])

    def test_file_double_click_never_opens_document(self):
        from clair_storage.app import StorageApp
        app=StorageApp.__new__(StorageApp)
        app.select_entry=Mock();app.navigate=Mock();app.begin_scan=Mock()
        entry=Entry('file','document.exe',42,'file','document.exe')
        app.scanning=False
        app.open_entry(entry)
        app.select_entry.assert_called_once_with(entry)
        app.navigate.assert_not_called();app.begin_scan.assert_not_called()


class OllamaHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,payload):
                body=json.dumps(payload).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_GET(self):
                if self.path=='/api/version':self.reply(200,{'version':'test-local'})
                elif self.path=='/api/tags':self.reply(200,{'models':[{'name':'qwen3:8b'},{'name':'remote:cloud','remote_host':'cloud'}]})
                else:self.reply(404,{'error':'unknown endpoint'})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.calls.append(body)
                if self.server.reject_think and 'think' in body:self.reply(400,{'error':'think is not supported'})
                elif self.server.fail_status:self.reply(self.server.fail_status,{'error':self.server.fail_message})
                elif self.server.empty:self.reply(200,{'message':{'content':'','thinking':'unfinished'}})
                else:self.reply(200,{'message':{'content':'Les dossiers dominants semblent contenir des vidéos et des fichiers applicatifs. Cette interprétation reste à vérifier.'}})
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def setUp(self):
        self.server.calls=[];self.server.reject_think=False;self.server.fail_status=None;self.server.empty=False
        self.server.fail_message=''
        self.advisor=LocalAdvisor(default_port=self.server.server_address[1])
        self.snapshot=describe(example(),1,max_nodes=8)

    def tearDown(self):self.advisor.close()

    def test_existing_server_is_reused_without_starting_another_process(self):
        with patch('clair_storage.ai.subprocess.Popen') as spawn:
            diagnosis=self.advisor.diagnose()
        spawn.assert_not_called()
        self.assertTrue(self.advisor.external)
        self.assertEqual(diagnosis['models'],['qwen3:8b'])
        self.assertIn('test-local',diagnosis['connection'])

    def test_end_to_end_plain_answer_and_measured_report(self):
        result=self.advisor.analyze('qwen3:8b',self.snapshot)
        self.assertIn('BILAN MESURÉ',result['text'])
        self.assertIn('INTERPRÉTATION IA',result['text'])
        self.assertIn('vidéos',result['interpretation'])
        body=self.server.calls[-1]
        self.assertEqual(body['options']['num_ctx'],4096)
        self.assertFalse(body['think']);self.assertNotIn('format',body);self.assertNotIn('tools',body)

    def test_multi_pass_over_real_local_http(self):
        from clair_storage.exploration import explore,attach,batches
        snapshot=attach(self.snapshot,explore(example(),1))
        result=self.advisor.analyze('qwen3:8b',snapshot)
        self.assertEqual(len(self.server.calls),len(batches(snapshot['exploration']))+1)
        self.assertEqual(result['mode'],'multi_pass_metadata_no_actions')
        self.assertIn('bilan final',self.server.calls[-1]['messages'][1]['content'])
        self.assertTrue(all(call['options']['num_ctx']==4096 for call in self.server.calls))

    def test_older_engine_retries_without_optional_thinking_flag(self):
        self.server.reject_think=True
        result=self.advisor.analyze('qwen3:8b',self.snapshot)
        self.assertTrue(result['interpretation'])
        self.assertEqual(len(self.server.calls),2)
        self.assertNotIn('think',self.server.calls[-1])

    def test_memory_error_is_specific(self):
        self.server.fail_status=500;self.server.fail_message='model requires more system memory'
        with self.assertRaises(OllamaError) as caught:self.advisor.analyze('qwen3:8b',self.snapshot)
        self.assertIn('mémoire insuffisante',str(caught.exception))
        self.assertEqual(caught.exception.status,500)

    def test_http_error_body_is_preserved(self):
        self.server.fail_status=503;self.server.fail_message='runner unavailable for testing'
        with self.assertRaises(OllamaError) as caught:self.advisor.analyze('qwen3:8b',self.snapshot)
        self.assertIn('runner unavailable',str(caught.exception))

    def test_no_final_answer_is_explained(self):
        self.server.empty=True
        with self.assertRaises(OllamaError) as caught:self.advisor.analyze('qwen3:8b',self.snapshot)
        self.assertIn('sans réponse finale',str(caught.exception))

    def test_close_does_not_stop_external_ollama_server(self):
        self.advisor.diagnose();self.advisor.close()
        self.assertTrue(self.thread.is_alive())
        fresh=LocalAdvisor(default_port=self.server.server_address[1])
        try:self.assertEqual(fresh.diagnose()['models'],['qwen3:8b'])
        finally:fresh.close()


class RenderingTests(unittest.TestCase):
    def test_list_renders_only_visible_rows(self):
        from clair_storage.widgets import ExplorerList
        view=ExplorerList.__new__(ExplorerList)
        view.entries=[Entry(str(i),'fichier-'+str(i),i,'file','') for i in range(50_000)]
        view.total=sum(e.size for e in view.entries);view.selected=None
        view.canvas=Mock();view.header=Mock()
        view.canvas.winfo_width.return_value=850
        view.canvas.winfo_height.return_value=300
        view.canvas.canvasy.return_value=0
        view.font=Mock();view.font.measure.side_effect=lambda s:len(s)*7
        view.bold=view.small=view.font
        view.draw()
        self.assertLess(view.canvas.create_text.call_count,100)
        self.assertGreater(view.canvas.create_text.call_count,0)

    def test_old_directory_result_cannot_replace_new_view(self):
        import queue
        from clair_storage.app import StorageApp
        app=StorageApp.__new__(StorageApp)
        app.closed=False;app.list_generation=4
        app.events=queue.Queue();app.events.put(('listing',(3,[],'')))
        app.root=Mock();app.render_entries=Mock()
        app.drain()
        app.render_entries.assert_not_called()

    def test_model_context_is_small_and_scoped(self):
        from clair_storage.ai import model_context
        snapshot=describe(example(),1,max_nodes=12)
        context=model_context(snapshot)
        self.assertLessEqual(len(context['folders']),6)
        self.assertEqual(context['snapshot_id'],snapshot['snapshot_id'])
        self.assertTrue(context['summary_limited'])
