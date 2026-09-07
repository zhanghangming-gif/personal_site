import importlib.util
import json
from pathlib import Path

from PIL import Image


def module():
    path = Path(__file__).resolve().parents[1] / 'ml' / 'rest_detector' / 'split_coco_tasks.py'
    spec = importlib.util.spec_from_file_location('split_coco_tasks', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_task_split_remaps_classes_and_keeps_task_negatives(tmp_path):
    source = tmp_path / 'source'; (source / 'annotations').mkdir(parents=True)
    for split in ('train', 'validation', 'test'):
        (source / 'images' / split).mkdir(parents=True)
        Image.new('RGB', (20, 20), 'white').save(source / 'images' / split / 'rest.png')
        Image.new('RGB', (20, 20), 'white').save(source / 'images' / split / 'structure.png')
        payload = {
            'categories': [{'id': 6, 'name': 'quarter_rest'}, {'id': 13, 'name': 'barline'}],
            'images': [
                {'id': 1, 'file_name': f'{split}/rest.png', 'task_type': 'rest'},
                {'id': 2, 'file_name': f'{split}/structure.png', 'task_type': 'structure'},
            ],
            'annotations': [
                {'id': 1, 'image_id': 1, 'category_id': 6, 'bbox': [1, 1, 5, 7]},
                {'id': 2, 'image_id': 2, 'category_id': 13, 'bbox': [10, 1, 2, 15]},
            ],
        }
        (source / 'annotations' / f'{split}.json').write_text(json.dumps(payload), encoding='utf-8')
    rest_output = tmp_path / 'rest'
    structure_output = tmp_path / 'structure'
    splitter = module()
    rest = splitter.split_dataset(source, rest_output, 'rest')
    structure = splitter.split_dataset(source, structure_output, 'structure')
    assert rest['classes'] == ['quarter_rest']
    assert structure['classes'] == ['barline']
    rest_train = json.loads((rest_output / 'annotations' / 'train.json').read_text())
    structure_train = json.loads((structure_output / 'annotations' / 'train.json').read_text())
    assert [item['category_id'] for item in rest_train['annotations']] == [1]
    assert [item['category_id'] for item in structure_train['annotations']] == [1]
    assert [item['file_name'] for item in rest_train['images']] == ['train/rest.png']
    assert [item['file_name'] for item in structure_train['images']] == ['train/structure.png']
