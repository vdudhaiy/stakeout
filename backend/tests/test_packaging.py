"""Guards on backend/pyproject.toml's packaging manifest.

These exist because of a real production outage. `rate_limit.py` lives at the
top level of backend/src but was never listed in `py-modules`, so it was
absent from the installed wheel. Nothing noticed for a long time: the only
importer was routers/local_auth.py, which a Supabase deployment never mounts.
The moment the public routers started importing it, Render died on startup
with `ModuleNotFoundError: No module named 'rate_limit'` — while every local
run kept working, because uvicorn starts with backend/src as cwd and the
working tree shadows the installed copy.

Nothing in the normal test suite can catch that: the tests also run against
the working tree. So these compare the *manifest* against the directory
instead, which is the one check that would have failed before the deploy did.
"""

import sys
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src"


def _manifest() -> dict:
    with open(BACKEND / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _flat_modules() -> set[str]:
    """Every importable top-level module in backend/src."""
    return {p.stem for p in SRC.glob("*.py") if not p.stem.startswith("_")}


def _subpackages() -> set[str]:
    return {p.name for p in SRC.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def test_every_flat_module_is_declared_in_py_modules():
    """setuptools does not discover flat modules — each is listed by hand.

    A module missing here is invisible until a deployment imports it from
    site-packages rather than from the working tree.
    """
    declared = set(_manifest()["tool"]["setuptools"]["py-modules"])
    missing = _flat_modules() - declared
    assert not missing, (
        f"{sorted(missing)} exist in backend/src but are not in py-modules, so they "
        "will not be installed. Add them to backend/pyproject.toml."
    )


def test_py_modules_does_not_list_anything_that_no_longer_exists():
    declared = set(_manifest()["tool"]["setuptools"]["py-modules"])
    stale = declared - _flat_modules()
    assert not stale, f"py-modules lists {sorted(stale)}, which no longer exist in backend/src."


def test_subpackages_are_found_from_src():
    """The subpackages rely on `packages.find`, which needs `where = ["src"]`.

    Asserted rather than assumed: if that ever drifts, the failure mode is
    the same silent one — fine locally, broken once installed.
    """
    manifest = _manifest()
    assert manifest["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert manifest["tool"]["setuptools"]["package-dir"] == {"": "src"}
    # Sanity check that there is actually something for it to find.
    assert {"routers", "services", "models", "schemas"} <= _subpackages()


def test_every_module_the_routers_import_is_importable_by_a_flat_name():
    """The routers import flat modules by bare name (`from rate_limit import …`).

    That only resolves if the name is either a declared flat module or a
    discovered subpackage — which is exactly the invariant the wheel has to
    satisfy, and exactly what broke.
    """
    installable = set(_manifest()["tool"]["setuptools"]["py-modules"]) | _subpackages()
    routers = SRC / "routers"

    referenced: set[str] = set()
    for path in routers.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("from ") or " import " not in line:
                continue
            module = line.split()[1]
            # Relative imports and stdlib/third-party names are not ours.
            if module.startswith("."):
                continue
            root = module.split(".")[0]
            if (SRC / f"{root}.py").exists() or (SRC / root).is_dir():
                referenced.add(root)

    missing = referenced - installable
    assert not missing, (
        f"routers import {sorted(missing)}, which the wheel would not contain."
    )


def test_the_modules_actually_import_under_their_flat_names():
    """Belt and braces: every declared module imports cleanly as a bare name.

    Catches a name listed in py-modules that doesn't correspond to a working
    import (a typo, or a module that only works as part of a package).
    """
    assert str(SRC) in sys.path or any(Path(p).resolve() == SRC for p in sys.path if p), (
        "conftest puts backend/src on sys.path; this test assumes that."
    )
    import importlib

    for name in _manifest()["tool"]["setuptools"]["py-modules"]:
        if name == "main":
            continue  # importing main builds the whole app; covered elsewhere
        importlib.import_module(name)
