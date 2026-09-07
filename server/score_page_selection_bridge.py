"""Run PDF page selection with the isolated score Python runtime."""
from __future__ import print_function

import json
import os
import subprocess
import sys


def validate_requested_pages(value):
    if not isinstance(value, list) or not value:
        raise ValueError('请至少选择一页需要转换的乐谱')
    if len(value) > 20:
        raise ValueError('单次最多转换 20 页')
    result = []
    seen = set()
    for page in value:
        if isinstance(page, bool) or not isinstance(page, int):
            raise ValueError('转换页码必须是整数')
        if not 1 <= page <= 500:
            raise ValueError('转换页码无效')
        if page in seen:
            raise ValueError('转换页码不能重复')
        seen.add(page)
        result.append(page)
    return sorted(result)


def prepare_selected_pdf(source, output, selected_pages, report_path):
    isolated_python = '/opt/score-tools/score-venv/bin/python'
    python = os.environ.get('SCORE_SKILL_PYTHON') or (
        isolated_python if os.path.isfile(isolated_python) else sys.executable)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_page_selection.py')
    command = [python, '-X', 'utf8', script, source, output]
    if selected_pages is not None:
        command.extend(['--pages', ','.join(str(page) for page in selected_pages)])
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=45, check=False)
        raw = result.stdout.decode('utf-8', 'replace').strip().splitlines()
        try:
            details = json.loads(raw[-1]) if raw else {}
        except (TypeError, ValueError):
            details = {}
        if result.returncode or not os.path.isfile(output):
            raise ValueError(details.get('error') or 'PDF 选页处理失败')
        with open(report_path + '.tmp', 'w', encoding='utf-8') as stream:
            json.dump(details, stream, ensure_ascii=False, indent=2)
        os.replace(report_path + '.tmp', report_path)
        return details
    except subprocess.TimeoutExpired:
        raise ValueError('PDF 选页处理超时')
    except ValueError:
        raise
    except (OSError, KeyError):
        raise ValueError('服务器暂时无法读取 PDF 页码')
