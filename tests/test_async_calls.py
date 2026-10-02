"""Calling an async function without awaiting it does nothing (Python only
warns); the panel's "Send test alert" never refreshed the list this way."""
import ast
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_no_async_function_is_called_without_await():
    problems = []
    for path in glob.glob(os.path.join(ROOT, "webui", "*.py")) + \
            glob.glob(os.path.join(ROOT, "scripts", "**", "*.py"), recursive=True) + \
            [os.path.join(ROOT, "publish.py"), os.path.join(ROOT, "run.py")]:
        tree = ast.parse(open(path, encoding="utf-8").read())
        async_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        for n in ast.walk(tree):
            # A bare expression statement `f()` where f is async in this file.
            if (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Name) and n.value.func.id in async_names):
                problems.append(f"{os.path.relpath(path, ROOT)}:{n.lineno} {n.value.func.id}()")
    assert problems == []
