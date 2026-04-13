"""Build-time helper for collecting hidden task support assets."""

from __future__ import annotations

import hashlib
import py_compile
import re
import shutil
import tempfile
from pathlib import Path

_TASK_SLUG_RE = re.compile(r"""task\.slug\s*=\s*(['"])(?P<slug>.+?)\1""")
_SHIM_HEADER = '"""Shim for `'


def _support_aliases(task_dir: Path) -> set[str]:
    aliases = {task_dir.name}
    task_py = task_dir / "task.py"
    if not task_py.exists():
        return aliases

    match = _TASK_SLUG_RE.search(task_py.read_text(encoding="utf-8", errors="replace"))
    if match:
        aliases.add(match.group("slug"))
    return aliases


def _replace_with_symlink(target: Path, source: Path) -> None:
    if target == source:
        return
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    target.symlink_to(source.name, target_is_directory=True)


def _is_task_shim(path: Path) -> bool:
    return path.read_text(encoding="utf-8", errors="replace").startswith(_SHIM_HEADER)


def _task_owned_support_paths(tasks_root: Path) -> set[Path]:
    owned_paths: set[Path] = set()
    for task_dir in tasks_root.iterdir():
        support_dir = task_dir / "support"
        if not support_dir.is_dir():
            continue

        for support_file in support_dir.rglob("*.py"):
            if _is_task_shim(support_file):
                owned_paths.add(support_file.relative_to(support_dir))
    return owned_paths


def _compile_hidden_source(hidden_path: Path, source: str) -> None:
    hidden_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(source)
        tmp_source = Path(tmp.name)

    try:
        py_compile.compile(str(tmp_source), cfile=str(hidden_path), doraise=True)
    finally:
        tmp_source.unlink(missing_ok=True)


def _loader_stub(hidden_path: Path) -> str:
    return (
        '"""Opaque loader for hidden support module."""\n\n'
        "from __future__ import annotations\n\n"
        "import importlib.util\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        f"_HIDDEN = Path({str(hidden_path)!r})\n"
        "_SPEC = importlib.util.spec_from_file_location(__name__, _HIDDEN)\n"
        "if _SPEC is None or _SPEC.loader is None:\n"
        '    raise ImportError(f"Unable to load hidden support module: {_HIDDEN}")\n'
        "_MODULE = importlib.util.module_from_spec(_SPEC)\n"
        "sys.modules[__name__] = _MODULE\n"
        "_SPEC.loader.exec_module(_MODULE)\n"
        "globals().update(_MODULE.__dict__)\n"
    )


def _hide_cross_task_targets(task_support_root: Path, owned_paths: set[Path]) -> None:
    hidden_root = task_support_root / ".ast_pilot_hidden"

    for rel_path in sorted(owned_paths):
        if rel_path.name == "__init__.py":
            continue

        support_file = task_support_root / rel_path
        if not support_file.is_file():
            continue
        if _is_task_shim(support_file):
            continue

        source = support_file.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(f"{rel_path.as_posix()}\n{source}".encode("utf-8")).hexdigest()
        hidden_path = hidden_root / f"{digest}.pyc"
        _compile_hidden_source(hidden_path, source)
        support_file.write_text(_loader_stub(hidden_path), encoding="utf-8")


def stage_support_assets(tasks_root: Path, support_root: Path, requirements_path: Path) -> None:
    support_root.mkdir(parents=True, exist_ok=True)
    requirements: set[str] = set()
    owned_paths = _task_owned_support_paths(tasks_root)

    for task_dir in tasks_root.iterdir():
        if not task_dir.is_dir():
            continue

        support_dir = task_dir / "support"
        if support_dir.is_dir():
            primary_target = support_root / task_dir.name
            shutil.copytree(support_dir, primary_target, dirs_exist_ok=True)
            _hide_cross_task_targets(primary_target, owned_paths)
            for alias in sorted(_support_aliases(task_dir) - {task_dir.name}):
                _replace_with_symlink(support_root / alias, primary_target)

        req_path = task_dir / "requirements.hidden.txt"
        if req_path.exists():
            for line in req_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.add(line)

        _preinstall_node_modules(task_dir)

    if requirements:
        requirements_path.write_text(
            "\n".join(sorted(requirements)) + "\n",
            encoding="utf-8",
        )
    elif requirements_path.exists():
        requirements_path.unlink()


def _node_install_fingerprint(config_dir: Path) -> str:
    """Compute a fingerprint from install-relevant config files."""
    h = hashlib.sha256()
    for name in ("package.json", "package-lock.json", ".npmrc"):
        src = config_dir / name
        if src.exists():
            h.update(name.encode("utf-8"))
            h.update(src.read_bytes())
    return h.hexdigest()[:16]


def _preinstall_node_modules(task_dir: Path) -> None:
    """Pre-install node_modules for TypeScript tasks at image build time."""
    config_dir = task_dir / "config"
    pkg_json = config_dir / "package.json"
    if not pkg_json.exists():
        return

    slug = task_dir.name
    task_py = task_dir / "task.py"
    if task_py.exists():
        match = _TASK_SLUG_RE.search(task_py.read_text(encoding="utf-8", errors="replace"))
        if match:
            slug = match.group("slug")

    cache_dir = Path(f"/tmp/ast_pilot_node_{slug}_modules")
    cache_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = _node_install_fingerprint(config_dir)
    marker = cache_dir / ".installed"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == fingerprint:
        print(f"  [node] node_modules cache is current for {task_dir.name}")
        return

    shutil.copy2(pkg_json, cache_dir / "package.json")
    lockfile = config_dir / "package-lock.json"
    if lockfile.exists():
        shutil.copy2(lockfile, cache_dir / "package-lock.json")
    npmrc = config_dir / ".npmrc"
    if npmrc.exists():
        shutil.copy2(npmrc, cache_dir / ".npmrc")

    import subprocess
    result = subprocess.run(
        ["npm", "ci", "--ignore-scripts"],
        cwd=str(cache_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"  [node] npm ci failed for {task_dir.name}, falling back to npm install")
        result = subprocess.run(
            ["npm", "install", "--legacy-peer-deps", "--ignore-scripts"],
            cwd=str(cache_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    if result.returncode == 0:
        marker.write_text(fingerprint, encoding="utf-8")
        print(f"  [node] Pre-installed node_modules for {task_dir.name}")
    else:
        print(f"  [node] WARNING: npm install failed for {task_dir.name}: {result.stderr[:200]}")


def main() -> None:
    stage_support_assets(
        tasks_root=Path("/mcp_server/tasks"),
        support_root=Path("/opt/ast_pilot_support"),
        requirements_path=Path("/tmp/ast_pilot_hidden_requirements.txt"),
    )


if __name__ == "__main__":
    main()
