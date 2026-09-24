"""Import-only stubs for qoala/netqasm (private NetSquid index).

They are referenced only by DQC-NAC's Qoala output parser, which the probe
does not run (``parse=False``).
"""
import importlib.abc, importlib.machinery, sys, types

class _Dummy:
    def __init__(self, *a, **k): pass
    def __class_getitem__(cls, item): return cls

class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (_Dummy,), {})

class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    PREFIXES = ("qoala", "netqasm")
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in self.PREFIXES:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None
    def create_module(self, spec):
        m = _StubModule(spec.name); m.__path__ = []; return m
    def exec_module(self, module): pass

sys.meta_path.insert(0, _Finder())
