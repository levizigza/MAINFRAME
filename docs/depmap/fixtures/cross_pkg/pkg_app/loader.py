import importlib

def load(name: str):
    # dynamic dependency — target unknown statically
    return importlib.import_module(name)
