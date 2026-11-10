import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector import parse_cards,canonical_link,merge,make_xml
class CollectorTest(unittest.TestCase):
    def test_parse_dedup(self):
        html='''<html><h2><a href="/u/263790484">درخشش تیم دوچرخه سواری پتروشیمی تبریز در لیگ برتر کشور</a></h2>
        <a href="/u/263790484">همین خبر پتروشیمی تبریز در لیگ برتر کشور</a>
        <h2><a href="/u/263789630">ایستگاه هشتم ارزیابی عملکرد شرکت پتروشیمی فن آوران</a></h2></html>'''
        rows=parse_cards(html,'https://khabarfarsi.com/tags2/X','پتروشیمی')
        self.assertEqual(2,len(rows))
        self.assertEqual('https://khabarfarsi.com/u/263790484',rows[0]['url'])
    def test_restricts_external_urls(self):
        for u in ('http://127.0.0.1/u/123','https://example.com/u/12','javascript:alert(1)','https://khabarfarsi.com/search?q=a'):
            self.assertIsNone(canonical_link(u))
    def test_merging_tags(self):
        one={'url':'https://khabarfarsi.com/u/1','title':'خبر پتروشیمی بسیار مهم','tags':['پتروشیمی'],'first_seen':'2026-11-09T00:00:00+00:00','last_seen':'','id':'a'}
        two={**one,'tags':['شرکت پتروشیمی']}
        merged=merge({one['url']:one},[two],'2026-11-09T01:00:00+00:00')
        self.assertEqual(1,len(merged)); self.assertEqual(2,len(merged[0]['tags']))
        self.assertEqual('2026-11-09T00:00:00+00:00',merged[0]['first_seen'])
    def test_feed(self):
        from xml.etree import ElementTree as E
        one={'url':'https://khabarfarsi.com/u/1','title':'خبر پتروشیمی','tags':['صنعت پتروشیمی'],'first_seen':'2026-11-09T00:00:00+00:00'}
        xml=make_xml([one],'2026-11-09T01:00:00+00:00')
        self.assertEqual('خبر پتروشیمی',E.fromstring(xml).find('./channel/item/title').text)
if __name__=='__main__':unittest.main()
