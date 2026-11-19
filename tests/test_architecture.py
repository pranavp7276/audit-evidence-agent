"""The code is a stack of layers; a layer may import only from layers below it (docs/architecture.md).

A layer that imports upward, or two layers in the same band that import each other, turns the stack back into a tangle, so this test fails the build.
"""
import ast
from pathlib import Path

# package -> layer number. Packages with the same number are siblings and must not import each other.
LAYERS = {"core": 0, "tools": 1, "checks": 2, "knowledge": 2, "intake": 2, "runtime": 3, "services": 4, "web": 5, "__main__": 5}
ROOT = Path(__file__).resolve().parents[1] / "agent"


def _imports(path: Path) -> set[str]:
    found = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and n.module.split(".")[0] == "agent":
            parts = n.module.split(".")
            found.add(parts[1] if len(parts) > 1 else n.names[0].name)  # "from agent import x" names the package x
        elif isinstance(n, ast.Import):
            found |= {a.name.split(".")[1] for a in n.names if a.name.startswith("agent.")}
    return found


def _package(path: Path) -> str:
    return path.relative_to(ROOT).parts[0].removesuffix(".py")


def test_every_package_has_a_layer():
    packages = {_package(p) for p in ROOT.rglob("*.py")} - {"__init__"}
    assert packages <= set(LAYERS), f"add a layer for: {sorted(packages - set(LAYERS))}"


def test_imports_only_point_down():
    bad = []
    for path in ROOT.rglob("*.py"):
        src = _package(path)
        if src not in LAYERS:
            continue
        for dst in _imports(path):
            if dst == src or dst not in LAYERS:
                continue
            if LAYERS[dst] >= LAYERS[src]:
                bad.append(f"{path.relative_to(ROOT.parent).as_posix()}: {src} (layer {LAYERS[src]}) imports {dst} (layer {LAYERS[dst]})")
    assert not bad, "layers must only import downward:\n" + "\n".join(bad)


def test_the_agent_runtime_never_writes():
    """Persisting results is the services layer's job (docs/decisions.md D-023)."""
    for path in (ROOT / "runtime").glob("*.py"):
        assert "services" not in _imports(path), f"{path.name} imports services"
        text = path.read_text(encoding="utf-8")
        assert "INSERT INTO" not in text and "UPDATE audit" not in text, f"{path.name} writes to the database"


def test_paths_that_depend_on_the_repository_root_still_resolve():
    """Moving a module changes how many parents up the repository root is; the .env file and the pack folder hang off it."""
    from agent.core import db
    from agent.services import pack
    root = ROOT.parent
    assert Path(db.__file__).resolve().parents[2] == root
    assert pack.OUT == root / "out"
