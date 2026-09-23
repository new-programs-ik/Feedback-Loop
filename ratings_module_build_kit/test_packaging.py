"""test_packaging.py — the worker's container holds every module the worker imports.

The Dockerfile copies the worker's files from an explicit list. On 23 September 2026 a new module
(uplevel.py) was imported by service.py but missing from that list: every test passed on a laptop,
and on the server every UpLevel lookup crashed with "No module named 'uplevel'", which the website
could only report as "could not reach UpLevel". This walks every local import reachable from
service.py, including imports inside functions, and checks each file is copied and not ignored.
"""
import ast
import fnmatch
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def copied_files() -> set[str]:
    text = open(os.path.join(HERE, "Dockerfile"), encoding="utf-8").read()
    files: set[str] = set()
    for line in re.findall(r"^COPY\s+(.+)$", text, re.M):
        parts = line.split()
        files.update(p for p in parts[:-1] if p.endswith(".py"))    # the last word is the destination
    return files


def ignored_patterns() -> list[str]:
    path = os.path.join(HERE, ".dockerignore")
    if not os.path.exists(path):
        return []
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]


def local_imports(module: str) -> set[str]:
    """Names of local modules (files in this folder) that `module` imports anywhere in its body."""
    tree = ast.parse(open(os.path.join(HERE, module + ".py"), encoding="utf-8").read())
    found: set[str] = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module.split(".")[0]]
        found.update(n for n in names if os.path.exists(os.path.join(HERE, n + ".py")))
    return found


def reachable_from(start: str) -> set[str]:
    seen, todo = set(), [start]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(local_imports(m) - seen)
    return seen


class TestTheContainerHasEveryModule(unittest.TestCase):
    def test_every_module_the_worker_imports_is_copied(self):
        needed = {m + ".py" for m in reachable_from("service")}
        missing = sorted(needed - copied_files())
        self.assertEqual(missing, [], f"add these to the Dockerfile COPY line: {missing}")

    def test_no_copied_module_is_ignored(self):
        patterns = ignored_patterns()
        clashes = sorted(f for f in copied_files() for p in patterns if fnmatch.fnmatch(f, p))
        self.assertEqual(clashes, [], f".dockerignore hides modules the container needs: {clashes}")

    def test_the_walk_sees_imports_inside_functions(self):
        # uplevel is imported inside the endpoints, not at the top of service.py; the walk must see it.
        self.assertIn("uplevel", local_imports("service"))


if __name__ == "__main__":
    unittest.main()
