import unittest
from clair_storage.layout import size_text, parent_share, share_text
from clair_storage.browse import Entry
from clair_storage.widgets import ExplorerList
from unittest.mock import Mock


class StoragePresentationTests(unittest.TestCase):
    def test_decimal_units(self):
        self.assertEqual(size_text(1_500_000_000), '1,50 Go')
        self.assertEqual(size_text(250_000_000), '250,00 Mo')
        self.assertEqual(size_text(1), '< 0,01 Mo')
        self.assertEqual(size_text(0), '0,00 Mo')

    def test_parent_share_and_partial(self):
        self.assertEqual(parent_share(250, 1000), .25)
        self.assertEqual(share_text(250,1000), '25,0 %')
        self.assertEqual(share_text(250,1000,False), '≈ 25,0 %')
        for size,total in [(0,0),(150,100),(None,100)]:
            self.assertEqual(share_text(size,total), '—')

    def test_filter_does_not_change_denominator(self):
        widget=object.__new__(ExplorerList)
        widget.canvas=Mock();widget.draw=Mock()
        widget.set_entries([Entry('a','Visible',250,'file','a')],1000)
        self.assertEqual(widget.total,1000)
        self.assertEqual(parent_share(widget.entries[0].size,widget.total),.25)
