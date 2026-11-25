import pathlib,sys,tempfile,unittest,io,zipfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import collect_overseas_attachments as m
class AttachmentTests(unittest.TestCase):
    def test_portal_safety(self):
        self.assertTrue(m.allowed("https://www.find-tender.service.gov.uk/Notice/1"))
        for x in ["http://gov.uk","https://gov.uk.evil.com/","https://127.0.0.1/","https://user@gov.uk/","https://gov.uk:8080/"]:
            self.assertFalse(m.allowed(x),x)
    def test_docx(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            z.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>ISO 27001 certification required.</w:t></w:r></w:p></w:body></w:document>')
        data=b.getvalue();self.assertEqual(m.file_kind(data),"docx")
        t,state=m.extract(data,"docx");self.assertEqual(state,"body_only");self.assertTrue(m.hints(t))
    def test_link_discovery_and_login(self):
        base="https://www.find-tender.service.gov.uk/Notice/1"
        row={"id":"1","url":base}
        def get(u):
            if u==base:return u,"text/html","",b'<a href="/attachment/spec.pdf">Specification.pdf</a>'
            return u,"text/html","",b'<form><input type="password"></form>'
        with tempfile.TemporaryDirectory() as d,patch.object(m,"get",side_effect=get):
            r=m.inspect(row,pathlib.Path(d))
        self.assertEqual(r["status"],"registration_required");self.assertEqual(r["documents"],[])
    def test_pdf_bytes_not_html(self):
        from pypdf import PdfWriter
        b=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(b)
        data=b.getvalue()
        row={"id":"1","url":"https://www.find-tender.service.gov.uk/spec.pdf"}
        with tempfile.TemporaryDirectory() as d,patch.object(m,"get",return_value=(row["url"],"application/pdf","",data)):
            r=m.inspect(row,pathlib.Path(d));self.assertEqual(r["documents"][0]["extraction"],"partial");self.assertTrue(list(pathlib.Path(d).glob("*.pdf")))
    def test_manchester_candidate(self):
        self.assertTrue(any("due-north.com" in u for _,u in m.candidate_links({"id":"ocid:108918-2026"})))
if __name__=="__main__":unittest.main()
