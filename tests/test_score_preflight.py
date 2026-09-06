import io
import hashlib

from pypdf import PdfReader
from reportlab.pdfgen import canvas


def synthetic_font():
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder=FontBuilder(1000,isTTF=True)
    builder.setupGlyphOrder(['.notdef','first','second','empty'])
    builder.setupCharacterMap({0xF041:'first',0xF042:'second'})
    glyphs={}
    for name in ['.notdef','first','second','empty']:
        pen=TTGlyphPen(None)
        if name in ('first','second'):
            pen.moveTo((0,0));pen.lineTo((500,0));pen.lineTo((250,500));pen.closePath()
        glyphs[name]=pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({n:(600,0) for n in glyphs})
    builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupNameTable({'familyName':'SyntheticSymbols','styleName':'Regular',
                           'uniqueFontIdentifier':'SyntheticSymbols','fullName':'Synthetic Symbols','psName':'SyntheticSymbols'})
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    builder.setupPost()
    # Symbolic cmap like a legacy music font, with no Microsoft Unicode cmap.
    tables=builder.font['cmap'].tables
    tables[:]=[table for table in tables if table.platformID==3]
    tables[0].platEncID=0
    buffer=io.BytesIO();builder.save(buffer)
    return buffer.getvalue()


def test_repairs_only_provable_symbolic_font_defects(api,tmp_path):
    from fontTools.ttLib import TTFont
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, NumberObject, ArrayObject, DecodedStreamObject
    from score_pdf_preflight import prepare_pdf
    good=synthetic_font()
    font=TTFont(io.BytesIO(good))
    raw=bytearray(good)
    location=font.reader.tables['loca']
    unit=2 if font['head'].indexToLocFormat==0 else 4
    raw[location.offset+location.length-unit:location.offset+location.length]=b'\0'*unit
    writer=PdfWriter();page=writer.add_blank_page(600,800)
    fontfile=DecodedStreamObject();fontfile.set_data(bytes(raw))
    desc=DictionaryObject({NameObject('/Type'):NameObject('/FontDescriptor'),NameObject('/FontName'):NameObject('/ABCDEF+'),
                           NameObject('/Flags'):NumberObject(4),NameObject('/FontFile2'):writer._add_object(fontfile)})
    obj=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/TrueType'),
                          NameObject('/BaseFont'):NameObject('/ABCDEF+'),NameObject('/FontDescriptor'):writer._add_object(desc),
                          NameObject('/Encoding'):NameObject('/WinAnsiEncoding'),NameObject('/FirstChar'):NumberObject(65),
                          NameObject('/LastChar'):NumberObject(66),NameObject('/Widths'):ArrayObject([NumberObject(600),NumberObject(600)])})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(obj)})})
    content=DecodedStreamObject();content.set_data(b'BT /F1 20 Tf 1 0 0 1 40 600 Tm (AB) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(content)
    source,output=tmp_path/'bad-font.pdf',tmp_path/'repaired.pdf'
    writer.write(source)
    result=prepare_pdf(source,output)
    assert {item['type'] for item in result['repairs']}=={'truetype_empty_final_glyph','symbolic_encoding','embedded_font_name'}
    assert not result['issues']
    repaired=PdfReader(output).pages[0]
    assert repaired.get_contents().get_data()==content.get_data()
    assert result['pageDetails'][0]['commandsSha256']==hashlib.sha256(content.get_data()).hexdigest()
    corrected=repaired['/Resources']['/Font']['/F1'].get_object()
    assert '/Encoding' not in corrected
    fixed=TTFont(io.BytesIO(corrected['/FontDescriptor']['/FontFile2'].get_data()))
    assert list(fixed['loca'].locations)==list(font['loca'].locations)


def test_vector_geometry_counts_bars_not_stems_and_reads_numbers(api, tmp_path):
    from score_pdf_preflight import prepare_pdf
    source, output = tmp_path/'source.pdf', tmp_path/'prepared.pdf'
    c = canvas.Canvas(str(source), pagesize=(600,800))
    for y in (600,605,610,615,620):
        c.line(40,y,560,y)
    for x in (170,300,430,560):
        c.line(x,600,x,620)
    # Long stems crossing the staff do not end at both outer staff lines.
    c.line(100,596,100,630)
    c.line(200,600,200,631)
    c.setFont('Helvetica',10)
    c.drawString(40,630,'35')
    c.drawString(290,25,'7')
    c.save()
    result=prepare_pdf(source,output)
    assert not result['changed'] and not output.exists()
    geometry=result['pageDetails'][0]['geometry']
    assert len(geometry['staves'])==1
    assert geometry['staves'][0]['barlines']==[170.,300.,430.,560.]
    assert [n['value'] for n in geometry['numbers']]==[35,7]


def test_staff_segments_per_measure_are_merged(api,tmp_path):
    from score_pdf_preflight import prepare_pdf
    p=tmp_path/'segments.pdf'
    c=canvas.Canvas(str(p),pagesize=(600,800))
    for left,right in ((40,170),(170,300),(300,430),(430,560)):
        for y in range(600,621,5):
            c.line(left,y,right,y)
        c.line(right,600,right,620)
    c.save()
    geometry=prepare_pdf(p,tmp_path/'out.pdf')['pageDetails'][0]['geometry']
    assert len(geometry['staves'])==1
    assert geometry['staves'][0]['right']==560
    assert geometry['staves'][0]['barlines']==[170,300,430,560]


def test_valid_pdf_is_unchanged_and_nested_forms_are_inspected(api,tmp_path):
    from score_pdf_preflight import prepare_pdf
    p=tmp_path/'form.pdf'
    c=canvas.Canvas(str(p),pagesize=(600,800))
    c.beginForm('staff')
    for y in range(0,21,5):
        c.line(0,y,500,y)
    c.endForm()
    c.translate(40,600)
    c.doForm('staff')
    c.save()
    before=p.read_bytes()
    result=prepare_pdf(p,tmp_path/'out.pdf')
    assert not result['issues'] and not result['changed'] and p.read_bytes()==before
    assert len(result['pageDetails'][0]['geometry']['staves'])==1
