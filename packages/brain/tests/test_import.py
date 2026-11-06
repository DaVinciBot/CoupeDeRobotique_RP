import importlib

import pytest


@pytest.mark.parametrize("layer", ["domain", "services", "ports", "adapters", "app"])
def test_layer_is_importable(layer: str) -> None:
    importlib.import_module(f"dvb_brain.{layer}")
