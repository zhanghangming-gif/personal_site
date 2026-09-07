"""Create the exact PDF page subset that enters the score pipeline."""
from __future__ import print_function

import argparse
import json
import shutil
import sys

from pypdf import PdfReader, PdfWriter


MAX_SOURCE_PAGES = 500
MAX_SELECTED_PAGES = 20


def normalize_pages(pages, page_count):
    if pages is None:
        if page_count > MAX_SELECTED_PAGES:
            raise ValueError('原 PDF 超过 20 页，请指定本次需要转换的页码')
        return list(range(1, page_count + 1))
    if not isinstance(pages, list) or not pages:
        raise ValueError('请至少选择一页需要转换的乐谱')
    if len(pages) > MAX_SELECTED_PAGES:
        raise ValueError('单次最多转换 20 页')
    normalized = []
    seen = set()
    for value in pages:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError('转换页码必须是整数')
        if value < 1 or value > page_count:
            raise ValueError('转换页码 %s 超出原 PDF 的 1-%s 页范围' % (value, page_count))
        if value in seen:
            raise ValueError('转换页码不能重复')
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def select_pdf_pages(source, output, pages=None):
    reader = PdfReader(source, strict=False)
    if reader.is_encrypted:
        raise ValueError('受密码保护的 PDF 暂不支持转换')
    page_count = len(reader.pages)
    if not 1 <= page_count <= MAX_SOURCE_PAGES:
        raise ValueError('PDF 页数无效或超过 500 页')
    selected = normalize_pages(pages, page_count)
    if selected == list(range(1, page_count + 1)):
        shutil.copyfile(source, output)
    else:
        writer = PdfWriter()
        for page_number in selected:
            writer.add_page(reader.pages[page_number - 1])
        metadata = reader.metadata
        if metadata:
            clean_metadata = {str(key): str(value) for key, value in metadata.items()
                              if key and value is not None}
            if clean_metadata:
                writer.add_metadata(clean_metadata)
        with open(output, 'wb') as stream:
            writer.write(stream)
    return {
        'schemaVersion': 1,
        'sourcePageCount': page_count,
        'selectedPages': selected,
        'selectedPageCount': len(selected),
        'mode': 'all' if len(selected) == page_count else 'custom',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--pages', help='Comma-separated, one-based source page numbers')
    args = parser.parse_args()
    pages = None
    if args.pages is not None:
        try:
            pages = [int(value) for value in args.pages.split(',') if value]
        except ValueError:
            print(json.dumps({'error': '转换页码必须是整数'}, ensure_ascii=False))
            return 2
    try:
        report = select_pdf_pages(args.source, args.output, pages)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
