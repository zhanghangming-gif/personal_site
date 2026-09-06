"""Format-based PDF preflight; no score names, input hashes or music coordinates.

Executed with the isolated modern Python environment. Repairs only provable
embedded TrueType container/encoding defects and keeps page drawing commands.
"""
import argparse
import hashlib
import io
import json
import logging
import re
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, NumberObject
from score_pdf_layout import page_geometry

logging.getLogger('fontTools').setLevel(logging.ERROR)


def resolve(value):
    return value.get_object() if hasattr(value, 'get_object') else value


def resource_fonts(resources, visited=None):
    visited = visited if visited is not None else set()
    resources = resolve(resources)
    for ref in resolve(resources.get('/Font', {})).values():
        font = resolve(ref)
        if id(font) not in visited:
            visited.add(id(font))
            yield font
    for ref in resolve(resources.get('/XObject', {})).values():
        obj = resolve(ref)
        if obj.get('/Subtype') == '/Form' and obj.get('/Resources') and id(obj) not in visited:
            visited.add(id(obj))
            yield from resource_fonts(obj['/Resources'], visited)


def symbolic_widths_match(font, ft, cmap):
    """Require the PDF's used font widths to agree with its symbolic glyph map."""
    first = int(font.get('/FirstChar', 0))
    widths = font.get('/Widths', [])
    units = ft['head'].unitsPerEm
    compared = 0
    for index, width in enumerate(widths):
        if float(width) == 0:
            continue
        code = first + index
        name = cmap.get(0xF000 + code)
        if not name:
            return False
        actual = ft['hmtx'][name][0] * 1000 / units
        if abs(actual - float(width)) > 2:
            return False
        compared += 1
    return compared >= 2


def prepare_pdf(source_path, output_path):
    reader = PdfReader(source_path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF 需要密码，无法读取乐谱')
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    repairs, issues, seen = [], [], set()
    font_cache = {}
    music_families = set()
    page_details = []
    for page_number, page in enumerate(writer.pages, 1):
        resources = resolve(page.get('/Resources', {}))
        contents = page.get_contents()
        original_commands = contents.get_data() if contents is not None else b''
        page_details.append({'page': page_number, 'width': float(page.mediabox.width),
                             'height': float(page.mediabox.height),
                             'commandsSha256': hashlib.sha256(original_commands).hexdigest()})
        for font in resource_fonts(resources, seen):
            font_name = str(font.get('/BaseFont','')).lstrip('/').split('+')[-1].replace(' ','')
            if font_name in ('Bravura', 'Leland', 'FinaleJazz', 'JazzPerc', 'MusicalSymbols'):
                music_families.add(font_name)
            desc = resolve(font.get('/FontDescriptor', {}))
            stream = desc.get('/FontFile2')
            if not stream:
                continue
            identity = id(desc)
            try:
                if identity in font_cache:
                    ft, changed_container = font_cache[identity]
                else:
                    ft = TTFont(io.BytesIO(resolve(stream).get_data()), recalcTimestamp=False)
                    changed_container = False
                    if 'loca' in ft and 'glyf' in ft:
                        positions = ft['loca'].locations
                        raw = ft.reader['glyf']
                        # Some subset writers leave the final empty glyph's loca
                        # terminator at zero. Existing outlines and indices suffice
                        # to prove the correction; nonzero trailing data is rejected.
                        if (len(positions) > 2 and positions[-1] == 0 and positions[-2] > 0
                                and positions[-2] <= len(raw)
                                and all(a <= b for a, b in zip(positions[:-2], positions[1:-1]))
                                and not any(raw[positions[-2]:])):
                            positions[-1] = positions[-2]
                            changed_container = True
                        ft['glyf']  # A font with other outline corruption is not guessed.
                    if changed_container:
                        data = io.BytesIO()
                        ft.save(data)
                        repaired = DecodedStreamObject()
                        repaired.set_data(data.getvalue())
                        repaired[NameObject('/Length1')] = NumberObject(len(data.getvalue()))
                        desc[NameObject('/FontFile2')] = writer._add_object(repaired)
                        repairs.append({'page': page_number, 'type': 'truetype_empty_final_glyph',
                                        'detail': '修正内嵌字体最后一个空字形的索引，保留已有字形'})
                    font_cache[identity] = (ft, changed_container)
                cmap = next((table.cmap for table in ft['cmap'].tables
                             if table.platformID == 3 and table.platEncID == 0), {})
                unicode_ms = any(table.platformID == 3 and table.platEncID in (1, 10) for table in ft['cmap'].tables)
                if (int(desc.get('/Flags', 0)) & 4 and cmap and not unicode_ms
                        and str(font.get('/Encoding')) == '/WinAnsiEncoding'
                        and symbolic_widths_match(font, ft, cmap)):
                    font.pop('/Encoding')
                    repairs.append({'page': page_number, 'type': 'symbolic_encoding',
                                    'detail': '按内嵌符号字体与原字宽修正编码声明'})
                base = str(font.get('/BaseFont', ''))
                if re.fullmatch(r'/[A-Z]{6}\+', base):
                    ps_name = ft['name'].getDebugName(6)
                    if ps_name and re.fullmatch(r'[A-Za-z0-9_-]+', ps_name):
                        name = NameObject(base + ps_name)
                        font[NameObject('/BaseFont')] = name
                        desc[NameObject('/FontName')] = name
                        repairs.append({'page': page_number, 'type': 'embedded_font_name',
                                        'detail': '从内嵌字体恢复缺失的字体名称'})
            except (TTLibError, KeyError, ValueError, IndexError) as exc:
                issues.append({'page': page_number, 'type': 'invalid_embedded_font',
                               'font': str(font.get('/BaseFont', '')), 'detail': str(exc)[:180]})
    changed = bool(repairs)
    result_path = Path(output_path) if changed else Path(source_path)
    if changed:
        writer.write(result_path)
        reread = PdfReader(result_path)
        assert len(reread.pages) == len(reader.pages)
        for i, page in enumerate(reread.pages):
            contents = page.get_contents()
            commands = contents.get_data() if contents is not None else b''
            assert hashlib.sha256(commands).hexdigest() == page_details[i]['commandsSha256'], 'Drawing commands changed during font preflight'
    prepared_reader = PdfReader(result_path)
    for page, details in zip(prepared_reader.pages, page_details):
        details['geometry'] = page_geometry(page, prepared_reader)
    return {'sourceSha256': hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
            'preparedSha256': hashlib.sha256(result_path.read_bytes()).hexdigest(),
            'preparedPath': str(result_path), 'changed': changed, 'pages': len(reader.pages),
            'musicFamily': next(iter(music_families)) if len(music_families)==1 else None,
            'pageDetails': page_details, 'repairs': repairs, 'issues': issues}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    result = prepare_pdf(args.source, args.output)
    Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'changed': result['changed'], 'pages': result['pages'],
                      'repairs': len(result['repairs']), 'issues': len(result['issues'])}))
