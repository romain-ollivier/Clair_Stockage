import os
import tempfile
import threading
import unittest
from pathlib import Path
from clair_storage.scanner import scan
from clair_storage.browse import folders,list_directory


class FullScanTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','Liens nécessitant des privilèges Windows')
    def test_external_directory_link_measured_and_browsable(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target:
            (Path(target)/'payload').write_bytes(b'x'*123)
            (Path(root)/'linked').symlink_to(target,target_is_directory=True)
            result=scan([root],threading.Event())
            self.assertEqual(result.root.total_bytes,123)
            self.assertTrue(result.root.complete)
            self.assertEqual(folders(result,1)[0].size,123)
            entries,_=list_directory(result,1,threading.Event())
            self.assertEqual(len(entries),1)

    @unittest.skipIf(os.name=='nt','Liens nécessitant des privilèges Windows')
    def test_alias_shows_size_without_double_counting(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'actual').mkdir();(p/'actual'/'payload').write_bytes(b'x'*123)
            (p/'alias').symlink_to(p/'actual',target_is_directory=True)
            (p/'actual'/'loop').symlink_to(p,target_is_directory=True)
            result=scan([p],threading.Event())
            self.assertEqual(result.root.total_bytes,123)
            self.assertTrue(result.root.complete)
            entries=folders(result,1)
            alias=next(e for e in entries if e.name=='alias')
            self.assertEqual(alias.size,123)
            self.assertFalse(alias.counted)
            self.assertIn('non recomptée',alias.reason)

    @unittest.skipIf(os.name=='nt','Liens nécessitant des privilèges Windows')
    def test_accessible_file_link_measured(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target:
            f=Path(target)/'payload';f.write_bytes(b'x'*123)
            (Path(root)/'filelink').symlink_to(f)
            result=scan([root],threading.Event())
            self.assertEqual(result.root.total_bytes,123)
            entries,_=list_directory(result,1,threading.Event())
            self.assertEqual(entries[0].size,123)

    def test_default_limits_are_unbounded(self):
        import inspect,math
        parameters=inspect.signature(scan).parameters
        for key in ('max_entries','max_directories','max_seconds'):
            self.assertTrue(math.isinf(parameters[key].default))
