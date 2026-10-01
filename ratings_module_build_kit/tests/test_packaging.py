"""test_packaging.py — the worker's container holds every module the worker imports.

The Dockerfile copies three files and four folders. On 23 September 2026 a new module (uplevel.py)
was imported by service.py but missing from what was copied: every test passed on a laptop, and on
the server every UpLevel lookup crashed with "No module named 'uplevel'", which the website could
only report as "could not reach UpLevel".

Two checks. The first walks every local import reachable from service.py, including imports
inside functions, and requires each file to be copied and not ignored. The second builds the
container's layout in a temporary folder - exactly what the Dockerfile copies, nothing else - and
imports every one of those modules there, in a fresh Python.
"""
import ast
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

WORKER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def copied() -> tuple[set[str], set[str]]:
    """(files, folders) the Dockerfile copies into the image, relative to the worker folder."""
    text = open(os.path.join(WORKER, "Dockerfile"), encoding="utf-8").read()
    files: set[str] = set()
    folders: set[str] = set()
    for line in re.findall(r"^COPY\s+(.+)$", text, re.M):
        for src in line.split()[:-1]:                    # the last word is the destination
            if src.endswith(".py"):
                files.add(src)
            elif src.endswith("/"):
                folders.add(src.rstrip("/"))
    return files, folders


def is_copied(rel: str) -> bool:
    files, folders = copied()
    rel = rel.replace("\\", "/")
    return rel in files or rel.split("/")[0] in folders


def ignored_patterns() -> list[str]:
    path = os.path.join(WORKER, ".dockerignore")
    if not os.path.exists(path):
        return []
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]


def is_ignored(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    for p in ignored_patterns():
        if p.endswith("/"):
            if rel.startswith(p) or f"/{p}" in f"/{rel}":
                return True
        elif fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p):
            return True
    return False


def module_file(name: str) -> str | None:
    """The file a dotted module name stands for, relative to the worker folder, if it is ours."""
    base = name.replace(".", "/")
    for rel in (base + ".py", base + "/__init__.py"):
        if os.path.exists(os.path.join(WORKER, rel)):
            return rel
    return None


def local_imports(rel: str) -> set[str]:
    """Dotted names of the worker's own modules that the file imports anywhere in its body."""
    tree = ast.parse(open(os.path.join(WORKER, rel), encoding="utf-8").read())
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # "from feedback import engine" names feedback.engine; "from feedback.engine import X"
            # names feedback.engine too.
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        found.update(n for n in names if module_file(n))
    return found


def reachable_from(start: str) -> set[str]:
    seen: set[str] = set()
    todo = [start]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(local_imports(module_file(m)) - seen)
        if "." in m:                                     # importing a.b imports a/__init__.py too
            todo.append(m.rsplit(".", 1)[0])
    return seen


class TestTheContainerHasEveryModule(unittest.TestCase):
    def test_every_module_the_worker_imports_is_copied(self):
        needed = {module_file(m) for m in reachable_from("service")}
        missing = sorted(f for f in needed if not is_copied(f))
        self.assertEqual(missing, [], f"the Dockerfile does not copy: {missing}")

    def test_nothing_the_worker_needs_is_ignored(self):
        needed = {module_file(m) for m in reachable_from("service")}
        clashes = sorted(f for f in needed if is_ignored(f))
        self.assertEqual(clashes, [], f".dockerignore hides modules the container needs: {clashes}")

    def test_the_walk_sees_imports_inside_functions(self):
        # uplevel is imported inside the endpoints, not at the top of service.py; the walk must see it.
        self.assertIn("recordings.uplevel", local_imports("service.py"))

    def test_every_folder_of_modules_is_reached(self):
        """A folder the Dockerfile copies but nothing imports is dead weight; a folder of modules
        the Dockerfile does not copy is the 23 September failure waiting to happen."""
        _files, folders = copied()
        packages = {d for d in os.listdir(WORKER)
                    if os.path.exists(os.path.join(WORKER, d, "__init__.py"))}
        self.assertEqual(packages, folders)

    def test_the_container_layout_imports_every_module(self):
        """Build what the image holds and import all of it there. This is the check a laptop
        cannot otherwise make: on a laptop every file is always present."""
        files, folders = copied()
        modules = sorted(reachable_from("service"))
        with tempfile.TemporaryDirectory() as image:
            for f in files:
                shutil.copy(os.path.join(WORKER, f), os.path.join(image, f))
            for d in folders:
                shutil.copytree(os.path.join(WORKER, d), os.path.join(image, d),
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
            env.update({"DATABASE_URL": "postgresql://tests:tests@127.0.0.1:9/never",
                        "ANTHROPIC_API_KEY": "sk-ant-tests-not-a-real-key", "PYTHONDONTWRITEBYTECODE": "1"})
            code = ("import importlib, sys\n"
                    f"for m in {modules!r}:\n"
                    "    importlib.import_module(m)\n"
                    "print('ok', len(sys.modules))\n")
            run = subprocess.run([sys.executable, "-c", code], cwd=image, env=env,
                                 capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr[-1500:])
        self.assertIn("ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
