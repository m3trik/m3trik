#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The Maya/Blender parity gate: every toolkit call a shared tentacle Slots class makes
resolves on both hosts.

One Slots class per marking-menu category (``slots/<category>.py``) and per tool
(``slots/tools/<tool>.py``, its helpers in ``slots/tools/_<tool>/``) serves Maya and
Blender, reaching the host through ``self.tk`` (``mtk`` / ``btk``). So parity means:
each ``tk.<chain>`` the shared slots read resolves on mayatk AND blendertk -- the same
name, and a signature that takes the call's arguments (too many positionals, an unknown
keyword, a missing required argument) -- unless the host that lacks it never runs it.
Every read counts: through ``self.tk`` or any name bound to the toolkit or to a chain of
it (``t = self.tk``, ``env = self.tk.EnvUtils``, ``fn = getattr(tk.X, "f", None)``), a
name a literal class table supplies (``getattr(tk.X, self.OPS[key])``, unrolled over the
table), and members of what a toolkit call returns (``self.x = tk.Engine(...)``,
``tk.A.create(...)``, annotated ``self.x: T = ...``, a ``cached_property`` or a lazy
property over ``self._engine``; a function's result is its annotation or its ``return``).

What keeps a read off a host:

* **requires** -- the Slots class's handler shows where its widget does: the widget's
  ``.ui`` tag (``ui/<category>.ui`` / ``ui/<category>#*.ui`` / ``ui/tools/<tool>.ui``;
  blank means every host, as uitk reads it), a code-built row of a table the class tags
  from (a tuple literal naming the method and a host, ``("Cleanup Unknown", "b006", tip,
  "maya")``), or ``Slots.requires(widget, host)``. ``<widget>_init`` is NOT hidden: uitk
  runs it on every host (``MainWindow.register_widget`` applies the policy, then
  ``init_slot``). A ``requires`` speaks for the Slots class only, not another class of
  the module with a method of the same name.
* **HOSTS / STANDALONE** -- the tool serves one host (``slots.tools.HOSTS``), or is a
  standalone panel with no host at all (``slots.tools.STANDALONE``).
* **a capability check is a host limit** -- ``hasattr(X, "f")``, ``getattr(X, "f", d)``
  (``is None`` / ``is not None`` / truth), directly, through a local, through a helper
  method whose ``return`` makes one (``self._has(*ops)``, ``self._unsupported(button)``,
  inlined with the call's arguments), or through a hide (``Slots.hide_unless(widget,
  <check>)``, ``widget.setVisible(<check>)``, which hide the widget's handler). The
  checked name is resolved on each host: the code the check dominates is excused on
  exactly the hosts where the answer rules it out, with polarity read (``not``, ``and`` /
  ``or``, else-branches, code after an exit only when the exiting branch is the one
  where the name is missing). A check on another name, or on an owner
  (``hasattr(tk, "CoreUtils")``), excuses nothing its answer does not rule out. A
  ``getattr(..., None)(...)`` called with no check is a plain read. ``setEnabled`` is
  not a hide: a disabled control's slot can still run (repeat-last).
* **caught** -- a direct read inside a ``try`` that catches ``AttributeError``; a lambda
  or a def inside it runs later, uncaught.

A private method takes the hosts and conditions of every place its class references it
(a call, or a callback it wires); one that anything outside the class reads (a helper
module's ``slots._apply()``) or a string names (a dispatch table, ``getattr(self, ...)``)
is also an entry point, as every public one is. Nested classes are scanned as classes.

Static: both libraries are read from source -- the root namespace as pythontk's module
resolver builds it from ``DEFAULT_INCLUDE`` (wildcard modules, flat class methods, ``->``
aliases, ``MOVED_NAMES``; a ``DEFAULT_INCLUDE`` that is not a literal exits 2), each
class's MRO across the workspace packages (pythontk, uitk, ...), class and instance
attributes, class tables, metaclasses. Nothing is imported but the standard library.
``API_REGISTRY.json`` is not read: it lists public members only (no class or instance
attributes, no private mixins) and lags the working tree until regenerated.

Listed, never failed (the static model cannot prove absence there): *unverified* reads
-- past a value the model cannot see into (a property's or an unannotated call's value,
a base class outside the workspace, a module ``__getattr__``) or under a name computed
at runtime -- and the calls whose signature check is skipped: ``f(*args)``, and a target
taking ``*args`` / ``**kwargs`` the call relies on (forwarding). The sweep also lints
every tentacle ``.ui`` for a promoted class missing from ``<customwidgets>`` (it would
silently load as a plain ``QWidget``). Exit 1 on a gap or a lint, 2 when a library
cannot be read.

Usage:
    python compare_panel_surface.py --all            # sweep, print the report
    python compare_panel_surface.py --all --write    # also rewrite tentacle/docs/PARITY_SURFACE.md
    python compare_panel_surface.py --panel <name>   # one Slots file (stem, file or class): every call
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import dataclasses
import importlib
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
#: Host tag (``requires`` / ``slots.tools.HOSTS``) -> the library ``self.tk`` is there.
HOST_PACKAGES = {"maya": "mayatk", "blender": "blendertk"}
ALL_HOSTS = frozenset(HOST_PACKAGES)
#: Names ``bootstrap_package`` installs in a package root besides the resolved surface.
_RESOLVER_GLOBALS = {
    "CLASS_TO_MODULE", "METHOD_TO_MODULE", "IMPORTED_MODULES", "MODULE_TO_PARENT",
    "configure", "build_dictionaries", "import_module", "get_attribute_from_module",
    "export_all", "_RESOLVER", "PACKAGE_RESOLVER", "__all__", "__getattr__",
}
_SAFE_DECORATORS = {"staticmethod", "classmethod", "abstractmethod", "override", "overload"}
_EXITS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_STDLIB = getattr(sys, "stdlib_module_names", frozenset())


def _surface_out(root: Path) -> Path:
    return Path(root) / "tentacle" / "docs" / "PARITY_SURFACE.md"


def _public(name: str) -> bool:
    return not name.startswith("_")


def _deco_names(node) -> List[str]:
    out = []
    for d in node.decorator_list:
        d = d.func if isinstance(d, ast.Call) else d
        out.append(d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", ""))
    return out


# =========================================================================== static values
@dataclass(frozen=True)
class Missing:
    why: str


@dataclass(frozen=True)
class Opaque:
    """A value the static model cannot see into: anything read off it passes.

    *seen* when the chain reached real data (a constant, a property's or a call's value,
    an attribute set at runtime): the toolkit surface ends there, so the read is
    resolved. Otherwise the model could not look (a base class outside the workspace, a
    module ``__getattr__``) and the read passes *unverified*.
    """

    why: str
    seen: bool = False


@dataclass(frozen=True)
class Real:
    """A standard-library object (a real ``threading.Thread``, ``builtins.object``)."""

    obj: object


@dataclass(frozen=True)
class ModuleV:
    module: "Module"


@dataclass(frozen=True)
class ClassV:
    node: ast.ClassDef
    module: "Module"

    @property
    def name(self):
        return self.node.name


@dataclass(frozen=True)
class InstanceV:
    cls: ClassV


@dataclass(frozen=True)
class AliasV:
    """A ``"module->Alias"`` include entry: one class fused from a module's classes."""

    name: str
    classes: Tuple[ClassV, ...]


@dataclass(frozen=True)
class FuncV:
    node: ast.AST
    kind: str  # function / method / classmethod / staticmethod
    instance: bool = False  # read off an instance (a method then binds self)
    owner: Optional["ClassV"] = None  # the class that defines it
    module: Optional["Module"] = None  # where its body resolves names
    receiver: Optional["ClassV"] = None  # the class it is read off (``cls`` at the call)


@dataclass(frozen=True)
class CallShape:
    npos: int
    kws: Tuple[str, ...]
    star: bool


# =========================================================================== source model
class Module:
    """One module's top-level bindings, parsed once."""

    def __init__(self, ws: "Workspace", dotted: str, path: Path, is_pkg: bool):
        self.ws, self.dotted, self.path, self.is_pkg = ws, dotted, path, is_pkg
        self.package = dotted if is_pkg else dotted.rpartition(".")[0]
        try:
            self.tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            self.tree = ast.Module(body=[], type_ignores=[])
        self.bindings: Dict[str, tuple] = {}
        self.stars: List[str] = []
        self.lazy: Dict[str, str] = {}
        self.getattr_hook = False
        self.bootstrap: Optional[Dict[str, ast.AST]] = None
        self._collect(self.tree.body)

    def _absolute(self, node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module or ""
        parts = self.package.split(".")
        parts = parts[: len(parts) - (node.level - 1)]
        return ".".join(parts + ([node.module] if node.module else []))

    def _bind(self, name, binding):
        self.bindings.setdefault(name, binding)

    def _collect(self, body):
        for node in body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self._bind(node.name, ("node", node))
                if node.name == "__getattr__":
                    self.getattr_hook = True
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._bind(target.id, ("expr", node.value))
                        self.getattr_hook |= target.id == "__getattr__"
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                self._bind(elt.id, ("opaque",))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self._bind(node.target.id, ("expr", node.value) if node.value else ("opaque",))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self._bind(alias.asname, ("module", alias.name))
                    else:
                        top = alias.name.split(".")[0]
                        self._bind(top, ("module", top))
            elif isinstance(node, ast.ImportFrom):
                source = self._absolute(node)
                for alias in node.names:
                    if alias.name == "*":
                        self.stars.append(source)
                    else:
                        self._bind(alias.asname or alias.name, ("from", source, alias.name))
            elif isinstance(node, ast.If):
                self._collect(node.body)
                self._collect(node.orelse)
            elif isinstance(node, ast.Try):
                self._collect(node.body)
                for handler in node.handlers:
                    self._collect(handler.body)
                self._collect(node.orelse)
                self._collect(node.finalbody)
            elif isinstance(node, ast.With):
                self._collect(node.body)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._collect_call(node.value)

    def _collect_call(self, call: ast.Call):
        name = getattr(call.func, "id", getattr(call.func, "attr", ""))
        if name == "bootstrap_package":
            self.bootstrap = {k.arg: k.value for k in call.keywords if k.arg}
        elif name == "lazy_exports" and len(call.args) > 1:
            try:
                sources = ast.literal_eval(call.args[1])
            except ValueError:
                return
            for sub, names in sources.items():
                for n in (names,) if isinstance(names, str) else names:
                    self.lazy[n] = f"{self.dotted}.{sub}"

    def literal(self, name):
        """The literal value of a top-level ``name = {...}`` (``DEFAULT_INCLUDE``)."""
        binding = self.bindings.get(name)
        if binding and binding[0] == "expr":
            try:
                return ast.literal_eval(binding[1])
            except (ValueError, TypeError, SyntaxError):
                return None
        return None

    def attr(self, name):
        if self.bootstrap is not None and self.dotted == self.package.split(".")[0]:
            return self.ws.package(self.dotted).root_lookup(name)
        return self.plain_attr(name)

    def plain_attr(self, name):
        binding = self.bindings.get(name)
        if binding:
            return self.ws.eval_binding(self, name, binding)
        if name in self.lazy:
            sub = self.ws.module(self.lazy[name])
            return sub.attr(name) if sub else Missing(f"{self.lazy[name]} not found")
        if _public(name):
            for star in self.stars:
                src = self.ws.module(star)
                value = src.attr(name) if src else Opaque(f"from {star} import *")
                if not isinstance(value, Missing):
                    return value
        if self.is_pkg:
            sub = self.ws.module(f"{self.dotted}.{name}")
            if sub:
                return ModuleV(sub)
        if name in ("__name__", "__file__", "__package__", "__doc__"):
            return Real("")
        if name.startswith("__") and name.endswith("__"):
            return Opaque("module attribute", seen=True)
        if self.getattr_hook:
            return Opaque(f"{self.dotted}.__getattr__")
        return Missing(f"{self.dotted} has no {name!r}")


def _side_effect_free(statements) -> bool:
    """pythontk's ``ModuleAttributeResolver._statements_are_side_effect_free``: the
    module is scanned lazily (classes AND functions) instead of imported (classes)."""
    for node in statements:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.If):
            test = node.test
            main = (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__")
            if main:
                if not _side_effect_free(node.orelse):
                    return False
                continue
            if not (_side_effect_free(node.body) and _side_effect_free(node.orelse)):
                return False
            continue
        if isinstance(node, ast.Try):
            if not all(_side_effect_free(b) for b in (node.body, node.orelse, node.finalbody)):
                return False
            continue
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign, ast.Pass)):
            return False
    return True


def _defined_classes(body):
    """Classes a module defines at import, inside top-level ``if`` / ``try`` too."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            yield node
        elif isinstance(node, ast.If):
            yield from _defined_classes(node.body)
            yield from _defined_classes(node.orelse)
        elif isinstance(node, ast.Try):
            for block in (node.body, node.orelse, node.finalbody, *(h.body for h in node.handlers)):
                yield from _defined_classes(block)


class Package:
    """A workspace package's root namespace, as ``bootstrap_package`` resolves it."""

    def __init__(self, ws: "Workspace", name: str, src: Path):
        self.ws, self.name, self.src = ws, name, src
        self._built = False

    def _walk(self, directory: Path, prefix: str):
        """``pkgutil.walk_packages`` order: each directory sorted, depth first."""
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.is_dir():
                if "." in entry.name or not (entry / "__init__.py").is_file():
                    continue
                yield f"{prefix}{entry.name}"
                yield from self._walk(entry, f"{prefix}{entry.name}.")
            elif entry.suffix == ".py" and entry.stem != "__init__" and "." not in entry.stem:
                yield f"{prefix}{entry.stem}"

    def _build(self):
        self._built = True
        root = self.ws.module(self.name)
        boot = root.bootstrap or {}
        include = self._kw_literal(root, boot.get("include"))
        if boot.get("include") is not None and include is None:
            raise GateError(
                f"{self.name}: bootstrap_package(include=...) is not a literal (its "
                "DEFAULT_INCLUDE must be a dict literal for the gate to read the root "
                "namespace without importing the package)")
        self.moved = self._kw_literal(root, boot.get("moved")) or {}
        self.custom_getattr = "custom_getattr" in boot
        self.class_to_module: Dict[str, str] = {}
        self.method_to_module: Dict[str, Tuple[str, str]] = {}
        self.aliases: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        if root.bootstrap is None:
            return
        direct, absolute = {}, {}
        for key, value in (include or {}).items():
            module_key, alias = key, None
            if "->" in key:
                module_key, alias = (s.strip() for s in key.split("->", 1))
            norm = (("*",) if value in (None, "*") else
                    (value,) if isinstance(value, str) else tuple(value))
            if alias:
                self.aliases[alias] = (module_key, norm)
            if "." in module_key:
                absolute[f"{self.name}.{module_key}"] = norm
            else:
                direct[module_key] = norm
        for dotted in self._walk(self.src, f"{self.name}."):
            if include is None:
                classes = ("*",)
            elif dotted in absolute:
                classes = absolute[dotted]
            elif dotted.split(".")[-1] in direct:
                classes = direct[dotted.split(".")[-1]]
            else:
                continue
            if "*" not in classes:
                for c in classes:
                    self.class_to_module[c] = dotted
                continue
            mod = self.ws.module(dotted)
            if mod is None:
                continue
            if _side_effect_free(mod.tree.body):
                found = False
                for node in mod.tree.body:
                    if isinstance(node, ast.ClassDef) and _public(node.name):
                        found = True
                        self.class_to_module[node.name] = dotted
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and _public(item.name):
                                self.method_to_module[item.name] = (dotted, node.name)
                    elif isinstance(node, ast.FunctionDef) and _public(node.name):
                        found = True
                        self.class_to_module[node.name] = dotted
                if found:
                    continue
            for node in _defined_classes(mod.tree.body):
                self.class_to_module[node.name] = dotted
                for item in node.body:
                    if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                            and _public(item.name)):
                        self.method_to_module[item.name] = (dotted, node.name)

    @staticmethod
    def _kw_literal(root: Module, node):
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return root.literal(node.id)
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return None

    def _alias(self, name: str):
        module_key, names = self.aliases[name]
        mod = self.ws.module(f"{self.name}.{module_key}")
        classes = []
        if names == ("*",) and mod is not None:
            sources = [mod]
            if mod.is_pkg:
                sources = [self.ws.module(f"{mod.dotted}.{p.stem}")
                           for p in sorted(mod.path.parent.glob("*.py")) if p.stem != "__init__"]
            for src in filter(None, sources):
                classes += [ClassV(n, src) for n in _defined_classes(src.tree.body)
                            if _public(n.name)]
        else:
            for n in names:
                value = mod.plain_attr(n) if mod else self.root_lookup(n)
                if not isinstance(value, ClassV):
                    return Missing(f"{self.name}.{name} cannot be built ({n})")
                classes.append(value)
        return AliasV(name, tuple(classes)) if classes else Missing(f"{self.name}.{name} is empty")

    def root_lookup(self, name: str):
        if not self._built:
            self._build()
        root = self.ws.module(self.name)
        if name in root.bindings:
            return self.ws.eval_binding(root, name, root.bindings[name])
        if name in _RESOLVER_GLOBALS:
            return Opaque("resolver helper", seen=True)
        if name in self.aliases:
            return self._alias(name)
        if name in self.class_to_module:
            mod = self.ws.module(self.class_to_module[name])
            return mod.plain_attr(name) if mod else Missing(f"{self.class_to_module[name]} not found")
        if name in self.method_to_module:
            dotted, cls = self.method_to_module[name]
            return self.ws.getattr(self.ws.module(dotted).plain_attr(cls), name)
        sub = self.ws.module(f"{self.name}.{name}")
        if sub:
            return ModuleV(sub)
        if _public(name):
            for alias in self.aliases:
                fused = self._alias(alias)
                for cls in getattr(fused, "classes", ()):
                    if cls.name == name:
                        return cls
        if name in self.moved:
            new_home, version = self.moved[name]
            return Missing(f"moved to {new_home} ({version})")
        if name in ("__name__", "__file__", "__package__", "__doc__"):
            return Real("")
        if name.startswith("__") and name.endswith("__"):
            return Opaque("module attribute", seen=True)
        if self.custom_getattr:
            return Opaque(f"{self.name}'s custom __getattr__")
        return Missing(f"{self.name} has no {name!r}")


class _ClassInfo:
    """A class body's members, and the attributes its methods assign."""

    def __init__(self, node: ast.ClassDef):
        self.members: Dict[str, ast.AST] = {}
        self.instance_attrs, self.class_attrs = set(), set()
        self._collect(node.body)
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or not item.args.args:
                continue
            first = item.args.args[0].arg
            target_set = self.class_attrs if "classmethod" in _deco_names(item) else self.instance_attrs
            for n in ast.walk(item):
                targets = (n.targets if isinstance(n, ast.Assign) else
                           [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign)) else [])
                for t in targets:
                    for t2 in (t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]):
                        if (isinstance(t2, ast.Attribute) and isinstance(t2.value, ast.Name)
                                and t2.value.id == first):
                            target_set.add(t2.attr)
                if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "setattr"
                        and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)
                        and getattr(n.args[0], "id", "") == first):
                    target_set.add(n.args[1].value)

    def _collect(self, body):
        for item in body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.members.setdefault(item.name, item)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    for t2 in (t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]):
                        if isinstance(t2, ast.Name):
                            self.members.setdefault(t2.id, item)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                self.members.setdefault(item.target.id, item)
            elif isinstance(item, ast.If):
                self._collect(item.body)
                self._collect(item.orelse)
            elif isinstance(item, ast.Try):
                self._collect(item.body)
                self._collect(item.orelse)


class Workspace:
    """Static model of the ecosystem sources under *root*: nothing is imported."""

    def __init__(self, root):
        self.root = Path(root)
        self._modules: Dict[str, Optional[Module]] = {}
        self._packages: Dict[str, Optional[Package]] = {}
        self._infos: Dict[int, _ClassInfo] = {}
        self._mros: Dict[int, tuple] = {}
        self._active = set()

    # ------------------------------------------------------------------ modules
    def package(self, name: str) -> Optional[Package]:
        if name not in self._packages:
            src = self.root / name / name
            self._packages[name] = Package(self, name, src) if (src / "__init__.py").is_file() else None
        return self._packages[name]

    def module(self, dotted: str) -> Optional[Module]:
        if dotted not in self._modules:
            parts = dotted.split(".")
            pkg = self.package(parts[0]) if parts[0] else None
            mod = None
            if pkg is not None:
                base = pkg.src.joinpath(*parts[1:])
                if (base / "__init__.py").is_file():
                    mod = Module(self, dotted, base / "__init__.py", True)
                elif len(parts) > 1 and base.with_suffix(".py").is_file():
                    mod = Module(self, dotted, base.with_suffix(".py"), False)
            self._modules[dotted] = mod
        return self._modules[dotted]

    def external(self, dotted: str, attr: Optional[str] = None):
        """A name from outside the workspace: real when it is the standard library's."""
        if dotted.split(".")[0] not in _STDLIB:
            return Opaque(f"{dotted} is outside the workspace")
        try:
            obj = importlib.import_module(dotted)
        except Exception:  # noqa: BLE001 - any stdlib import failure: unverifiable
            return Opaque(f"{dotted} did not import")
        if attr is None:
            return Real(obj)
        return Real(getattr(obj, attr)) if hasattr(obj, attr) else Missing(f"{dotted} has no {attr!r}")

    # ------------------------------------------------------------------ evaluation
    def eval_binding(self, mod: Module, name: str, binding: tuple):
        key = (mod.dotted, name)
        if key in self._active:
            return Opaque("import cycle")
        self._active.add(key)
        try:
            kind = binding[0]
            if kind == "node":
                node = binding[1]
                return ClassV(node, mod) if isinstance(node, ast.ClassDef) else \
                    FuncV(node, "function", module=mod)
            if kind == "expr":
                return self.eval_expr(binding[1], mod)
            if kind == "from":
                _, source, attr = binding
                src = self.module(source)
                if src is not None:
                    return src.attr(attr)
                sub = self.module(f"{source}.{attr}")
                return ModuleV(sub) if sub else self.external(source, attr)
            if kind == "module":
                src = self.module(binding[1])
                return ModuleV(src) if src else self.external(binding[1])
            return Opaque("unpacked assignment", seen=True)
        finally:
            self._active.discard(key)

    def eval_expr(self, expr, mod: Module, cls: Optional[ClassV] = None):
        if isinstance(expr, ast.Name):
            if cls is not None and expr.id in self.info(cls).members:
                return self.member(cls, expr.id, self.info(cls).members[expr.id], False)
            value = mod.attr(expr.id)
            if isinstance(value, Missing) and hasattr(builtins, expr.id):
                return Real(getattr(builtins, expr.id))
            return value
        if isinstance(expr, ast.Attribute):
            return self.getattr(self.eval_expr(expr.value, mod, cls), expr.attr)
        if isinstance(expr, ast.Call):
            func = self.eval_expr(expr.func, mod, cls)
            if isinstance(func, ClassV):
                return InstanceV(func)
            if isinstance(func, Real) and func.obj in (staticmethod, classmethod) and expr.args:
                inner = self.eval_expr(expr.args[0], mod, cls)
                kind = func.obj.__name__
                return FuncV(inner.node, kind) if isinstance(inner, FuncV) else inner
            return Opaque("a call's result", seen=True)
        return Opaque("a value", seen=True)

    def getattr(self, value, name: str):
        if isinstance(value, Missing):
            return value
        if isinstance(value, Opaque):
            # Past real data (a property's value, a call's result) the read is the
            # value's, which the model cannot see: unverified.
            return Opaque(f"read past {value.why}") if value.seen else value
        if isinstance(value, ModuleV):
            return value.module.attr(name)
        if isinstance(value, ClassV):
            return self.class_attr(value, name, instance=False)
        if isinstance(value, InstanceV):
            return self.class_attr(value.cls, name, instance=True)
        if isinstance(value, AliasV):
            for cls in value.classes:
                found = self.class_attr(cls, name, instance=False)
                if not isinstance(found, Missing):
                    return found
            return Missing(f"{value.name} has no {name!r}")
        if isinstance(value, Real):
            return Real(getattr(value.obj, name)) if hasattr(value.obj, name) else \
                Missing(f"{value.obj!r} has no {name!r}")
        return Opaque("a function's attribute", seen=True)

    def call_result(self, value):
        """``value(...)``: an instance of a class; what a function returns, when its
        annotation or its ``return`` says; anything else is unverified."""
        if isinstance(value, Missing):
            return value
        if isinstance(value, Opaque):
            return Opaque(f"a call on {value.why}") if value.seen else value
        if isinstance(value, ClassV):
            return InstanceV(value)
        if isinstance(value, FuncV):
            return self._returns(value)
        return Opaque("a call's result")

    _CONTAINERS = {
        "dict": {}, "Dict": {}, "Mapping": {}, "MutableMapping": {}, "list": [], "List": [],
        "Sequence": [], "Iterable": [], "tuple": (), "Tuple": (), "set": set(), "Set": set(),
        "frozenset": frozenset(), "FrozenSet": frozenset(), "str": "", "int": 0, "float": 0.0,
        "bool": False, "bytes": b"",
    }

    def _returns(self, fn: FuncV):
        """What *fn* returns: its annotation (a workspace class, a builtin container,
        ``Optional[X]``), else its ``return cls(...)`` / ``return Name(...)`` / a literal."""
        mod = fn.module or (fn.owner.module if fn.owner else None)
        if mod is None:
            return Opaque("a call's result", seen=True)
        node = fn.node
        target = fn.receiver or fn.owner
        if node.returns is not None:
            got = self._annotation(node.returns, mod, fn.owner)
            if (isinstance(got, InstanceV) and target is not None and fn.owner is not None
                    and got.cls.node is fn.owner.node):
                return InstanceV(target)  # ``-> "KeyStash"`` read off a subclass is the subclass
            if got is not None:
                return got
        for r in (n for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None):
            value = r.value
            if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "cls" and target:
                return InstanceV(target)
            if isinstance(value, ast.Name) and value.id == "self" and target:
                return InstanceV(target)
            if isinstance(value, ast.Call):
                got = self.eval_expr(value, mod, fn.owner)
                if isinstance(got, InstanceV):
                    return got
            if isinstance(value, (ast.Dict, ast.List, ast.Tuple, ast.Set, ast.JoinedStr)):
                return Real({ast.Dict: {}, ast.List: [], ast.Tuple: (), ast.Set: set(),
                             ast.JoinedStr: ""}[type(value)])
            break
        return Opaque("a call's result", seen=True)

    def _annotation(self, ann, mod, owner):
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                ann = ast.parse(ann.value, mode="eval").body
            except SyntaxError:
                return None
        if isinstance(ann, ast.Constant) and ann.value is None:
            return Real(None)
        if isinstance(ann, ast.Subscript):
            head = getattr(ann.value, "id", getattr(ann.value, "attr", ""))
            if head == "Optional":
                return self._annotation(ann.slice, mod, owner)
            if head == "Union":
                items = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
                kept = [i for i in items if not (isinstance(i, ast.Constant) and i.value is None)]
                return self._annotation(kept[0], mod, owner) if len(kept) == 1 else None
            if head in self._CONTAINERS:
                return Real(self._CONTAINERS[head])
            return None
        if isinstance(ann, (ast.Name, ast.Attribute)):
            head = getattr(ann, "id", getattr(ann, "attr", ""))
            if head in self._CONTAINERS:
                return Real(self._CONTAINERS[head])
            got = self.eval_expr(ann, mod, owner)
            if isinstance(got, ClassV):
                return InstanceV(got)
        return None

    # ------------------------------------------------------------------ classes
    def info(self, cls: ClassV) -> _ClassInfo:
        key = id(cls.node)
        if key not in self._infos:
            self._infos[key] = _ClassInfo(cls.node)
        return self._infos[key]

    def mro(self, cls: ClassV):
        """``(classes, bases outside the model)``, depth first, left to right."""
        key = id(cls.node)
        if key in self._mros:
            return self._mros[key]
        self._mros[key] = ([cls], [])  # a cyclic base reads the partial answer
        out, open_bases, seen = [], [], set()

        def visit(c: ClassV):
            if id(c.node) in seen:
                return
            seen.add(id(c.node))
            out.append(c)
            for base in c.node.bases:
                if isinstance(base, ast.Subscript):
                    base = base.value
                value = self.eval_expr(base, c.module)
                if isinstance(value, ClassV):
                    visit(value)
                elif isinstance(value, AliasV):
                    for fused in value.classes:
                        visit(fused)
                elif not (isinstance(value, Real) and value.obj is object):
                    open_bases.append(value)

        visit(cls)
        self._mros[key] = (out, open_bases)
        return self._mros[key]

    def _metaclasses(self, classes):
        for c in classes:
            for kw in c.node.keywords:
                if kw.arg == "metaclass":
                    yield self.eval_expr(kw.value, c.module)

    def member(self, owner: ClassV, name: str, node, instance: bool):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos = _deco_names(node)
            if any("property" in d or d in ("setter", "getter", "deleter") for d in decos):
                return Opaque("a property's value", seen=True)
            kind = ("staticmethod" if "staticmethod" in decos else
                    "classmethod" if "classmethod" in decos else "method")
            return FuncV(node, kind, instance, owner, owner.module)
        if isinstance(node, ast.ClassDef):
            return ClassV(node, owner.module)
        value = getattr(node, "value", None)
        if value is None:
            return Opaque("an annotated field", seen=True)
        try:
            return Real(_literal(value))  # a table the code reads (``.get``, ``.items``)
        except (ValueError, TypeError, SyntaxError):
            pass
        key = (owner.module.dotted, owner.name, name)
        if key in self._active:
            return Opaque("a self-referencing attribute", seen=True)
        self._active.add(key)
        try:
            found = self.eval_expr(value, owner.module, owner)
        finally:
            self._active.discard(key)
        if isinstance(found, FuncV) and found.kind == "function":
            return FuncV(found.node, "method", instance, owner, found.module or owner.module)
        if isinstance(found, Missing):
            return Opaque("a class attribute", seen=True)
        return found

    def class_attr(self, cls: ClassV, name: str, instance: bool):
        classes, open_bases = self.mro(cls)
        for c in classes:
            node = self.info(c).members.get(name)
            if node is not None:
                found = self.member(c, name, node, instance)
                if isinstance(found, FuncV):
                    found = dataclasses.replace(found, receiver=cls)
                return found
        if any(name in self.info(c).class_attrs or (instance and name in self.info(c).instance_attrs)
               for c in classes):
            return Opaque("an attribute set at runtime", seen=True)
        if instance and any("__getattr__" in self.info(c).members for c in classes):
            return Opaque("a __getattr__")
        if not instance:
            for meta in self._metaclasses(classes):
                if isinstance(meta, ClassV):
                    found = self.class_attr(meta, name, instance=True)
                    if not isinstance(found, Missing):
                        return found
                elif isinstance(meta, Real) and hasattr(meta.obj, name):
                    return Real(getattr(meta.obj, name))
        for base in open_bases:
            if isinstance(base, Real) and hasattr(base.obj, name):
                return Real(getattr(base.obj, name))
        if hasattr(object if instance else type, name):
            return Opaque("a builtin attribute", seen=True)
        unknown = [b for b in open_bases if not isinstance(b, Real)]
        if unknown:
            why = getattr(unknown[0], "why", type(unknown[0]).__name__)
            return Opaque(f"{cls.name} has a base the model cannot read ({why})")
        return Missing(f"{cls.name} has no {name!r}")

    # ------------------------------------------------------------------ signatures
    def arity(self, value, call: Optional[CallShape]) -> Tuple[Optional[str], Optional[str]]:
        """``(why *call* cannot bind to *value*'s signature or None, note)``: the note
        says the check was skipped -- ``"starred"`` (``f(*args)``) or ``"forwarded"``
        (the target takes ``*args`` / ``**kwargs`` the call relies on)."""
        if call is None:
            return None, None
        if isinstance(value, ClassV):
            init = self.class_attr(value, "__init__", instance=True)
            if not isinstance(init, FuncV):
                return None, None
            value, where = init, f"{value.name}()"
        elif isinstance(value, FuncV):
            where = "the call"
        else:
            return None, None
        if call.star:
            return None, "starred"
        a = value.node.args
        params = [(p, True) for p in a.posonlyargs] + [(p, False) for p in a.args]
        defaults = len(a.defaults)
        required = [i < len(params) - defaults for i in range(len(params))]
        if value.kind == "classmethod" or (value.kind == "method" and value.instance):
            params, required = params[1:], required[1:]
        if a.vararg is None and call.npos > len(params):
            return f"{where} passes {call.npos} positional argument(s); it takes {len(params)}", None
        keyword_ok = {p.arg for p, posonly in params if not posonly} | {p.arg for p in a.kwonlyargs}
        unknown = [k for k in call.kws if k not in keyword_ok]
        if a.kwarg is None and unknown:
            return f"{where} passes {', '.join(unknown)}=, which it does not take", None
        note = "forwarded" if (unknown or call.npos > len(params)) else None
        if set(_deco_names(value.node)) - _SAFE_DECORATORS:
            return None, note  # a wrapper may supply arguments the def requires
        given = set(call.kws)
        missing = [p.arg for i, ((p, _), req) in enumerate(zip(params, required))
                   if req and i >= call.npos and p.arg not in given]
        missing += [p.arg for p, d in zip(a.kwonlyargs, a.kw_defaults) if d is None and p.arg not in given]
        if missing and note is None:
            return f"{where} omits required {', '.join(missing)}", None
        return None, note


# =========================================================================== conditions
#: What a piece of code runs under, judged per host at the sweep: ``("on", hosts, why)``
#: -- it runs on *hosts* only (a ``requires`` tag); ``("has", chain, present, why)`` --
#: it runs only where *chain* resolves (present) or only where it does not: a
#: capability check, a HOST LIMIT on the hosts its answer rules out.
_NONE = frozenset()


def _on(hosts, why):
    return ("on", frozenset(hosts), why)


def _check(chain, present, why):
    return ("has", tuple(chain), bool(present), why)


def _flip(cond):
    if cond[0] == "on":
        return ("on", ALL_HOSTS - cond[1], cond[2])
    return ("has", cond[1], not cond[2], cond[3])


@dataclass(frozen=True)
class Ctx:
    """The conditions a node runs under, and whether a ``try`` of this frame catches
    ``AttributeError`` around it (a deferred lambda or def starts a frame of its own)."""

    conds: FrozenSet[tuple] = _NONE
    caught: bool = False

    def plus(self, conds):
        return Ctx(self.conds | frozenset(conds), self.caught) if conds else self


@dataclass
class Site:
    """One toolkit read in the shared slots."""

    rel: str  # under tentacle/tentacle/slots
    where: str  # Class.method, or the module function
    line: int
    parts: Tuple[str, ...]  # "()" marks a call's result
    call: Optional[CallShape]
    #: host -> why it need not resolve there (absent = it must)
    excused: Dict[str, str] = field(default_factory=dict)

    @property
    def chain(self) -> str:
        return ".".join(self.parts).replace(".()", "()")


def _attr_parts(node):
    """``(base, [attrs])`` for an attribute chain: base is a Name, a Call, or other."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return node, list(reversed(parts))


def _shape(call: ast.Call) -> CallShape:
    return CallShape(
        len(call.args),
        tuple(k.arg for k in call.keywords if k.arg),
        any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords),
    )


def _tags_requires(node) -> bool:
    """Whether *node* tags a widget for one host: ``w.setProperty("requires", ...)``."""
    return any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "setProperty"
        and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "requires"
        for n in ast.walk(node)
    )


def _hides_first_param(fn) -> bool:
    """Whether *fn* hides the widget it is handed first: ``set_widget_visible(w, False)``,
    ``w.setVisible(False)`` or ``w.hidden_by_policy = ...`` (``Slots.hide_unless``)."""
    args = fn.args.posonlyargs + fn.args.args
    if len(args) < 2:
        return False
    widget = args[1].arg
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and n.args:
            name = getattr(n.func, "attr", "")
            first = n.args[0]
            if name == "set_widget_visible" and getattr(first, "id", "") == widget:
                return True
            if (name == "setVisible" and getattr(n.func.value, "id", "") == widget
                    and isinstance(first, ast.Constant) and first.value is False):
                return True
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Attribute) and t.attr == "hidden_by_policy"
                and getattr(t.value, "id", "") == widget for t in n.targets):
            return True
    return False


def _self_call(n) -> Optional[str]:
    """``name`` for a ``self.name(...)`` call, else ``None``."""
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and getattr(n.func.value, "id", "") == "self"):
        return n.func.attr
    return None


def _is_tk_root(node) -> bool:
    """``self.tk`` / ``slots.tk`` / a bare ``tk``: the host toolkit itself."""
    return (isinstance(node, ast.Attribute) and node.attr == "tk") or (
        isinstance(node, ast.Name) and node.id == "tk")


def _defaulted_getattr(node) -> bool:
    """``getattr(X, "f", default)``: its value is None (or the default) where X lacks f."""
    return isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getattr" \
        and len(node.args) == 3


def _exits(body) -> bool:
    return any(isinstance(s, _EXITS) for s in body)


def _literal(node):
    """A literal's value, ``dict(k=v)`` calls included; raises ``ValueError``."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "dict" and not node.args:
        return {k.arg: _literal(k.value) for k in node.keywords if k.arg}
    if isinstance(node, ast.Dict):
        return {_literal(k): _literal(v) for k, v in zip(node.keys, node.values) if k is not None}
    if isinstance(node, (ast.Tuple, ast.List)):
        return type(())(_literal(e) for e in node.elts) if isinstance(node, ast.Tuple) \
            else [_literal(e) for e in node.elts]
    return ast.literal_eval(node)


def _is_slots_class(node: ast.ClassDef) -> bool:
    """A Slots class: named ``*Slots`` or deriving ``Slots`` -- what uitk binds a ``.ui``'s
    widgets to, so the only class a widget's ``requires`` speaks for."""
    return node.name.endswith("Slots") or any(
        getattr(b, "id", getattr(b, "attr", "")) == "Slots" for b in node.bases)


def _own_nodes(node):
    """``ast.walk`` that stays out of nested class bodies."""
    todo = [node]
    while todo:
        n = todo.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if not isinstance(child, ast.ClassDef):
                todo.append(child)


@dataclass
class _Frame:
    """One function as the scanner reads it: its locals, parameters and the values an
    unrolled loop or an inlined call binds to names."""

    key: str
    cls: Optional[str]
    params: List[str]
    vararg: Optional[str]
    assigns: Dict[str, list]  # name -> [(value, tuple index or None)]
    binds: Dict[str, tuple]  # name -> the toolkit chain it holds
    env: Dict[str, tuple]  # name -> (expression, frame it reads in)
    scope: Optional[FrozenSet[str]]  # the hosts this method's widget shows on
    widget: Optional[Tuple[str, str]]  # (parameter, widget name) of a ``<w>_init``
    #: names bound to ``getattr(X, "f", default)``: None where X lacks f
    optional: set = field(default_factory=set)


@dataclass
class _Shared:
    """What every module's scan reads from the whole slots tree."""

    host_helpers: set = field(default_factory=set)  # methods calling setProperty("requires")
    hiders: set = field(default_factory=set)  # methods hiding the widget handed first
    base_methods: Dict[str, ast.AST] = field(default_factory=dict)  # slots/_slots.py
    external: set = field(default_factory=set)  # names read off anything but ``self``


class _FileScan:
    """The toolkit reads in one slots module, with the conditions each runs under."""

    _MAX_UNROLL = 64

    def __init__(self, path: Path, rel: str, ui_hosts: Dict[str, FrozenSet[str]],
                 shared: Optional[_Shared] = None, ui_parents: Optional[Dict[str, set]] = None):
        self.rel, self.shared = rel, shared or _Shared()
        #: widget -> the widgets that contain it in the ``.ui`` (hiding one hides it)
        self.ui_parents = ui_parents or {}
        self.tree = ast.parse(path.read_text(encoding="utf-8-sig"), str(path))
        self.sites: List[Tuple[Site, str, Ctx]] = []
        self.refs: Dict[str, List[Tuple[str, FrozenSet[tuple]]]] = {}
        self.methods: Dict[str, Tuple[str, ast.AST]] = {}  # key -> (class key, def)
        self.classes: Dict[str, ast.ClassDef] = {}
        self.method_names: Dict[str, str] = {}
        self.unchecked_reads: List[Tuple[str, int, str]] = []  # (where, line, source)
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                self._index_class(node, node.name)
        self.slots_classes = {k for k, c in self.classes.items() if _is_slots_class(c)}
        self.host_helpers = set(self.shared.host_helpers) | {
            fn.name for _, fn in self.methods.values() if _tags_requires(fn)}
        self.hiders = set(self.shared.hiders) | {
            fn.name for _, fn in self.methods.values() if _hides_first_param(fn)}
        self._f = _Frame("<module>", None, [], None, {}, {}, {}, None, None)
        self.class_dicts = {k: self._class_dicts(c) for k, c in self.classes.items()}
        self.class_binds: Dict[str, Dict[str, tuple]] = {}
        self.optional: Dict[str, set] = {}
        for k, c in self.classes.items():
            self.class_binds[k] = self._class_binds(c, k)
        self.table_strings: set = set()
        self.widget_hosts = self._widget_hosts(ui_hosts)
        self.strings = {n.value for n in ast.walk(self.tree)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)} - self.table_strings
        #: widget name -> the condition sets it is shown under, one per place that
        #: hides it (``hide_unless``, ``setVisible``, ``Slots.requires``)
        self.widget_conds: Dict[str, List[FrozenSet[tuple]]] = {}
        for key, (ckey, fn) in self.methods.items():
            self._walk_function(fn, ckey, key)
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_function(node, None, node.name)
            elif not isinstance(node, ast.ClassDef):
                self._f = _Frame("<module>", None, [], None, {}, {}, {}, None, None)
                self.refs.setdefault("<module>", [])
                self._visit(node, Ctx())

    def _index_class(self, node: ast.ClassDef, key: str):
        self.classes[key] = node
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                mkey = f"{key}.{item.name}"
                self.methods[mkey] = (key, item)
                self.method_names.setdefault(item.name, mkey)
            elif isinstance(item, ast.ClassDef):
                self._index_class(item, f"{key}.{item.name}")

    # ------------------------------------------------------------------ frames
    def _frame_for(self, fn, cls: Optional[str], key: str, env=None) -> _Frame:
        args = fn.args.posonlyargs + fn.args.args
        params = [a.arg for a in (args[1:] if cls else args)] + [a.arg for a in fn.args.kwonlyargs]
        vararg = fn.args.vararg.arg if fn.args.vararg else None
        if vararg:
            params.append(vararg)
        name = fn.name[: -len("_init")] if fn.name.endswith("_init") else fn.name
        slots = cls in self.slots_classes
        scope = self.widget_hosts.get(name) if slots else None
        widget = (params[0], name) if slots and fn.name.endswith("_init") and params else None
        frame = _Frame(key, cls, params, vararg, {}, {}, dict(env or {}), scope, widget)
        prev, self._f = self._f, frame
        try:
            for n in _own_nodes(fn):
                targets = (n.targets if isinstance(n, ast.Assign) else
                           [n.target] if isinstance(n, ast.AnnAssign) and n.value is not None else [])
                for t in targets:
                    if isinstance(t, ast.Name):
                        frame.assigns.setdefault(t.id, []).append((n.value, None))
                    elif isinstance(t, (ast.Tuple, ast.List)):
                        for i, e in enumerate(t.elts):
                            if isinstance(e, ast.Name):
                                frame.assigns.setdefault(e.id, []).append((n.value, i))
            for n in sorted((n for n in _own_nodes(fn) if isinstance(n, (ast.Assign, ast.AnnAssign))),
                            key=lambda n: (n.lineno, n.col_offset)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if n.value is None:
                    continue
                for t in targets:
                    if isinstance(t, ast.Name) and t.id not in frame.binds:
                        bound = self._bound_value(n.value)
                        if bound is not None:
                            frame.binds[t.id] = bound
                            if _defaulted_getattr(n.value):
                                frame.optional.add(t.id)
        finally:
            self._f = prev
        return frame

    @contextlib.contextmanager
    def _in(self, frame: _Frame):
        prev, self._f = self._f, frame
        try:
            yield
        finally:
            self._f = prev

    def _method(self, name: str):
        """``(class key, def)`` for ``self.<name>``: this class's, a same-file class's,
        else the base Slots class's (``slots/_slots.py``)."""
        own = f"{self._f.cls}.{name}"
        key = own if own in self.methods else self.method_names.get(name)
        if key is not None:
            return self.methods[key][0], self.methods[key][1]
        fn = self.shared.base_methods.get(name)
        return ("Slots", fn) if fn is not None else (None, None)

    # ------------------------------------------------------------------ tables and widgets
    def _class_dicts(self, cls: ast.ClassDef) -> Dict[str, object]:
        """The class's literal tables (``HOST_ONLY = {"b005": ...}``, ``ROWS = (...)``)."""
        out = {}
        for item in cls.body:
            value = getattr(item, "value", None)
            if not isinstance(item, (ast.Assign, ast.AnnAssign)) or value is None:
                continue
            try:
                literal = _literal(value)
            except (ValueError, TypeError, SyntaxError):
                continue
            for t in (item.targets if isinstance(item, ast.Assign) else [item.target]):
                if isinstance(t, ast.Name):
                    out[t.id] = literal
        return out

    def _widget_hosts(self, ui_hosts):
        """``{widget: hosts}`` for the Slots classes' handlers: the ``.ui`` tags, plus the
        code-built rows a class tags from a table -- a tuple literal naming one of its
        methods and a host (``("Cleanup Unknown", "b006", tip, "maya")``; ``None``: both)
        in a class that tags widgets."""
        out = dict(ui_hosts)
        for key in self.slots_classes:
            c = self.classes[key]
            if not (_tags_requires(c) or any(_self_call(n) in self.host_helpers for n in ast.walk(c))):
                continue
            for n in ast.walk(c):
                if not isinstance(n, ast.Tuple):
                    continue
                consts = [e.value for e in n.elts if isinstance(e, ast.Constant)]
                names = [v for v in consts if isinstance(v, str) and f"{key}.{v}" in self.methods]
                tags = frozenset(v for v in consts if v in ALL_HOSTS)
                if names and (tags or None in consts):
                    self.table_strings.update(names)
                    for name in names:
                        out[name] = out.get(name, frozenset()) | (tags or ALL_HOSTS)
        return out

    def _items(self, expr):
        """The items a ``for`` over *expr* takes, as ``(expression, frame)`` -- a literal
        table (``self.T``, ``.items()``, ``.values()``), a tuple or list display, or a
        name bound to one -- else ``None``."""
        if isinstance(expr, (ast.Tuple, ast.List)):
            out = []
            for e in expr.elts:
                if isinstance(e, ast.Starred):
                    inner = self._items(e.value)
                    if inner is None:
                        return None
                    out.extend(inner)
                else:
                    out.append((e, self._f))
            return out
        if isinstance(expr, ast.Name) and expr.id in self._f.env:
            value, frame = self._f.env[expr.id]
            with self._in(frame):
                return self._items(value)
        if isinstance(expr, ast.Name) and len(self._f.assigns.get(expr.id, ())) == 1:
            value, index = self._f.assigns[expr.id][0]
            if index is None and isinstance(value, (ast.Tuple, ast.List, ast.ListComp)):
                return self._items(value) if not isinstance(value, ast.ListComp) else None
        objects = None
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and not expr.args \
                and expr.func.attr in ("items", "values", "keys"):
            tables = self._objects(expr.func.value)
            if tables and all(isinstance(t, dict) for t in tables):
                objects = [x for t in tables for x in getattr(t, expr.func.attr)()]
        else:
            tables = self._objects(expr)
            if tables and len(tables) == 1 and isinstance(tables[0], (dict, list, tuple)):
                objects = list(tables[0])
        if objects is None or len(objects) > self._MAX_UNROLL:
            return None
        return [(ast.Constant(value=o), None) for o in objects]

    def _objects(self, expr) -> Optional[list]:
        """The values *expr* can take, when they are literals the code names: a constant,
        a class table, a lookup into one (any key when the key is not known), a name
        bound to those -- else ``None``."""
        if isinstance(expr, ast.Constant):
            return [expr.value]
        if isinstance(expr, ast.Name):
            if expr.id in self._f.env:
                value, frame = self._f.env[expr.id]
                if frame is None:
                    return [value.value] if isinstance(value, ast.Constant) else None
                with self._in(frame):
                    return self._objects(value)
            out = []
            for value, index in self._f.assigns.get(expr.id, ()):
                got = self._objects(value)
                if got is None:
                    return None
                if index is not None:
                    got = [g[index] for g in got if isinstance(g, (tuple, list)) and len(g) > index]
                out.extend(got)
            return out or None
        if isinstance(expr, ast.Attribute) and getattr(expr.value, "id", "") == "self":
            table = self.class_dicts.get(self._f.cls, {}).get(expr.attr)
            return [table] if table is not None else None
        if isinstance(expr, ast.Subscript):
            bases, keys = self._objects(expr.value), self._objects(expr.slice)
            return self._lookup(bases, keys)
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) \
                and expr.func.attr == "get" and expr.args:
            bases, keys = self._objects(expr.func.value), self._objects(expr.args[0])
            got = self._lookup(bases, keys)
            if got is not None and len(expr.args) > 1:
                extra = self._objects(expr.args[1])
                got = None if extra is None else got + extra
            return got
        try:
            return [_literal(expr)]
        except (ValueError, TypeError, SyntaxError):
            return None

    @staticmethod
    def _lookup(bases, keys):
        if bases is None:
            return None
        out = []
        for b in bases:
            if isinstance(b, dict):
                out.extend(b[k] for k in keys if k in b) if keys is not None else out.extend(b.values())
            elif isinstance(b, (list, tuple)):
                out.extend(b[k] for k in keys if isinstance(k, int) and -len(b) <= k < len(b)) \
                    if keys is not None else out.extend(b)
            else:
                return None
        return out

    def _names(self, expr) -> Optional[set]:
        objects = self._objects(expr)
        if objects is None:
            return None
        names = {o for o in objects if isinstance(o, str)}
        return names or None

    def _widget_names(self, expr) -> set:
        """The objectNames a widget expression can be: ``menu.add(...,
        setObjectName=...)``, ``getattr(self.ui, name)``, ``self.ui.b005``, a ``<w>_init``'s
        widget, a name bound to those, a display of them."""
        if isinstance(expr, ast.Call):
            for kw in expr.keywords:
                if kw.arg == "setObjectName":
                    return self._names(kw.value) or set()
            if getattr(expr.func, "id", "") == "getattr" and len(expr.args) == 2:
                return self._names(expr.args[1]) or set()
            return set()
        if isinstance(expr, ast.Attribute):
            return {expr.attr}
        if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
            return set().union(*(self._widget_names(e) for e in expr.elts)) if expr.elts else set()
        if isinstance(expr, ast.Starred):
            return self._widget_names(expr.value)
        if isinstance(expr, ast.Name):
            if self._f.widget and expr.id == self._f.widget[0]:
                return {self._f.widget[1]}
            if expr.id in self._f.env:
                value, frame = self._f.env[expr.id]
                if frame is None:
                    return {value.value} if isinstance(value, ast.Constant) and isinstance(value.value, str) else set()
                with self._in(frame):
                    return self._widget_names(value)
            out = set()
            for value, index in self._f.assigns.get(expr.id, ()):
                if index is None:
                    out |= self._widget_names(value)
            return out
        return set()

    # ------------------------------------------------------------------ binds
    def _tk_parts(self, node) -> Optional[Tuple[str, ...]]:
        """The toolkit chain *node* reads (``self.tk.A.b`` -> ``("A", "b")``)."""
        base, attrs = _attr_parts(node)
        if isinstance(base, ast.Call):
            inner = self._call_parts(base)
            return inner + tuple(attrs) if inner is not None and attrs else None
        if not isinstance(base, ast.Name):
            return None
        names = [base.id] + attrs
        if "tk" in names[:-1]:
            return tuple(names[names.index("tk") + 1:])
        if base.id == "self" and attrs and self._f.cls is not None:
            bound = self.class_binds.get(self._f.cls, {}).get(attrs[0])
            if bound is not None:
                return bound + tuple(attrs[1:])
        if base.id in self._f.binds:
            return self._f.binds[base.id] + tuple(attrs)
        return None

    def _call_parts(self, call: ast.Call) -> Optional[Tuple[str, ...]]:
        """The chain a call's result is: ``tk.A.f(...)`` -> ``("A", "f", "()")``;
        ``getattr(tk.A, "f"[, d])`` -> ``("A", "f")``."""
        if getattr(call.func, "id", "") == "getattr" and len(call.args) in (2, 3):
            prefix = self._chain_of(call.args[0])
            names = self._names(call.args[1])
            if prefix is not None and names and len(names) == 1:
                return prefix + (next(iter(names)),)
            return None
        inner = self._chain_of(call.func)
        return inner + ("()",) if inner else None

    def _chain_of(self, node) -> Optional[Tuple[str, ...]]:
        if _is_tk_root(node):
            return ()
        if isinstance(node, ast.Attribute):
            return self._tk_parts(node)
        if isinstance(node, ast.Name):
            return self._f.binds.get(node.id)
        return None

    def _bound_value(self, value) -> Optional[Tuple[str, ...]]:
        """The chain a name bound to *value* holds: the toolkit itself, a chain of it, an
        engine or any other call's result (``tk.Engine(...)``, ``tk.A.create(...)``)."""
        if isinstance(value, ast.Call):
            return self._call_parts(value)
        return self._chain_of(value)

    def _class_binds(self, cls: ast.ClassDef, key: str) -> Dict[str, Tuple[str, ...]]:
        """``self.x = <toolkit chain or call>`` anywhere in the class (an annotated one
        too), and properties (``cached_property`` too) returning one, a lazy one over
        ``self._engine`` included: ``x`` -> the chain it holds."""
        binds: Dict[str, Tuple[str, ...]] = {}
        self.class_binds[key] = binds
        optional = self.optional.setdefault(key, set())
        for _ in range(2):  # the second pass sees ``return self._engine``
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                with self._in(_Frame(f"{key}.{fn.name}", key, [], None, {}, {}, {}, None, None)):
                    for n in _own_nodes(fn):
                        targets = (n.targets if isinstance(n, ast.Assign) else
                                   [n.target] if isinstance(n, ast.AnnAssign) else [])
                        value = getattr(n, "value", None)
                        for t in targets:
                            if (value is not None and isinstance(t, ast.Attribute)
                                    and getattr(t.value, "id", "") == "self"):
                                bound = self._bound_value(value)
                                if bound is not None and t.attr not in binds:
                                    binds[t.attr] = bound
                                    if _defaulted_getattr(value):
                                        optional.add(t.attr)
                    if any("property" in d for d in _deco_names(fn)):
                        for r in _own_nodes(fn):
                            if isinstance(r, ast.Return) and r.value is not None:
                                bound = self._bound_value(r.value)
                                if bound is not None:
                                    binds.setdefault(fn.name, bound)
        return binds

    # ------------------------------------------------------------------ conditions
    def _where(self) -> str:
        return f"{self.rel} {self._f.key}"

    def _existence(self, expr) -> Optional[Tuple[str, ...]]:
        """The chain whose presence *expr*'s ``None``-ness or truth answers: a
        ``getattr(X, name, default)``, or a name bound to one."""
        if isinstance(expr, ast.Call) and getattr(expr.func, "id", "") == "getattr" \
                and len(expr.args) == 3:
            prefix = self._chain_of(expr.args[0])
            names = self._names(expr.args[1])
            if prefix is not None and names and len(names) == 1:
                return prefix + (next(iter(names)),)
            return None
        if (isinstance(expr, ast.Attribute) and getattr(expr.value, "id", "") == "self"
                and expr.attr in self.optional.get(self._f.cls, ())):
            return self.class_binds[self._f.cls][expr.attr]
        if isinstance(expr, ast.Name):
            if expr.id in self._f.env:
                value, frame = self._f.env[expr.id]
                if frame is not None:
                    with self._in(frame):
                        return self._existence(value)
                return None
            if expr.id in self._f.optional:
                return self._f.binds[expr.id]
            assigned = self._f.assigns.get(expr.id, ())
            if len(assigned) == 1 and assigned[0][1] is None:
                return self._existence(assigned[0][0])
        return None

    def _cond(self, expr, depth=0) -> Tuple[FrozenSet[tuple], FrozenSet[tuple]]:
        """``(true, false)``: the conditions known to hold where *expr* is truthy, and
        where it is falsy. Polarity is read: ``not``, ``and`` / ``or``, ``is (not)
        None``, a helper's returned check."""
        if depth > 8 or expr is None:
            return _NONE, _NONE
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            t, f = self._cond(expr.operand, depth + 1)
            return f, t
        if isinstance(expr, ast.BoolOp):
            parts = [self._cond(v, depth + 1) for v in expr.values]
            if isinstance(expr.op, ast.And):
                return frozenset().union(*(t for t, _ in parts)), (parts[0][1] if len(parts) == 1 else _NONE)
            return (parts[0][0] if len(parts) == 1 else _NONE), frozenset().union(*(f for _, f in parts))
        if isinstance(expr, ast.Compare) and len(expr.ops) == 1:
            op, left, right = expr.ops[0], expr.left, expr.comparators[0]
            if isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
                other = left if isinstance(right, ast.Constant) and right.value is None else \
                    right if isinstance(left, ast.Constant) and left.value is None else None
                if other is not None:
                    chain = self._existence(other)
                    if chain is not None:
                        present = _check(chain, True, self._where())
                        pair = (frozenset({present}), frozenset({_flip(present)}))
                        return pair if isinstance(op, (ast.IsNot, ast.NotEq)) else pair[::-1]
                policy = self._policy_test(left, right)
                if policy is not None and self._f.scope is not None and isinstance(op, (ast.Eq, ast.NotEq)):
                    shown = _on(self._f.scope, f"{self._f.key} returns where its widget is hidden")
                    pair = (frozenset({_flip(shown)}), frozenset({shown}))
                    return pair if isinstance(op, ast.Eq) else pair[::-1]
            return _NONE, _NONE
        if isinstance(expr, ast.Call):
            return self._cond_call(expr, depth)
        if isinstance(expr, ast.Name):
            if expr.id in self._f.env:
                value, frame = self._f.env[expr.id]
                if frame is None:
                    return _NONE, _NONE
                with self._in(frame):
                    return self._cond(value, depth + 1)
            assigned = self._f.assigns.get(expr.id, ())
            if len(assigned) == 1 and assigned[0][1] is None:
                return self._cond(assigned[0][0], depth + 1)
        chain = self._existence(expr)
        if chain is not None:
            return frozenset({_check(chain, True, self._where())}), _NONE
        return _NONE, _NONE

    @staticmethod
    def _policy_test(left, right):
        """``widget.hidden_by_policy == "requires"`` (or its ``getattr`` form)."""
        for a, b in ((left, right), (right, left)):
            if isinstance(b, ast.Constant) and b.value == "requires":
                if isinstance(a, ast.Attribute) and a.attr == "hidden_by_policy":
                    return a
                if (isinstance(a, ast.Call) and getattr(a.func, "id", "") == "getattr"
                        and len(a.args) >= 2 and isinstance(a.args[1], ast.Constant)
                        and a.args[1].value == "hidden_by_policy"):
                    return a
        return None

    def _cond_call(self, call: ast.Call, depth: int):
        name = getattr(call.func, "id", None)
        if name == "hasattr" and len(call.args) == 2:
            prefix, names = self._chain_of(call.args[0]), self._names(call.args[1])
            if prefix is not None and names and len(names) == 1:
                present = _check(prefix + (next(iter(names)),), True, self._where())
                return frozenset({present}), frozenset({_flip(present)})
            return _NONE, _NONE
        if name == "getattr" and len(call.args) == 3:
            chain = self._existence(call)
            return (frozenset({_check(chain, True, self._where())}), _NONE) if chain else (_NONE, _NONE)
        if name in ("bool", "callable") and len(call.args) == 1:
            return self._cond(call.args[0], depth + 1)
        if name in ("all", "any") and len(call.args) == 1:
            return self._cond_all(call.args[0], name == "all", depth)
        helper = _self_call(call)
        if helper is None:
            return _NONE, _NONE
        if helper in self.host_helpers:
            tags = self._host_tags(call)
            if tags is None:
                return _NONE, _NONE
            shown = _on(tags, f"code-built widget tagged {'/'.join(sorted(tags))} ({self._where()})")
            return frozenset({shown}), frozenset({_flip(shown)})
        return self._cond_inline(helper, call, depth)

    def _host_tags(self, call: ast.Call) -> Optional[FrozenSet[str]]:
        """The host tags a ``self.requires(widget, host)`` call names, ``ALL`` for none."""
        for arg in call.args[1:]:
            objects = self._objects(arg)
            if objects is None:
                continue
            tags = set()
            for o in objects:
                if o is None or (isinstance(o, str) and not o.strip()):
                    return ALL_HOSTS
                if isinstance(o, str):
                    tags |= {t for t in re.split(r"[|,\s]+", o) if t}
            return frozenset(tags) & ALL_HOSTS
        return None

    def _cond_all(self, arg, conjunction: bool, depth: int):
        if isinstance(arg, ast.Name) and len(self._f.assigns.get(arg.id, ())) == 1:
            arg = self._f.assigns[arg.id][0][0]
        if not isinstance(arg, (ast.GeneratorExp, ast.ListComp)) or len(arg.generators) != 1:
            return _NONE, _NONE
        gen = arg.generators[0]
        items = self._items(gen.iter)
        if items is None or not isinstance(gen.target, ast.Name):
            t, f = self._cond(arg.elt, depth + 1)
            return (t, _NONE) if conjunction else (_NONE, f)
        parts = []
        for value in items:
            frame = _Frame(self._f.key, self._f.cls, self._f.params, self._f.vararg,
                           self._f.assigns, self._f.binds, {**self._f.env, gen.target.id: value},
                           self._f.scope, self._f.widget, self._f.optional)
            with self._in(frame):
                parts.append(self._cond(arg.elt, depth + 1))
        if conjunction:
            return frozenset().union(*(t for t, _ in parts)), (parts[0][1] if len(parts) == 1 else _NONE)
        return (parts[0][0] if len(parts) == 1 else _NONE), frozenset().union(*(f for _, f in parts))

    def _cond_inline(self, helper: str, call: ast.Call, depth: int):
        """A helper's answer at this call: its returned check, read with the call's
        arguments for its parameters (``self._has("op")``, ``self._unsupported("b005")``,
        ``Slots.hide_unless(widget, available)``)."""
        cls, fn = self._method(helper)
        if fn is None or depth > 6:
            return _NONE, _NONE
        frame = self._frame_for(fn, cls, f"{cls}.{fn.name}")
        names = [a.arg for a in (fn.args.posonlyargs + fn.args.args)[1:]]
        for i, arg in enumerate(call.args):
            if isinstance(arg, ast.Starred):
                if fn.args.vararg is not None and isinstance(arg.value, ast.Name) and i >= len(names):
                    frame.env[fn.args.vararg.arg] = (arg.value, self._f)
                break
            if i < len(names):
                frame.env[names[i]] = (arg, self._f)
        if fn.args.vararg is not None and fn.args.vararg.arg not in frame.env:
            frame.env[fn.args.vararg.arg] = (
                ast.Tuple(elts=[a for a in call.args[len(names):]], ctx=ast.Load()), self._f)
        for kw in call.keywords:
            if kw.arg:
                frame.env[kw.arg] = (kw.value, self._f)
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        with self._in(frame):
            if len(body) == 1 and isinstance(body[0], ast.Return):
                return self._cond(body[0].value, depth + 1)
            first = next((s for s in body if isinstance(s, ast.If)), None)
            last = body[-1] if body else None
            if (first is not None and first.body and isinstance(first.body[-1], ast.Return)
                    and isinstance(getattr(first.body[-1], "value", None), ast.Constant)
                    and isinstance(last, ast.Return) and isinstance(last.value, ast.Constant)
                    and isinstance(first.body[-1].value.value, bool)
                    and isinstance(last.value.value, bool)
                    and first.body[-1].value.value != last.value.value
                    and not any(isinstance(s, ast.Return) for s in body[body.index(first) + 1:-1])):
                t, f = self._cond(first.test, depth + 1)
                return (t, f) if first.body[-1].value.value else (f, t)
        return _NONE, _NONE

    # ------------------------------------------------------------------ walk
    def _walk_function(self, fn, cls: Optional[str], key: str):
        self._f = self._frame_for(fn, cls, key)
        self.refs.setdefault(key, [])
        for d in fn.decorator_list:
            self._visit(d, Ctx())
        self._visit_body(fn.body, Ctx())

    def _visit_body(self, stmts, ctx: Ctx):
        for stmt in stmts:
            self._visit(stmt, ctx)
            if isinstance(stmt, ast.If):
                t, f = self._cond(stmt.test)
                body_exits, else_exits = _exits(stmt.body), bool(stmt.orelse) and _exits(stmt.orelse)
                if body_exits and not else_exits:
                    ctx = ctx.plus(f)
                elif else_exits and not body_exits:
                    ctx = ctx.plus(t)
            elif isinstance(stmt, ast.Assert):
                ctx = ctx.plus(self._cond(stmt.test)[0])

    def _visit(self, node, ctx: Ctx, call: Optional[ast.Call] = None):
        if isinstance(node, (ast.If, ast.While)):
            t, f = self._cond(node.test)
            self._visit(node.test, ctx)
            self._visit_body(node.body, ctx.plus(t))
            self._visit_body(node.orelse, ctx.plus(f))
            return
        if isinstance(node, ast.IfExp):
            t, f = self._cond(node.test)
            self._visit(node.test, ctx)
            self._visit(node.body, ctx.plus(t))
            self._visit(node.orelse, ctx.plus(f))
            return
        if isinstance(node, ast.BoolOp):
            known = set()
            for value in node.values:
                self._visit(value, ctx.plus(known))
                t, f = self._cond(value)
                known |= t if isinstance(node.op, ast.And) else f
            return
        if isinstance(node, ast.Try):
            catches = any(
                h.type is not None and any(
                    getattr(t, "id", "") == "AttributeError"
                    for t in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]))
                for h in node.handlers)
            self._visit_body(node.body, Ctx(ctx.conds, True) if catches else ctx)
            for h in node.handlers:
                self._visit_body(h.body, ctx)
            self._visit_body(node.orelse, ctx)
            self._visit_body(node.finalbody, ctx)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            deferred = Ctx(ctx.conds, False)  # runs later: no enclosing try catches it
            for d in getattr(node, "decorator_list", ()):
                self._visit(d, ctx)
            for d in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                self._visit(d, ctx)
            if isinstance(node, ast.Lambda):
                self._visit(node.body, deferred)
            else:
                self._visit_body(node.body, deferred)
            return
        if isinstance(node, ast.ClassDef):
            return  # a nested class is scanned as a class of its own
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._visit(node.iter, ctx)
            items = self._items(node.iter)
            if items is None:
                self._visit_body(node.body, ctx)
            else:
                for value in items:
                    env = dict(self._f.env)
                    self._bind_target(node.target, value, env)
                    saved, self._f.env = self._f.env, env
                    try:
                        self._visit_body(node.body, ctx)
                    finally:
                        self._f.env = saved
            self._visit_body(node.orelse, ctx)
            return
        if isinstance(node, ast.Call):
            self._visit_call(node, ctx, call)
            return
        if isinstance(node, ast.Attribute):
            self._visit_attribute(node, ctx, call)
            return
        for _, value in ast.iter_fields(node):
            if isinstance(value, list):
                if value and isinstance(value[0], ast.stmt):
                    self._visit_body(value, ctx)
                else:
                    for item in value:
                        if isinstance(item, ast.AST):
                            self._visit(item, ctx)
            elif isinstance(value, ast.AST):
                self._visit(value, ctx)

    def _bind_target(self, target, value, env):
        """Bind a ``for`` target to one item: names, or a tuple unpacking a literal."""
        expr, frame = value
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            if frame is None and isinstance(expr, ast.Constant) and isinstance(expr.value, (tuple, list)):
                for t, v in zip(target.elts, expr.value):
                    self._bind_target(t, (ast.Constant(value=v), None), env)
            elif isinstance(expr, (ast.Tuple, ast.List)):
                for t, v in zip(target.elts, expr.elts):
                    self._bind_target(t, (v, frame), env)

    def _visit_call(self, node: ast.Call, ctx: Ctx, outer: Optional[ast.Call]):
        func_name = getattr(node.func, "id", None)
        if func_name == "getattr" and len(node.args) in (2, 3):
            prefix = self._chain_of(node.args[0])
            # A 2-argument getattr reads the name; a 3-argument one only when its
            # result is called unchecked (``getattr(x, "f", None)()``).
            if prefix is not None and (len(node.args) == 2 or outer is not None):
                names = self._names(node.args[1])
                if names:
                    for name in sorted(names):
                        self._site(prefix + (name,), node, ctx, outer)
                else:
                    self.unchecked_reads.append(
                        (self._f.key, node.lineno, ast.unparse(node)[:80]))
        elif isinstance(node.func, ast.Name) and node.func.id in self._f.binds and \
                self._f.binds[node.func.id]:
            self._site(self._f.binds[node.func.id], node, ctx, node)
        helper = _self_call(node)
        if helper in self.hiders and len(node.args) >= 2:
            self._hide(node.args[0], self._cond(node)[0], ctx)
        elif helper in self.host_helpers and node.args:
            tags = self._host_tags(node)
            if tags is not None:
                why = f"code-built widget tagged {'/'.join(sorted(tags)) or 'no host'} ({self._where()})"
                self._hide(node.args[0], frozenset() if tags == ALL_HOSTS else {_on(tags, why)}, ctx)
        elif (isinstance(node.func, ast.Attribute) and node.func.attr == "setVisible"
              and len(node.args) == 1):
            self._hide(node.func.value, self._cond(node.args[0])[0], ctx)
        self._visit(node.func, ctx, call=node)
        for a in node.args:
            self._visit(a, ctx)
        for k in node.keywords:
            self._visit(k.value, ctx)

    def _hide(self, widget, conds, ctx: Ctx):
        """Record that *widget* shows only where *conds* hold. A hide under a condition
        of its own also leaves the widget shown where that condition fails."""
        for name in self._widget_names(widget):
            alternatives = self.widget_conds.setdefault(name, [])
            alternatives.append(frozenset(conds))
            if ctx.conds:
                alternatives.append(_NONE)

    def _visit_attribute(self, node: ast.Attribute, ctx: Ctx, call: Optional[ast.Call]):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            # Writing an attribute needs only its owner: ``tk.X.flag = 1``.
            owner = self._tk_parts(node.value)
            if owner:
                self._site(owner, node, ctx, None)
        else:
            parts = self._tk_parts(node)
            bare = (call is None and getattr(node.value, "id", "") == "self"
                    and node.attr in self.optional.get(self._f.cls, ()))
            if parts and not bare:
                self._site(parts, node, ctx, call)
        base, attrs = _attr_parts(node)
        if isinstance(base, ast.Name) and base.id == "self" and attrs:
            own = f"{self._f.cls}.{attrs[0]}"
            callee = own if own in self.methods else self.method_names.get(attrs[0])
            if callee:
                self.refs[self._f.key].append((callee, ctx.conds))
        elif not isinstance(base, ast.Name):
            self._visit(base, ctx)

    def _site(self, parts, node, ctx, call):
        if not parts:
            return
        site = Site(self.rel, self._f.key, getattr(node, "lineno", 0), tuple(parts),
                    _shape(call) if call is not None else None)
        self.sites.append((site, self._f.key, ctx))

    # ------------------------------------------------------------------ entries
    def entries(self) -> Dict[str, List[FrozenSet[tuple]]]:
        """Per method, the condition sets it is entered under (one per way in; an empty
        list: only through the references of its class). A Slots class's handler
        shows where its widget does; a private method is reached through its
        references unless something outside the class names it."""
        referenced = {callee for refs in self.refs.values() for callee, _ in refs}
        out = {}
        for key in self.refs:
            cls = self.methods[key][0] if key in self.methods else None
            name = key.rpartition(".")[2]
            chain = [name, *sorted(self.ui_parents.get(name, ()))]
            if cls in self.slots_classes and any(w in self.widget_hosts or w in self.widget_conds
                                                  for w in chain):
                alternatives = [_NONE]
                for widget in chain:  # shown where it and every group holding it show
                    hosts = self.widget_hosts.get(widget)
                    base = _NONE if hosts is None or hosts == ALL_HOSTS else frozenset(
                        {_on(hosts, f"widget {widget} requires {'/'.join(sorted(hosts)) or 'no host'}")})
                    own = [base | alt for alt in self.widget_conds.get(widget) or [_NONE]]
                    alternatives = [a | b for a in alternatives for b in own]
                out[key] = alternatives
            elif (cls is not None and name.startswith("_") and not name.startswith("__")
                  and key in referenced and name not in self.shared.external
                  and name not in self.strings):
                out[key] = []
            else:
                out[key] = [_NONE]
        return out


# =========================================================================== the sweep
class GateError(Exception):
    """The gate cannot read a library statically: it exits 2 rather than guess."""


@dataclass
class Gap:
    chain: str
    host: str
    problem: str
    sites: List[Site]


@dataclass
class SweepResult:
    files: Dict[str, List[Site]]
    sites: List[Site]
    gaps: List[Gap]
    unverified: Dict[Tuple[str, str], str]  # (chain, host) -> why
    lint: List[str]
    tools: Dict[str, str]  # tool stem -> "both" / "maya" / "standalone"
    #: (chain, host lacking it, what hides it there) -> its sites: the one-host operations
    one_host: Dict[Tuple[str, str, str], List[Site]] = field(default_factory=dict)
    #: (chain, "starred" | "forwarded") -> sites whose signature check was skipped
    unchecked: Dict[Tuple[str, str], List[Site]] = field(default_factory=dict)
    #: (rel, where, line, source): a toolkit read under a name computed at runtime
    computed: List[Tuple[str, str, int, str]] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.gaps or self.lint)


def _tools_table(slots_dir: Path):
    """``(HOSTS, STANDALONE)`` from ``slots/tools/__init__.py``, read as literals."""
    hosts, standalone = {}, ()
    init = slots_dir / "tools" / "__init__.py"
    if init.is_file():
        for node in ast.parse(init.read_text(encoding="utf-8-sig")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = getattr(node.targets[0], "id", "")
                if name == "HOSTS":
                    hosts = ast.literal_eval(node.value)
                elif name == "STANDALONE":
                    standalone = ast.literal_eval(node.value)
    return {k: frozenset(v) for k, v in hosts.items()}, frozenset(standalone)


def _requires_of(ui_files) -> Dict[str, FrozenSet[str]]:
    """``{widget: hosts it shows on}`` across *ui_files* (any untagged copy: all). A
    blank ``requires`` shows everywhere, as uitk's policy reads it."""
    out: Dict[str, FrozenSet[str]] = {}
    for f in ui_files:
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        for w in root.iter("widget"):
            name = w.get("name")
            if not name:
                continue
            tags = ALL_HOSTS
            for p in w.findall("property"):
                if p.get("name") == "requires":
                    named = {t for t in re.split(r"[|,\s]+", p.findtext("string") or "") if t}
                    if named:
                        tags = frozenset(named) & ALL_HOSTS
            out[name] = out.get(name, frozenset()) | tags
    return out


def _ui_parents(ui_files) -> Dict[str, set]:
    """``{widget: the named widgets that contain it}`` -- in every file that has it, so
    a copy outside a group is never taken for hidden with the group."""
    out: Dict[str, set] = {}
    for f in ui_files:
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        found: Dict[str, set] = {}

        def walk(node, above):
            for child in node:
                if child.tag == "widget" and child.get("name"):
                    found.setdefault(child.get("name"), set()).update(above)
                    walk(child, above | {child.get("name")})
                else:
                    walk(child, above)

        top = root.find("widget")
        if top is not None:
            walk(top, set())  # the window itself contains everything: not a group
        for name, above in found.items():
            out[name] = out[name] & above if name in out else set(above)
    return out


def _ui_lint(ui_dir: Path) -> List[str]:
    lint = []
    for f in sorted(ui_dir.rglob("*.ui")):
        rel = f.relative_to(ui_dir).as_posix()
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as e:
            lint.append(f"{rel}: XML parse error: {e}")
            continue
        customs = {c.text for c in root.findall(".//customwidget/class")}
        for w in root.iter("widget"):
            cls = w.get("class")
            if cls and not cls.startswith("Q") and cls not in customs:
                lint.append(f"{rel}: promoted class '{cls}' (widget '{w.get('name')}') is missing "
                            "from <customwidgets>; it would load as a plain QWidget")
    return lint


def _slot_files(slots_dir: Path):
    """``(rel, path, tool stem or None)`` for every shared slots module."""
    for path in sorted(slots_dir.rglob("*.py")):
        rel = path.relative_to(slots_dir).as_posix()
        top = rel.split("/")[0]
        if "__pycache__" in rel or top in HOST_PACKAGES:  # slots/<host>/: one host's own
            continue
        tool = None
        if top == "tools" and rel != "tools/__init__.py":
            seg = rel.split("/")[1]
            tool = seg[1:] if seg.startswith("_") and "/" in rel[6:] else Path(seg).stem
        yield rel, path, tool


def _paired_ui(ui_dir: Path, rel: str) -> List[Path]:
    stem = Path(rel).stem
    if "/" not in rel:
        folder = ui_dir
    elif rel.count("/") == 1 and rel.startswith("tools/"):
        folder = ui_dir / "tools"
    else:
        return []
    return [f for f in folder.glob("*.ui") if f.stem == stem or f.stem.startswith(stem + "#")]


def _shared(slots_dir: Path) -> _Shared:
    """The tree-wide facts each module's scan needs: the widget-tagging and hiding
    helpers, the base Slots class's methods, the names read off other objects."""
    shared = _Shared()
    for rel, path, _ in _slot_files(slots_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue  # reported by its scan
        for c in ast.walk(tree):
            if not isinstance(c, ast.ClassDef):
                continue
            for fn in c.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _tags_requires(fn):
                        shared.host_helpers.add(fn.name)
                    if _hides_first_param(fn):
                        shared.hiders.add(fn.name)
                    if rel == "_slots.py":
                        shared.base_methods.setdefault(fn.name, fn)
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and not (isinstance(n.value, ast.Name) and n.value.id == "self"):
                shared.external.add(n.attr)
    return shared


def _excuse(cond, host) -> str:
    if cond[0] == "on":
        return f"hidden by `requires` ({cond[2]})"
    chain = ".".join(cond[1]).replace(".()", "()")
    if cond[2]:
        return f"runs only where `{chain}` resolves, not on {host} (checked in {cond[3]})"
    return f"runs only where `{chain}` is missing (checked in {cond[3]})"


def sweep(root=None) -> SweepResult:
    """Run the gate over the workspace at *root* (default: this script's workspace)."""
    root = Path(root or ROOT)
    tentacle = root / "tentacle" / "tentacle"
    slots_dir, ui_dir = tentacle / "slots", tentacle / "ui"
    hosts_table, standalone = _tools_table(slots_dir)
    ws = Workspace(root)
    for pkg in HOST_PACKAGES.values():  # an unreadable include map fails before any verdict
        if ws.package(pkg) is not None:
            ws.package(pkg).root_lookup("__name__")
    resolved: Dict[Tuple[Tuple[str, ...], str], object] = {}

    def resolve(parts, host):
        if (parts, host) not in resolved:
            value = ws.module(HOST_PACKAGES[host])
            value = ModuleV(value) if value else Missing(f"{HOST_PACKAGES[host]} not in the workspace")
            for part in parts:
                value = ws.call_result(value) if part == "()" else ws.getattr(value, part)
            resolved[(parts, host)] = value
        return resolved[(parts, host)]

    def holds(cond, host) -> bool:
        if cond[0] == "on":
            return host in cond[1]
        return (not isinstance(resolve(cond[1], host), Missing)) == cond[2]

    shared = _shared(slots_dir)
    files: Dict[str, List[Site]] = {}
    tools: Dict[str, str] = {}
    computed: List[Tuple[str, str, int, str]] = []
    for rel, path, tool in _slot_files(slots_dir):
        base = ALL_HOSTS
        why = {}
        if tool in standalone:
            base, why = frozenset(), {h: "standalone panel (slots.tools.STANDALONE)" for h in ALL_HOSTS}
        elif tool in hosts_table:
            base = hosts_table[tool] & ALL_HOSTS
            why = {h: "tool serves " + "/".join(sorted(base)) + " (slots.tools.HOSTS)"
                   for h in ALL_HOSTS - base}
        if tool and "/" not in rel[len("tools/"):]:
            tools[tool] = ("standalone" if tool in standalone else
                           "/".join(sorted(base)) if base != ALL_HOSTS else "both")
        try:
            ui_files = _paired_ui(ui_dir, rel)
            scan = _FileScan(path, rel, _requires_of(ui_files), shared, _ui_parents(ui_files))
        except SyntaxError as error:
            sys.exit(f"{path}: {error.msg} (line {error.lineno}) -- fix it before the sweep can run")
        reach, reasons = _reach(scan, base, holds)
        computed += [(rel, w, line, src) for w, line, src in scan.unchecked_reads]
        out, seen = [], set()
        for site, key, ctx in scan.sites:
            ident = (site.parts, site.line, key, site.call)
            if ident in seen:  # an unrolled loop reads it once per item
                continue
            seen.add(ident)
            site.excused.update(why)
            for h in base:
                if not reach.get(key, {}).get(h, True):
                    site.excused[h] = reasons(key, h)
                    continue
                failing = next((c for c in sorted(ctx.conds, key=repr) if not holds(c, h)), None)
                if failing is not None:
                    site.excused[h] = _excuse(failing, h)
                elif ctx.caught:
                    site.excused[h] = "caught (try ... except AttributeError)"
            out.append(site)
        files[rel] = out
    sites = [s for v in files.values() for s in v]

    gaps: Dict[Tuple[str, str, str], Gap] = {}
    unverified: Dict[Tuple[str, str], str] = {}
    one_host: Dict[Tuple[str, str, str], List[Site]] = {}
    unchecked: Dict[Tuple[str, str], List[Site]] = {}
    for site in sites:
        for host, why in site.excused.items():
            if "slots.tools." not in why and isinstance(resolve(site.parts, host), Missing):
                one_host.setdefault((site.chain, host, why), []).append(site)
        for host in sorted(ALL_HOSTS - set(site.excused)):
            value = resolve(site.parts, host)
            if isinstance(value, Missing):
                problem = f"does not resolve: {value.why}"
            elif isinstance(value, Opaque):
                if not value.seen:
                    unverified.setdefault((site.chain, host), value.why)
                continue
            else:
                problem, note = ws.arity(value, site.call)
                if note:
                    bucket = unchecked.setdefault((site.chain, note), [])
                    if site not in bucket:
                        bucket.append(site)
                if problem is None:
                    continue
            gap = gaps.setdefault((site.chain, host, problem), Gap(site.chain, host, problem, []))
            gap.sites.append(site)
    return SweepResult(files, sites, sorted(gaps.values(), key=lambda g: (g.chain, g.host, g.problem)),
                       unverified, _ui_lint(ui_dir), tools, dict(sorted(one_host.items())),
                       dict(sorted(unchecked.items())), computed)


def _reach(scan: _FileScan, hosts: FrozenSet[str], holds):
    """``({method: {host: runs there}}, reasons(method, host))``: a method runs on a host
    when one way in holds there -- an entry, or a reference from a method that runs
    there under conditions that hold."""
    entries = scan.entries()
    reach = {k: {h: False for h in hosts} for k in entries}
    for key, alternatives in entries.items():
        for h in hosts:
            reach[key][h] = any(all(holds(c, h) for c in alt) for alt in alternatives)
    incoming: Dict[str, List[Tuple[str, FrozenSet[tuple]]]] = {}
    for caller, refs in scan.refs.items():
        for callee, conds in refs:
            incoming.setdefault(callee, []).append((caller, conds))
    changed = True
    while changed:
        changed = False
        for caller, refs in scan.refs.items():
            for callee, conds in refs:
                for h in hosts:
                    if (reach.get(caller, {}).get(h) and callee in reach and not reach[callee][h]
                            and all(holds(c, h) for c in conds)):
                        reach[callee][h] = changed = True

    def reasons(key, host, depth=0):
        for alt in entries.get(key, ()):
            failing = next((c for c in sorted(alt, key=repr) if not holds(c, host)), None)
            if failing is not None:
                return _excuse(failing, host)
        for caller, conds in incoming.get(key, ()):
            failing = next((c for c in sorted(conds, key=repr) if not holds(c, host)), None)
            if failing is not None:
                return _excuse(failing, host)
            if depth < 4 and not reach.get(caller, {}).get(host, True):
                return reasons(caller, host, depth + 1)
        return "reached only from code that does not run here"

    return reach, reasons


# =========================================================================== reports
def _where(sites) -> str:
    seen = []
    for s in sites:
        label = f"`{s.rel}` {s.where}"
        if label not in seen:
            seen.append(label)
    return "; ".join(seen)


def report(result: SweepResult) -> str:
    L: List[str] = []
    w = L.append
    chains = {s.chain for s in result.sites}
    n_unverified = len(result.unverified) + len(result.computed)
    w("# tentacle -- Maya/Blender toolkit parity")
    w("")
    w("> **Auto-generated by `m3trik/scripts/compare_panel_surface.py --all --write`.** Do not edit "
      "by hand. One Slots class per category and per tool serves both hosts through `self.tk`, so "
      "parity is: every toolkit chain a shared Slots class reads resolves on mayatk AND blendertk "
      "(same name, a signature that takes the call), unless the host that lacks it never runs it -- "
      "its widget's `requires` tag, `slots.tools.HOSTS` / `STANDALONE`, or a capability check "
      "(`hasattr` / `getattr`, a hide over one) whose answer rules that host out. A **gap** fails "
      "the gate (exit 1): add the operation to that host's library, or hide the call there. "
      "Resolution is static, from both libraries' sources (the script docstring has the rules).")
    w("")
    w(f"**{len(result.files)} slots modules; {len(chains)} distinct toolkit chains at "
      f"{len(result.sites)} call sites. {len(result.gaps)} gap(s), {len(result.lint)} `.ui` lint(s): "
      f"the gate {'FAILS' if result.failed else 'PASSES'}.** {n_unverified} unverified read(s) and "
      f"{len(result.unchecked)} unchecked signature(s), listed below, pass: the static model "
      "cannot prove them absent.")
    w("")
    if result.gaps:
        w("## Gaps")
        w("")
        w("| chain | host | problem | called from |")
        w("|:--|:--|:--|:--|")
        for g in result.gaps:
            w(f"| `{g.chain}` | {g.host} | {g.problem} | {_where(g.sites)} |")
        w("")
    if result.lint:
        w("## `.ui` lint")
        w("")
        for line in result.lint:
            w(f"- {line}")
        w("")
    w("## Per module")
    w("")
    w("| module | hosts | chains | sites | not run on maya | not run on blender | gaps |")
    w("|:--|:--|--:|--:|--:|--:|--:|")
    gap_sites = {id(s) for g in result.gaps for s in g.sites}
    for rel, sites in result.files.items():
        if not sites:
            continue
        tool = rel.split("/")[1] if rel.startswith("tools/") else None
        stem = Path(tool).stem.lstrip("_") if tool else None
        hosts = result.tools.get(stem, "both") if stem else "both"
        hid = {h: sum(1 for s in sites if h in s.excused) for h in ("maya", "blender")}
        n_gaps = sum(1 for s in sites if id(s) in gap_sites)
        w(f"| `{rel}` | {hosts} | {len({s.chain for s in sites})} | {len(sites)} | {hid['maya']} | "
          f"{hid['blender']} | {'**' + str(n_gaps) + '**' if n_gaps else 0} |")
    w("")
    w("## One-host operations")
    w("")
    w("Every chain one library lacks, and what keeps the shared slots from calling it there. "
      "Each is a conscious divergence: the day the other host gains the operation, the check "
      "lets it run there (or drop the `requires`) and the row goes.")
    w("")
    w("| chain | lacking | kept off by | called from |")
    w("|:--|:--|:--|:--|")
    for (chain, host, why), sites in result.one_host.items():
        w(f"| `{chain}` | {host} | {why} | {_where(sites)} |")
    w("")
    scoped = {t: h for t, h in result.tools.items() if h != "both"}
    if scoped:
        w("Tools with no contract on every host (`slots.tools`): " + ", ".join(
            f"`{t}` ({h})" for t, h in sorted(scoped.items())) + ".")
        w("")
    if n_unverified:
        w("## Unverified (listed, not failed: the static model cannot see into them)")
        w("")
        w("| chain | host | why |")
        w("|:--|:--|:--|")
        for (chain, host), why in sorted(result.unverified.items()):
            w(f"| `{chain}` | {host} | {why} |")
        for rel, where, line, source in result.computed:
            w(f"| `{source}` | both | a name computed at runtime (`{rel}` {where}) |")
        w("")
    if result.unchecked:
        w("## Unchecked signatures (listed, not failed)")
        w("")
        w("`starred`: the call spreads `*args` / `**kwargs`; `forwarded`: the target takes "
          "`*args` / `**kwargs` the call relies on, so what it forwards to is not followed.")
        w("")
        w("| chain | why | called from |")
        w("|:--|:--|:--|")
        for (chain, note), sites in result.unchecked.items():
            w(f"| `{chain}` | {note} | {_where(sites)} |")
        w("")
    return "\n".join(L) + "\n"


def _print_panel(result: SweepResult, name: str) -> int:
    wanted = {name, name.removesuffix(".py"), name.removesuffix("Slots")}
    match = None
    for rel in result.files:
        stem = Path(rel).stem
        camel = "".join(p.capitalize() for p in stem.split("_"))
        if rel in wanted or stem in wanted or camel in wanted or f"{camel}Slots" in wanted:
            match = rel
            break
    if match is None:
        for rel, sites in result.files.items():
            if any(s.where.split(".")[0] in (name, f"{name}Slots") for s in sites):
                match = rel
                break
    if match is None:
        sys.exit(f"could not resolve {name!r} to a shared slots module under tentacle/tentacle/slots/")
    sites = result.files[match]
    gaps = [g for g in result.gaps if any(s.rel == match for s in g.sites)]
    print(f"# Toolkit parity -- tentacle/tentacle/slots/{match}")
    print()
    for s in sorted(sites, key=lambda s: (s.chain, s.line)):
        verdict = []
        for h in ("maya", "blender"):
            gap = next((g for g in gaps if g.host == h and s in g.sites), None)
            if gap:
                verdict.append(f"{h}: GAP ({gap.problem})")
            elif h in s.excused:
                verdict.append(f"{h}: {s.excused[h]}")
            elif (s.chain, h) in result.unverified:
                verdict.append(f"{h}: unverified ({result.unverified[(s.chain, h)]})")
            else:
                verdict.append(f"{h}: ok")
        print(f"  {s.line:>5} {s.where:40} {s.chain:44} " + "; ".join(verdict))
    print()
    print(f"## SUMMARY: {len(sites)} call sites, {len(gaps)} gap(s).")
    return 1 if gaps else 0


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):  # Windows console defaults to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    if argv[0] in ("--all", "--panel"):
        try:
            result = sweep(ROOT)
        except GateError as error:
            print(f"compare_panel_surface: {error}", file=sys.stderr)
            return 2
    if argv[0] == "--all":
        text = report(result)
        if "--write" in argv:
            out = _surface_out(ROOT)
            out.write_text(text, encoding="utf-8")
            print(f"Wrote {out.relative_to(ROOT).as_posix()} (exit {int(result.failed)})")
        else:
            print(text)
        return int(result.failed)
    if len(argv) == 2 and argv[0] == "--panel":
        return _print_panel(result, argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
