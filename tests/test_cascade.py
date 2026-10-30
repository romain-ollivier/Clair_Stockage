import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from clair_storage.scanner import scan
from clair_storage.browse import folders


class CascadeTests(unittest.TestCase):
    def test_cascade_and_live_root_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'A'/'B').mkdir(parents=True)
            (root/'A'/'B'/'deep').write_bytes(b'x'*50)
            (root/'A'/'direct').write_bytes(b'x'*20)
            (root/'rootfile').write_bytes(b'x'*30)
            updates=[]
            with patch('clair_storage.scanner.time.monotonic',side_effect=range(10000)):
                result=scan([root],threading.Event(),progress=updates.append,max_seconds=float('inf'))
            a=next(n for n in result.nodes if n.name=='A')
            self.assertEqual(a.total_bytes,70)
            self.assertEqual(result.nodes[1].total_bytes,100)
            self.assertTrue(any(any(e['name']=='A' and e['bytes']==70 for e in u['folders']) for u in updates))

    def test_unvisited_folder_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'A').mkdir()
            result=scan([tmp],threading.Event(),max_entries=1)
            entries=folders(result,1)
            self.assertEqual(len(entries),1)
            self.assertIsNone(entries[0].size)
            self.assertFalse(entries[0].complete)

    def test_breadth_first_visits_root_siblings_before_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['A','B']:
                (Path(tmp)/name/'deep').mkdir(parents=True)
            result=scan([tmp],threading.Event(),max_entries=4)
            siblings=[n for n in result.nodes if n.parent==1]
            self.assertTrue(all(n.scanned for n in siblings))
