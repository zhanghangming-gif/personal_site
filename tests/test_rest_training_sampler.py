import importlib.util
from collections import defaultdict
from pathlib import Path


def load_training_module():
    path = Path(__file__).resolve().parents[1] / 'ml' / 'rest_detector' / 'train_torchvision.py'
    spec = importlib.util.spec_from_file_location('train_torchvision', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TinyDataset:
    def __init__(self):
        self.images = [{'id': value} for value in range(8)]
        self.annotations = defaultdict(list)
        for image_id in range(5):
            self.annotations[image_id].append({'bbox': [0, 0, 1, 1]})

    def __len__(self):
        return len(self.images)


def test_positive_aware_sampler_never_pairs_only_negative_crops():
    module = load_training_module()
    dataset = TinyDataset()
    sampler = module.PositiveAwareBatchSampler(dataset, batch_size=2, seed=7)

    batches = list(sampler)

    assert sorted(index for batch in batches for index in batch) == list(range(len(dataset)))
    assert all(any(dataset.annotations[dataset.images[index]['id']] for index in batch)
               for batch in batches)
