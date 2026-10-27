import os
import pytest
from tools.synthetic_dataset_generator import generate_synthetic_dataset


def test_synthetic_dataset_generation(tmp_path):
    output_dir = str(tmp_path / "dataset_test")
    generate_synthetic_dataset(output_dir=output_dir, num_samples=5, width=640, height=360)

    # train ve val klasörleri oluşmalı
    train_imgs = os.listdir(os.path.join(output_dir, "images", "train"))
    train_lbls = os.listdir(os.path.join(output_dir, "labels", "train"))
    yaml_file = os.path.join(output_dir, "dataset.yaml")

    assert len(train_imgs) > 0
    assert len(train_lbls) == len(train_imgs)
    assert os.path.exists(yaml_file)
