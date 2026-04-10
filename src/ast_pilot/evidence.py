"""Evidence store: data structures for everything the scanner extracts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Parameter:
    name: str
    annotation: str = ""
    default: str = ""


@dataclass
class FunctionInfo:
    name: str
    qualname: str
    module: str
    lineno: int
    decorators: list[str] = field(default_factory=list)
    params: list[Parameter] = field(default_factory=list)
    signature_params: str = ""
    return_annotation: str = ""
    docstring: str = ""
    is_async: bool = False
    is_method: bool = False
    is_property: bool = False
    is_staticmethod: bool = False
    is_classmethod: bool = False


@dataclass
class ClassInfo:
    name: str
    qualname: str
    module: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    methods: list[FunctionInfo] = field(default_factory=list)
    class_variables: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ModuleInfo:
    path: str
    module_name: str
    docstring: str = ""
    imports: list[str] = field(default_factory=list)
    from_imports: list[tuple[str, list[str]]] = field(default_factory=list)
    all_exports: list[str] = field(default_factory=list)
    constants: list[tuple[str, str]] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    line_count: int = 0


@dataclass
class TestEvidence:
    test_file: str
    test_name: str
    tested_symbols: list[str] = field(default_factory=list)
    source_snippet: str = ""


@dataclass
class Evidence:
    """Root container for everything extracted from a scan."""

    project_name: str = ""
    source_files: list[ModuleInfo] = field(default_factory=list)
    tests: list[TestEvidence] = field(default_factory=list)
    readme_sections: dict[str, str] = field(default_factory=dict)
    total_loc: int = 0
    python_version: str = "3.10"
    dependencies: list[str] = field(default_factory=list)

    def all_public_symbols(self) -> list[str]:
        symbols: list[str] = []
        for mod in self.source_files:
            for fn in mod.functions:
                if not fn.name.startswith("_"):
                    symbols.append(fn.qualname)
            for cls in mod.classes:
                if not cls.name.startswith("_"):
                    symbols.append(cls.qualname)
                    for method in cls.methods:
                        if not method.name.startswith("_"):
                            symbols.append(method.qualname)
        return symbols

    def tested_symbols(self) -> set[str]:
        out: set[str] = set()
        for t in self.tests:
            out.update(t.tested_symbols)
        return out

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Evidence":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return _evidence_from_dict(raw)


def _evidence_from_dict(d: dict[str, Any]) -> Evidence:
    """Reconstruct Evidence from a JSON-round-tripped dict."""

    ev = Evidence(
        project_name=d.get("project_name", ""),
        total_loc=d.get("total_loc", 0),
        python_version=d.get("python_version", "3.10"),
        dependencies=d.get("dependencies", []),
        readme_sections=d.get("readme_sections", {}),
    )
    for m in d.get("source_files", []):
        mod = ModuleInfo(
            path=m["path"],
            module_name=m["module_name"],
            docstring=m.get("docstring", ""),
            imports=m.get("imports", []),
            from_imports=[tuple(fi) for fi in m.get("from_imports", [])],
            all_exports=m.get("all_exports", []),
            constants=[(c[0], c[1]) for c in m.get("constants", [])],
            string_literals=m.get("string_literals", []),
            line_count=m.get("line_count", 0),
        )
        for f in m.get("functions", []):
            mod.functions.append(_func_from_dict(f))
        for c in m.get("classes", []):
            ci = ClassInfo(
                name=c["name"],
                qualname=c["qualname"],
                module=c["module"],
                lineno=c["lineno"],
                bases=c.get("bases", []),
                decorators=c.get("decorators", []),
                docstring=c.get("docstring", ""),
                class_variables=[(v[0], v[1]) for v in c.get("class_variables", [])],
            )
            for method in c.get("methods", []):
                ci.methods.append(_func_from_dict(method))
            mod.classes.append(ci)
        ev.source_files.append(mod)
    for t in d.get("tests", []):
        ev.tests.append(
            TestEvidence(
                test_file=t["test_file"],
                test_name=t["test_name"],
                tested_symbols=t.get("tested_symbols", []),
                source_snippet=t.get("source_snippet", ""),
            )
        )
    return ev


def _func_from_dict(f: dict[str, Any]) -> FunctionInfo:
    params = [Parameter(**p) for p in f.get("params", [])]
    return FunctionInfo(
        name=f["name"],
        qualname=f["qualname"],
        module=f["module"],
        lineno=f["lineno"],
        decorators=f.get("decorators", []),
        params=params,
        signature_params=f.get("signature_params", ""),
        return_annotation=f.get("return_annotation", ""),
        docstring=f.get("docstring", ""),
        is_async=f.get("is_async", False),
        is_method=f.get("is_method", False),
        is_property=f.get("is_property", False),
        is_staticmethod=f.get("is_staticmethod", False),
        is_classmethod=f.get("is_classmethod", False),
    )
