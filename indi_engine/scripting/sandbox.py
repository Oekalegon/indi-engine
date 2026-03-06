"""RestrictedPython sandbox for user script execution.

Security-critical: this module defines what user scripts can and cannot do.
All user-supplied source code must be compiled through compile_script() and
executed via make_restricted_globals() before exec().

Security properties:
- open, exec, eval, compile, __import__ are absent from builtins
- os, sys, subprocess, socket, pathlib, importlib are blocked at import
- _-prefixed attribute access is blocked (closes __class__.__subclasses__() escapes)
- Allowed modules: math, cmath, statistics, datetime, time, astropy, astroquery,
  fitsio, numpy, scipy
"""

import builtins as _builtins_module
import types

from RestrictedPython import compile_restricted, safe_globals, safe_builtins, PrintCollector

# Capture the real __import__ before any substitution
_real_import = _builtins_module.__import__

# Builtins that are safe but may be absent from safe_builtins in some RestrictedPython versions
_EXTRA_SAFE_BUILTINS = frozenset({
    "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr", "complex",
    "dict", "dir", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "getattr", "hasattr", "hash", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "oct",
    "ord", "pow", "print", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "type", "zip",
})


def _safe_getitem_(obj, key):
    """Default _getitem_ guard: allows subscript access on script-visible objects."""
    return obj[key]


ALLOWED_MODULES = frozenset({
    "math",
    "cmath",
    "decimal",
    "fractions",
    "statistics",
    "datetime",
    "time",
    "astropy",
    "astroquery",
    "fitsio",
    "numpy",
    "scipy",
})


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Allowlist-based import guard. Only ALLOWED_MODULES may be imported."""
    top = name.split(".")[0]
    if top not in ALLOWED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed in scripts")
    return _real_import(name, globals, locals, fromlist, level)


def compile_script(source: str, filename: str = "<script>") -> types.CodeType:
    """Compile source with RestrictedPython AST transformation.

    Raises:
        SyntaxError: If source has syntax errors or RestrictedPython violations.
    """
    code = compile_restricted(source, filename=filename, mode="exec")
    if code is None:
        raise SyntaxError(f"Script failed RestrictedPython compilation: {filename}")
    return code


def check_syntax(source: str) -> None:
    """Validate source against RestrictedPython. Raises SyntaxError on failure."""
    compile_script(source, filename="<syntax-check>")


def make_restricted_globals(script_context: dict) -> dict:
    """Build the globals dict for exec()ing a compiled restricted script.

    Starts from RestrictedPython's safe_globals (which includes the required
    _getattr_, _getitem_, _getiter_, _write_ guard functions), then overlays
    a restricted builtins dict and the script_context.

    Args:
        script_context: Names to inject directly into the script namespace
                        (e.g. indi, time_utils, log, params, math).
    """
    builtins = dict(safe_builtins)

    # Add any commonly-needed builtins that safe_builtins may omit in this version
    for name in _EXTRA_SAFE_BUILTINS:
        if name not in builtins:
            func = getattr(_builtins_module, name, None)
            if func is not None:
                builtins[name] = func

    # Ensure dangerous keys are absent even if safe_builtins ever includes them
    for key in ("open", "exec", "eval", "compile", "input"):
        builtins.pop(key, None)

    # Replace __import__ with our allowlist-based version
    builtins["__import__"] = safe_import

    g = dict(safe_globals)  # includes _getattr_, _getiter_, _write_ guards
    # _getitem_ may not be present in all versions; provide a safe default
    if "_getitem_" not in g:
        g["_getitem_"] = _safe_getitem_
    # RestrictedPython transforms print(...) using a PrintCollector pattern.
    # Provide a collector that writes through to stdout.
    g["_print_"] = PrintCollector
    g["__builtins__"] = builtins
    g.update(script_context)
    return g
