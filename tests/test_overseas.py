import importlib.util, pathlib, unittest
from unittest.mock import patch
P=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"collect_overseas.py"
spec=importlib.util.spec_from_file_location("overseas",P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OverseasTests(unittest.TestCase):
    def test_uk_real_shape(self):
        r={"id":"123456-2026","ocid":"ocds-example","date":"2026-11-25T00:00:00Z","tag":["tender"],"buyer":{"name":"Example"},"tender":{"title":"Software development","value":{"amount":12000,"currency":"GBP"},"items":[{"classification":{"id":"72200000"}}]}}
        with patch.object(m,"js",return_value={"releases":[r,{"id":"other","tender":{"title":"Road works"}}]}):
            rows=m.uk(7)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["amount"],12000);self.assertEqual(rows[0]["country"],"GBR")
    def test_ted_pagination(self):
        r={"publication-number":"123456-2026","notice-title":{"eng":["Software"]},"buyer-country":["IRL"],"buyer-name":{"eng":["Example"]},"publication-date":"20261125","notice-type":"cn-standard"}
        with patch.object(m,"js",side_effect=[{"notices":[r],"iterationNextToken":"next"},{"notices":[],"iterationNextToken":"still-present"}]) as call:
            rows=m.eu(7)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["country"],"IRL");self.assertEqual(rows[0]["title"],"Software");self.assertEqual(call.call_count,2)
    def test_ca_csv(self):
        content="referenceNumber-numeroReference,title-titre-eng,publicationDate-datePublication\nABC,Software development,2026-11-25\nDEF,Road works,2026-11-25\n"
        with patch.object(m,"request",return_value=content.encode()):
            rows=m.ca(7)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["country"],"CAN")
    def test_bad_link(self):
        self.assertEqual(m.https("javascript:alert(1)"),"")
    def test_failed_source_preserves_last_snapshot(self):
        import tempfile,json,sys
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d); prior=m.row("uk","old","GBR","Software","Buyer","2026-11-24","","tender","https://example.com",{})
            (p/"old.json").write_text(json.dumps({"notices":[prior],"sources":{"uk":{"checked":"old","success":"old","error":None}}}))
            with patch.object(m,"uk",side_effect=ValueError("offline")),patch.object(m,"eu",return_value=[]),patch.object(m,"ca",return_value=[]),patch.object(sys,"argv",["collect","--db",str(p/"db"),"--output",str(p/"new.json"),"--seed",str(p/"old.json")]):
                self.assertEqual(m.main(),1)
            data=json.loads((p/"new.json").read_text())
            self.assertEqual(data["notices"][0]["id"],"old")
            self.assertEqual(data["sources"]["uk"]["success"],"old")
            self.assertEqual(data["sources"]["uk"]["error"],"offline")
    def test_ted_bulk_xml(self):
        import sys,datetime as dt
        sys.path.insert(0,str(P.parent))
        import overseas_ted_bulk as b
        data=b"""<ContractNotice><Publication><NoticePublicationID>00012345-2026</NoticePublicationID><PublicationDate>2026-11-24</PublicationDate></Publication><Organization><Company><PartyIdentification><ID>ORG-0001</ID></PartyIdentification><PartyName><Name languageID="ENG">Buyer</Name></PartyName><PostalAddress><Country><IdentificationCode>IRL</IdentificationCode></Country></PostalAddress></Company></Organization><ContractingParty><Party><PartyIdentification><ID>ORG-0001</ID></PartyIdentification></Party></ContractingParty><NoticeTypeCode>cn-standard</NoticeTypeCode><ProcurementProject><Name languageID="ENG">Software system</Name><MainCommodityClassification><ItemClassificationCode>72200000</ItemClassificationCode></MainCommodityClassification></ProcurementProject></ContractNotice>"""
        r=b.parse("00012345_2026.xml",data,dt.date(2026,11,24),m.EU,m.row)
        self.assertEqual((r["country"],r["buyer"],r["id"]),("IRL","Buyer","00012345-2026"))
        self.assertEqual(b.calendar(b"Date;Issue\n24/11/2026;228",2026)[dt.date(2026,11,24)],228)
    def test_rate_limit_retry(self):
        from urllib.error import HTTPError
        from unittest.mock import MagicMock
        err=HTTPError("https://example.org",429,"rate limit",{"Retry-After":"60"},None)
        resp=MagicMock();resp.__enter__.return_value.read.return_value=b"ok"
        with patch.object(m,"urlopen",side_effect=[err,resp]),patch.object(m.time,"sleep") as sleep:
            self.assertEqual(m.request("https://example.org"),b"ok")
            sleep.assert_called_once_with(60)
if __name__=="__main__":unittest.main()
