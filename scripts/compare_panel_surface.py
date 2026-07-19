#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mechanically diff the *full control surface* of every mayatk panel / tentacle slot against
its blendertk twin, and classify every delta through the triage ledger.

Why v2 exists — the v1 diff (pure AST over the slot .py only) had three proven failure modes:
  * loop-built controls with variable ``setObjectName`` collapsed to one junk key
    (7 phantom gaps on Naming; masked the genuinely-missing ``chk026`` on transform);
  * ``if __name__ == "__main__"`` demo blocks counted as panel surface
    (phantom ``config_buttons ['hide']`` on WheelRig/TubeRig);
  * the ``.ui`` XML side was never read at all, so dead Maya handlers (widget deleted from
    the shared .ui) reported as Blender gaps, and co-located twin ``.ui`` files could drift
    silently.

v2 extracts, per slot/panel file (still static — no imports, no DCC):
  * every menu / option-box / context / action control — **unrolling for-loops over literal
    tables** (``_SIMILAR_CRITERIA``-style), resolving local menu **aliases**
    (``m = widget.option_box.menu``), and evaluating **f-string** objectNames;
  * control **properties** (setChecked / setValue / set_limits / setPrefix / setToolTip) so
    default flips are visible, and **combo item lists** (``widget.add([...])`` /
    ``handle.addItem(...)`` loops);
  * ``config_buttons``, option-box affordances (full plugin family), ``register_menu_action``,
    ``header_actions.add``, ``HEADER_MENU_ITEMS``, ``@Signals`` overrides;
  * hide-until-ported ``*_init`` stubs (classified *hidden*, no longer "handled");
  * AttributeSpec/option-dict dynamic bodies (reported informationally);
and per ``.ui`` file (ElementTree, real XML):
  * the widget inventory + interesting properties (twin co-located ``.ui`` files are diffed
    name-by-name; the shared tentacle ``.ui`` gives handler-staleness ground truth);
  * a ``<customwidgets>`` lint — a promoted class missing from the block silently loads as a
    plain QWidget (the Curtain ``cmb000`` gotcha).

Every Maya->Blender delta is then classified through ``tentacle/docs/parity_map.py`` (the
triage ledger): na / renamed / relocated / replaced / pending / accepted-delta. Deltas the
ledger does not cover and the matcher cannot explain are **UNTRIAGED** and fail the sweep
(exit 1) — that is the CI contract. Handlers whose widget exists in no .ui and no code are
**stale Maya dead code** (a Maya-side cleanup list, not a Blender gap). Maya-only slot files
whose stem is a ``MayaNativeMenus.MENU_MAPPING`` key are the native-menu counterpart set
(Blender: ``blender.py`` + ``btk.call_native_menu``) and are excluded from the missing list.

Usage:
    python compare_panel_surface.py --panel reference_manager   # one pair, full detail
    python compare_panel_surface.py --all                       # sweep, print report
    python compare_panel_surface.py --all --write               # regenerate PARITY_SURFACE.md
"""
from __future__ import annotations
import ast
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_PATH = os.path.join(ROOT, "tentacle", "docs", "parity_map.py")
SURFACE_OUT = os.path.join(ROOT, "tentacle", "docs", "PARITY_SURFACE.md")
NATIVE_MENUS = os.path.join(ROOT, "mayatk", "mayatk", "ui_utils", "maya_native_menus.py")

UNRESOLVED = object()

# Control properties worth diffing (a flipped default silently changes first-use behavior).
PROPS = (
    "setChecked", "setValue", "set_limits", "setPrefix", "setSuffix",
    "setCurrentIndex", "setToolTip", "setText",
)
# Option-box plugin families + related per-widget affordances (v1 tracked only the first 4).
AFFORDANCES = {
    "set_toggle", "pin", "add_presets", "preset_dir", "set_action", "add_action",
    "set_filter", "set_disable", "add_value", "set_reset", "browse", "recent",
    "enable_clear", "set_help_text", "wire_combo", "make_preset_combo",
}
# .ui properties worth diffing on same-named widgets in twin files.
UI_PROPS = (
    "text", "toolTip", "value", "minimum", "maximum", "singleStep", "decimals",
    "prefix", "suffix", "checked", "enabled", "visible", "title", "placeholderText",
)
# Widget classes that constitute the *interactive* surface — containers/chrome (QToolBox
# pages, group boxes, Header, Region) are layout, not parity rows.
INTERACTIVE_UI = {
    "LineEdit", "QLineEdit", "ComboBox", "QComboBox", "WidgetComboBox", "SpinBox", "QSpinBox",
    "QDoubleSpinBox", "DoubleSpinBox", "CheckBox", "QCheckBox", "PushButton", "QPushButton",
    "ToolButton", "QToolButton", "RadioButton", "QRadioButton", "TableWidget", "QTableWidget",
    "ListWidget", "QListWidget", "TreeWidget", "QTreeWidget", "Slider", "QSlider",
    "QPlainTextEdit", "TextEdit", "QTextEdit", "Label", "QLabel", "MenuButton", "ExpandableList",
}
_WIDGET_HANDLER = re.compile(r"^[a-z]+\d{3}(_init)?$")


def read(path):
    return open(path, encoding="utf-8", errors="ignore").read()


# =========================================================================== ledger
def _check_duplicate_keys(src, path):
    """A duplicate key in a dict literal silently clobbers the earlier entry (this bit the
    nurbs HANDLERS block once) — fail loudly instead."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            seen = set()
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if k.value in seen:
                        sys.exit(f"{path}:{k.lineno}: duplicate key {k.value!r} in dict literal "
                                 "— the later entry silently clobbers the earlier one")
                    seen.add(k.value)


def load_ledger():
    """Load tentacle/docs/parity_map.py (pure data module) without importing project code."""
    src = read(LEDGER_PATH)
    _check_duplicate_keys(src, LEDGER_PATH)
    ns = {}
    exec(compile(src, LEDGER_PATH, "exec"), ns)
    return {
        "controls": ns.get("CONTROLS", {}),
        "controls_slots": ns.get("CONTROLS_SLOTS", {}),
        "handlers": ns.get("HANDLERS", {}),
        "panels": ns.get("PANELS", {}),
        "default_deltas": ns.get("DEFAULT_DELTAS", {}),
        "file_counterparts": ns.get("FILE_COUNTERPARTS", {}),
    }


def native_menu_keys():
    """MENU_MAPPING keys from mayatk's MayaNativeMenus, by AST (no import)."""
    if not os.path.isfile(NATIVE_MENUS):
        return set()
    tree = ast.parse(read(NATIVE_MENUS))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MENU_MAPPING" for t in node.targets
        ):
            if isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


# =========================================================================== partial evaluator
def _attr_chain(node):
    """Dotted attribute chain for a Call's func, e.g. 'widget.option_box.menu.add'."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):  # e.g. self.sb.get_ui(...).header
        parts.append("()")
    return ".".join(reversed(parts))


def resolve(node, env, tables):
    """Best-effort constant folding: literals, loop bindings, class/local literal tables,
    f-strings, dict.items(). Returns the value or UNRESOLVED."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in tables:
            return tables[node.id]
        return UNRESOLVED
    if isinstance(node, ast.Attribute):
        # self._TABLE / cls._TABLE -> class-level literal
        if isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"):
            if node.attr in tables:
                return tables[node.attr]
        return UNRESOLVED
    if isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        vals = [resolve(e, env, tables) for e in node.elts]
        if any(v is UNRESOLVED for v in vals):
            return UNRESOLVED
        return tuple(vals) if isinstance(node, ast.Tuple) else vals
    if isinstance(node, ast.Dict):
        keys = [resolve(k, env, tables) for k in node.keys]
        vals = [resolve(v, env, tables) for v in node.values]
        if any(v is UNRESOLVED for v in keys + vals):
            return UNRESOLVED
        return dict(zip(keys, vals))
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                r = resolve(v.value, env, tables)
                if r is UNRESOLVED:
                    return UNRESOLVED
                parts.append(str(r))
            else:
                return UNRESOLVED
        return "".join(parts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = resolve(node.operand, env, tables)
        return UNRESOLVED if v is UNRESOLVED else -v
    if isinstance(node, ast.Call):
        # <resolvable dict>.items()
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "items"
                and not node.args and not node.keywords):
            base = resolve(node.func.value, env, tables)
            if isinstance(base, dict):
                return list(base.items())
        return UNRESOLVED
    return UNRESOLVED


def bind_target(target, value, env):
    """Bind a for-loop target (possibly nested tuple) to a resolved element."""
    if isinstance(target, ast.Name):
        env[target.id] = value
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        try:
            items = list(value)
        except TypeError:
            return False
        if len(items) != len(target.elts):
            return False
        return all(bind_target(t, v, env) for t, v in zip(target.elts, items))
    return False


# =========================================================================== extraction
def _menu_location(chain, fn_name):
    """Where a control lives: optbox / action-col / header menu / table context menu / menu."""
    if "option_box" in chain:
        return "optbox"
    if chain.endswith("actions.add"):
        return "action-col"
    if fn_name and "header" in fn_name:
        return "header"
    if fn_name and ("tbl" in fn_name or "table" in fn_name):
        return "ctx"
    return "menu"


def _collect_tables(tree):
    """Module- and class-level literal assignments (the loop tables), plus HEADER_MENU_ITEMS."""
    tables = {}
    header_items = []

    def scan(body):
        for node in body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                node.targets[0], ast.Name
            ):
                name = node.targets[0].id
                val = resolve(node.value, {}, tables)
                if val is not UNRESOLVED:
                    tables[name] = val
                    if name == "HEADER_MENU_ITEMS" and isinstance(val, (list, tuple)):
                        header_items.extend(v for v in val if isinstance(v, (list, tuple)))
            elif isinstance(node, ast.ClassDef):
                scan(node.body)

    scan(tree.body)
    return tables, header_items


class Surface:
    """Extracted control surface of one slot/panel .py file."""

    def __init__(self, path):
        self.path = path
        self.src = read(path)
        self.config_buttons = []
        self.controls = {}        # key -> record dict
        self.affordances = Counter()
        self.slots = set()        # every def name
        self.signals = {}         # def name -> tuple of @Signals args
        self.hidden = set()       # widget names hidden by their _init (hide-until-ported)
        self.dynamic = []         # unresolvable control sites (need runtime/manual)
        self.spec_options = {}    # class name -> [option keys] (AttributeSpec dynamic bodies)
        self.list_trees = {}      # class attr name -> {category: [labels]} (ExpandableList data)
        self._extract()

    def referenced_beyond_defs(self, name):
        """True if `name` occurs in the source outside its own def lines — i.e. it is
        dispatched/called from elsewhere (list-wrapper engines, dispatch tables)."""
        occurrences = len(re.findall(rf"\b{re.escape(name)}\b", self.src))
        defs = len(re.findall(rf"\bdef {re.escape(name)}\b", self.src))
        return occurrences > defs

    # -------------------------------------------------------------- helpers
    def _add_control(self, key, loc, ctype, label, props, items=None, mech="code", fn=None):
        rec = self.controls.get(key)
        if rec is None:
            self.controls[key] = {
                "loc": loc, "ctype": ctype, "label": label,
                "props": props, "items": items, "mech": mech, "fn": fn,
            }
        else:  # merge (e.g. items attached later via addItem)
            if items:
                rec["items"] = (rec["items"] or []) + items
            rec["props"].update({k: v for k, v in props.items() if k not in rec["props"]})

    # -------------------------------------------------------------- main walk
    def _extract(self):
        try:  # a syntax error in a panel/slot file must name the file, not raise a raw traceback
            tree = ast.parse(self.src, filename=self.path)
        except SyntaxError as e:
            sys.exit(f"{self.path}:{e.lineno}: invalid syntax — {e.msg}")
        self.tables, header_items = _collect_tables(tree)
        for label, obj, *_ in ((i[0], i[1]) if len(i) >= 2 else (None, None) for i in header_items):
            key = obj or label
            if key:
                self._add_control(key, "header", "menu-item", label, {}, mech="declarative")

        # AttributeSpec-style dynamic bodies: class attrs resolving to a list of dicts
        # that each carry a 'key' (TubeRig strategy options, bridge PARAMS values).
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(
                        stmt.targets[0], ast.Name
                    ):
                        val = resolve(stmt.value, {}, self.tables)
                        if (isinstance(val, (list, tuple)) and val
                                and all(isinstance(d, dict) and "key" in d for d in val)):
                            self.spec_options.setdefault(node.name, []).extend(
                                d["key"] for d in val
                            )
                        # ExpandableList data tables: {category: [(label, target), ...]}
                        if (isinstance(val, dict) and val and all(
                                isinstance(v, (list, tuple)) and v
                                and all(isinstance(t, (list, tuple)) and t
                                        and isinstance(t[0], str) for t in v)
                                for v in val.values())):
                            self.list_trees[stmt.targets[0].id] = {
                                cat: [t[0] for t in items] for cat, items in val.items()
                            }

        funcs = []

        def gather(body):
            for node in body:
                if isinstance(node, ast.FunctionDef):
                    funcs.append(node)
                elif isinstance(node, ast.ClassDef):
                    gather(node.body)
                elif isinstance(node, ast.If) and _is_main_guard(node):
                    continue  # demo-launch block: not panel surface
        gather(tree.body)

        for fn in funcs:
            self.slots.add(fn.name)
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and _attr_chain(dec.func).endswith("Signals"):
                    args = tuple(a.value for a in dec.args
                                 if isinstance(a, ast.Constant) and isinstance(a.value, str))
                    if args:
                        self.signals[fn.name] = args
            self._process_block(fn.body, {}, {}, {}, fn.name, {}, in_loop=False)

    def _process_block(self, body, env, aliases, handles, fn_name, local_tables, in_loop):
        for node in body:
            if isinstance(node, ast.FunctionDef):  # nested closure — same surface
                self._process_block(node.body, dict(env), dict(aliases), dict(handles),
                                    fn_name, dict(local_tables), in_loop)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name):
                    if isinstance(node.value, ast.Attribute):
                        chain = self._expand(_attr_chain(node.value), aliases)
                        if "menu" in chain.split(".") or "option_box" in chain.split("."):
                            aliases[tgt.id] = chain
                            continue
                    if isinstance(node.value, ast.Call):
                        key = self._handle_call(node.value, env, aliases, handles, fn_name,
                                                local_tables, in_loop)
                        if key is not None:
                            handles[tgt.id] = key
                        continue
                    val = resolve(node.value, {**env, **local_tables}, self.tables)
                    if val is not UNRESOLVED:
                        local_tables[tgt.id] = val
                elif isinstance(tgt, ast.Attribute) and tgt.attr in AFFORDANCES:
                    self.affordances[tgt.attr] += 1  # e.g. menu.add_presets = True
            elif isinstance(node, ast.For):
                self._process_for(node, env, aliases, handles, fn_name, local_tables)
            elif isinstance(node, ast.If):
                self._process_block(node.body, env, aliases, handles, fn_name, local_tables, in_loop)
                self._process_block(node.orelse, env, aliases, handles, fn_name, local_tables, in_loop)
            elif isinstance(node, (ast.With, ast.Try)):
                subs = [node.body]
                if isinstance(node, ast.Try):
                    subs += [h.body for h in node.handlers] + [node.orelse, node.finalbody]
                for sub in subs:
                    self._process_block(sub, env, aliases, handles, fn_name, local_tables, in_loop)
            elif isinstance(node, ast.Expr):
                for call in _calls_in(node.value):
                    self._handle_call(call, env, aliases, handles, fn_name, local_tables, in_loop)
            elif isinstance(node, ast.Return) and node.value is not None:
                for call in _calls_in(node.value):
                    self._handle_call(call, env, aliases, handles, fn_name, local_tables, in_loop)

    def _process_for(self, node, env, aliases, handles, fn_name, local_tables):
        it = resolve(node.iter, {**env, **local_tables}, self.tables)
        if isinstance(it, dict):
            it = list(it)  # plain `for k in dct:` iterates KEYS (`.items()` is resolved in resolve())
        if isinstance(it, (list, tuple)) and len(it) <= 500:
            for elem in it:
                loop_env = dict(env)
                if bind_target(node.target, elem, loop_env):
                    self._process_block(node.body, loop_env, dict(aliases), dict(handles),
                                        fn_name, dict(local_tables), in_loop=True)
                else:
                    self._process_block(node.body, env, aliases, handles, fn_name,
                                        local_tables, in_loop=True)
                    break
        else:  # unresolvable iterable — walk once; unresolved keys become `dynamic` notes
            self._process_block(node.body, env, aliases, handles, fn_name, local_tables, in_loop=True)

    def _expand(self, chain, aliases):
        head, _, rest = chain.partition(".")
        if head in aliases:
            return aliases[head] + ("." + rest if rest else "")
        return chain

    # -------------------------------------------------------------- call handling
    def _handle_call(self, call, env, aliases, handles, fn_name, local_tables, in_loop):
        """Process one Call node; returns a control key when the call created a control."""
        scope = {**env, **local_tables}
        chain = self._expand(_attr_chain(call.func), aliases)
        parts = chain.split(".")
        last = parts[-1]

        if last == "config_buttons":
            for a in call.args:
                v = resolve(a, scope, self.tables)
                if isinstance(v, str) and v not in self.config_buttons:
                    self.config_buttons.append(v)
            return None

        if last in AFFORDANCES:
            self.affordances[last] += 1
            return None

        if last == "register_menu_action":
            name = resolve(call.args[0], scope, self.tables) if call.args else UNRESOLVED
            if isinstance(name, str):
                self._add_control(name, "ctx", "menu-action", name, {},
                                  mech="loop" if in_loop else "code", fn=fn_name)
            else:
                self.dynamic.append(f"{fn_name}: register_menu_action(<unresolved>)")
            return None

        if last == "add" and chain.endswith("header_actions.add"):
            name = resolve(call.args[0], scope, self.tables) if call.args else UNRESOLVED
            key = f"hdraction[{name if isinstance(name, str) else '?'}]"
            self._add_control(key, "header", "action", None, {}, fn=fn_name)
            return key

        if last == "add" and chain.endswith("actions.add"):
            states = next((k.value for k in call.keywords if k.arg == "states"), None)
            names = sorted(resolve(states, scope, self.tables).keys()) \
                if states is not None and isinstance(resolve(states, scope, self.tables), dict) else []
            key = f"action[{','.join(map(str, names))}]"
            self._add_control(key, "action-col", "action", None, {"states": names}, fn=fn_name)
            return key

        if last in ("addItem", "addItems") and parts[0] in handles:
            item = resolve(call.args[0], scope, self.tables) if call.args else UNRESOLVED
            items = ([item] if last == "addItem" else list(item)) \
                if item is not UNRESOLVED else None
            key = handles[parts[0]]
            rec = self.controls.get(key)
            if rec is not None:
                if items is None:
                    rec["props"]["items_dynamic"] = True
                else:
                    rec["items"] = (rec["items"] or []) + [
                        i if isinstance(i, str) else (i[0] if isinstance(i, (list, tuple)) and i else str(i))
                        for i in items
                    ]
            return None

        if last == "add" and "menu" in parts:
            kw = {k.arg: resolve(k.value, scope, self.tables) for k in call.keywords if k.arg}
            ctype = "?"
            if call.args:
                a0 = call.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    ctype = a0.value
                elif isinstance(a0, ast.Attribute):
                    ctype = a0.attr
            if ctype == "Separator":
                return None
            obj = kw.get("setObjectName")
            label = kw.get("setText")
            if obj in (None, UNRESOLVED) and label in (None, UNRESOLVED):
                self.dynamic.append(f"{fn_name}: {chain}({ctype}) — unresolved key")
                return None
            key = obj if isinstance(obj, str) else (label if isinstance(label, str) else f"{ctype}:{label}")
            props = {p: kw[p] for p in PROPS if p in kw and kw[p] is not UNRESOLVED}
            items = None
            if "addItems" in kw and isinstance(kw["addItems"], (list, tuple)):
                items = [str(i) for i in kw["addItems"]]
            self._add_control(key, _menu_location(chain, fn_name), ctype,
                              label if isinstance(label, str) else None, props, items,
                              mech="loop" if in_loop else "code", fn=fn_name)
            return key

        # ComboBox population: widget.add([...]) / <param>.add(dict|list) inside cmb###_init
        if last == "add" and fn_name and fn_name.endswith("_init"):
            arg0 = resolve(call.args[0], scope, self.tables) if call.args else UNRESOLVED
            if isinstance(arg0, (list, tuple, dict)):
                items = list(arg0.keys()) if isinstance(arg0, dict) else [
                    i if isinstance(i, str) else (i[0] if isinstance(i, (list, tuple)) and i else str(i))
                    for i in arg0
                ]
                wname = fn_name[: -len("_init")]
                self._add_control(wname, "combo", "ComboBox", None, {},
                                  [str(i) for i in items], mech="combo", fn=fn_name)
            return None

        # hide-until-ported: `widget.setVisible(False)` (or .hide()) inside a <name>_init
        if fn_name and fn_name.endswith("_init"):
            if (last == "setVisible" and call.args
                    and isinstance(call.args[0], ast.Constant) and call.args[0].value is False) \
                    or last == "hide":
                self.hidden.add(fn_name[: -len("_init")])
        return None


def _is_main_guard(node):
    t = node.test
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
            and t.left.id == "__name__")


def _calls_in(expr):
    return [n for n in ast.walk(expr) if isinstance(n, ast.Call)]


def _widget_handlers(slots):
    return {s for s in slots
            if _WIDGET_HANDLER.match(s) or (s.endswith("_init") and not s.startswith("__"))}


# =========================================================================== .ui XML
def parse_ui(path):
    """Widget inventory + interesting properties + <customwidgets> lint for one .ui file."""
    out = {"widgets": {}, "customs": set(), "lint": []}
    if not path or not os.path.isfile(path):
        return out
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        out["lint"].append(f"{os.path.basename(path)}: XML parse error: {e}")
        return out
    root = tree.getroot()
    for cw in root.findall(".//customwidget/class"):
        out["customs"].add(cw.text)

    def props_of(w):
        props = {}
        for p in w.findall("property"):
            name = p.get("name")
            if name not in UI_PROPS and name != "target":
                continue
            child = list(p)
            if child:
                props[name] = (child[0].text or "").strip()
        return props

    for w in root.iter("widget"):
        cls, name = w.get("class"), w.get("name")
        if not name:
            continue
        out["widgets"][name] = {"class": cls, "props": props_of(w)}
        if cls and not cls.startswith("Q") and cls not in out["customs"]:
            out["lint"].append(
                f"{os.path.basename(path)}: promoted class '{cls}' (widget '{name}') is "
                f"missing from <customwidgets> — it will silently load as a plain QWidget"
            )
    return out


def panel_ui_path(pyfile):
    cand = os.path.splitext(pyfile)[0] + ".ui"
    if os.path.isfile(cand):
        return cand
    cands = [c for c in glob.glob(os.path.join(os.path.dirname(pyfile), "*.ui"))]
    return cands[0] if len(cands) == 1 else None


def shared_ui(domain):
    """Merged widget inventory of the shared tentacle .ui files for one domain."""
    merged = {"widgets": {}, "lint": []}
    for p in glob.glob(os.path.join(ROOT, "tentacle", "tentacle", "ui", domain + ".ui")) + glob.glob(
        os.path.join(ROOT, "tentacle", "tentacle", "ui", domain + "#*.ui")
    ):
        ui = parse_ui(p)
        merged["widgets"].update(ui["widgets"])
        merged["lint"].extend(ui["lint"])
    return merged


# =========================================================================== pairing / diff
def _ledger_for(ledger, pair_key, is_slot):
    src = ledger["controls_slots"] if is_slot else ledger["controls"]
    return src.get(pair_key, {})


def _status_bucket(entry):
    s = entry.get("status", "na")
    return "pending" if s == "pending" else "triaged"


def diff_pair(maya_py, blend_py, pair_key, ledger, is_slot, domain=None):
    """Full classified diff of one pair. Returns a dict of classified delta lists."""
    m, b = Surface(maya_py), Surface(blend_py)
    lg = _ledger_for(ledger, pair_key, is_slot)
    lg_handlers = ledger["handlers"].get(pair_key, {}) if is_slot else {}
    accepted = ledger["default_deltas"].get(pair_key, {})

    ui_m = parse_ui(panel_ui_path(maya_py)) if not is_slot else None
    ui_b = parse_ui(panel_ui_path(blend_py)) if not is_slot else None
    ui_shared = shared_ui(domain) if is_slot else None

    d = {
        "m": m, "b": b, "pair": pair_key,
        "untriaged": [],      # (kind, key, detail) — gate exit code
        "pending": [],        # ledgered real gaps (open work)
        "triaged": [],        # ledgered divergences (na/renamed/relocated/replaced)
        "static_equiv": [],   # maya code-built control that exists as a Blender static widget
        "stale": [],          # maya handler/control with no widget anywhere: dead code
        "hidden": [],         # blender hide-until-ported stubs
        "prop_deltas": [],    # same-key controls with different defaults (report-only)
        "item_deltas": [],    # same-key combos with different item lists (report-only)
        "signal_deltas": [],  # same-named handlers with different @Signals (report-only)
        "extras": [],         # blender-only keys (report-only)
        "dynamic": m.dynamic + b.dynamic,
        "lint": [],
        "spec_options": {**m.spec_options, **b.spec_options},
    }
    if ui_m:
        d["lint"] += ui_m["lint"]
    if ui_b:
        d["lint"] += ui_b["lint"]
    if ui_shared:
        d["lint"] += ui_shared["lint"]

    def classify(kind, key, detail):
        entry = lg.get(key) or lg_handlers.get(key)
        if entry:
            to = f" -> {entry['to']}" if entry.get("to") else ""
            line = (kind, key, f"{detail}  [{entry.get('status')}{to}] {entry.get('reason', '')}")
            d[_status_bucket(entry)].append(line)
            return
        d["untriaged"].append((kind, key, detail))

    # ---- config buttons
    for name in m.config_buttons:
        if name not in b.config_buttons:
            classify("config-btn", f"config_buttons:{name}", f"header chrome '{name}'")

    # ---- affordances (multiset)
    for name, count in m.affordances.items():
        if b.affordances.get(name, 0) < count:
            classify("affordance", name, f"{name} (maya x{count}, blender x{b.affordances.get(name, 0)})")

    # ---- controls
    b_ui_names = set((ui_b or ui_shared or {"widgets": {}})["widgets"])
    for key in sorted(m.controls):
        if key in b.controls:
            continue
        rec = m.controls[key]
        detail = f"{rec['loc']} {rec['ctype']} {rec['label']!r}"
        if key in b.hidden:
            d["hidden"].append(("control", key, detail))
            continue
        if key in b_ui_names and (key in b.slots or f"{key}_init" in b.slots or not is_slot):
            # Maya builds it dynamically; Blender ships it as a static .ui widget (chk023 case)
            d["static_equiv"].append(("control", key, detail))
            continue
        classify("control", key, detail)

    # ---- ExpandableList data-tree diffs (report-only; data-driven per-DCC menus)
    for tname in sorted(set(m.list_trees) & set(b.list_trees)):
        mt, bt = m.list_trees[tname], b.list_trees[tname]
        for cat in sorted(set(mt) | set(bt)):
            missing = [x for x in mt.get(cat, []) if x not in bt.get(cat, [])]
            extra = [x for x in bt.get(cat, []) if x not in mt.get(cat, [])]
            if missing or extra:
                d["item_deltas"].append((f"{tname}[{cat}]", len(mt.get(cat, [])),
                                         len(bt.get(cat, [])), missing, extra))

    # ---- same-key property / item diffs
    for key in sorted(set(m.controls) & set(b.controls)):
        mr, br = m.controls[key], b.controls[key]
        for p in PROPS:
            if p == "setToolTip":
                continue  # tooltip wording drifts legitimately; don't diff text
            mv, bv = mr["props"].get(p), br["props"].get(p)
            if p == "setChecked":  # absence means unchecked — only real flips are deltas
                mv, bv = bool(mv), bool(bv)
            if mv != bv and (mv is not None or bv is not None):
                if f"{key}.{p}" in accepted:
                    continue
                d["prop_deltas"].append((key, p, mv, bv))
        mi, bi = mr.get("items"), br.get("items")
        if mi and bi and mi != bi:
            missing = [i for i in mi if i not in bi]
            extra = [i for i in bi if i not in mi]
            if missing or extra:
                d["item_deltas"].append((key, len(mi), len(bi), missing, extra))

    # ---- ledger data-quality: a `renamed` target must actually exist on the Blender side
    # (typos in `to:` otherwise go unnoticed and quietly excuse a real gap)
    b_names = set(b.controls) | b.slots | b.hidden | b_ui_names
    for key, e in {**lg, **lg_handlers}.items():
        to = e.get("to", "")
        if (e.get("status") == "renamed" and to
                and re.fullmatch(r"\w+", to) and to not in b_names):
            d["lint"].append(f"parity_map[{pair_key!r}][{key!r}]: renamed -> {to!r} "
                             "but no such name exists on the Blender side")

    # ---- blender extras (report-only; renamed/relocated ledger targets are expected)
    renames = {e.get("to") for e in {**lg, **lg_handlers}.values() if e.get("to")}
    for key in sorted(set(b.controls) - set(m.controls)):
        if key not in renames:
            rec = b.controls[key]
            d["extras"].append(("control", key, f"{rec['loc']} {rec['ctype']} {rec['label']!r}"))

    # ---- handlers (tentacle slots only)
    if is_slot:
        for h in sorted(_widget_handlers(m.slots) - _widget_handlers(b.slots)):
            base = h[: -len("_init")] if h.endswith("_init") else h
            entry = lg_handlers.get(h) or lg_handlers.get(base)
            if entry:
                to = f" -> {entry['to']}" if entry.get("to") else ""
                d[_status_bucket(entry)].append(
                    ("handler", h, f"[{entry.get('status')}{to}] {entry.get('reason', '')}"))
                continue
            in_ui = base in ui_shared["widgets"]
            m_dynamic = base in m.controls
            b_dynamic = base in b.controls
            if in_ui:
                if base in b.hidden:
                    d["hidden"].append(("handler", h, "widget hidden by Blender _init"))
                elif h.endswith("_init") and base in b.slots:
                    # the button IS handled on Blender; only Maya's _init (option box /
                    # menu content) is missing — a different, lesser class of gap
                    d["untriaged"].append(
                        ("handler", h, "Blender handles the widget but has no _init — Maya's "
                                       "option-box/menu content is not built"))
                else:
                    d["untriaged"].append(
                        ("handler", h, "shared-.ui widget UNHANDLED on Blender — visible but inert"))
            elif m_dynamic and b_dynamic:
                d["signal_deltas"].append((h, "wiring", "control exists on both; handler only in Maya"))
            elif m_dynamic:
                pass  # covered by the control diff above
            elif m.referenced_beyond_defs(base):
                pass  # internal engine method dispatched from code (list wrappers) — not UI surface
            else:
                d["stale"].append(("handler", h, "no widget in any shared .ui, none built in "
                                                 "code, no reference — dead Maya handler (delete it)"))
        # @Signals drift on same-named handlers
        for name in sorted(set(m.signals) & set(_widget_handlers(b.slots))):
            if m.signals.get(name) != b.signals.get(name):
                d["signal_deltas"].append((name, m.signals.get(name), b.signals.get(name)))

    # ---- twin .ui diff (co-located panels only; interactive widgets, not containers)
    if not is_slot and ui_m and ui_m["widgets"]:
        for name in sorted(ui_m["widgets"]):
            if ui_m["widgets"][name]["class"] not in INTERACTIVE_UI:
                continue
            if name not in ui_b["widgets"]:
                cls = ui_m["widgets"][name]["class"]
                classify("ui-widget", name, f".ui widget {cls}")
            else:
                mw, bw = ui_m["widgets"][name], ui_b["widgets"][name]
                if mw["class"] != bw["class"]:
                    d["prop_deltas"].append((name, "class", mw["class"], bw["class"]))
                for p in UI_PROPS:
                    if p in ("toolTip", "text", "title", "placeholderText"):
                        continue  # wording drifts legitimately; diff behavior-bearing props only
                    mv, bv = mw["props"].get(p), bw["props"].get(p)
                    if mv != bv and (mv is not None or bv is not None):
                        if f"{name}.{p}" not in accepted:
                            d["prop_deltas"].append((name, f".ui:{p}", mv, bv))
        for name in sorted(set(ui_b["widgets"]) - set(ui_m["widgets"])):
            if name not in renames and ui_b["widgets"][name]["class"] in INTERACTIVE_UI:
                d["extras"].append(("ui-widget", name, f".ui widget {ui_b['widgets'][name]['class']}"))

    return d


# =========================================================================== discovery
def _classes(pkg):
    """Map ``*Slots`` class name -> file for a package (skips build/ + tests)."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, pkg, pkg, "**", "*.py"), recursive=True):
        fp = f.replace("\\", "/")
        if "/build/" in fp or "/temp_tests/" in fp or "__pycache__" in fp:
            continue
        try:
            src = read(f)
        except OSError:
            continue
        for cn in re.findall(r"^class (\w+Slots)\b", src, re.M):
            out.setdefault(cn, f)
    return out


def _slot_files(dcc):
    d = os.path.join(ROOT, "tentacle", "tentacle", "slots", dcc)
    return {os.path.basename(f): f for f in glob.glob(os.path.join(d, "*.py"))
            if not os.path.basename(f).startswith("_")}


def _resolve(panel):
    def _find(pkg):
        for name in (panel + ".py", panel + "_slots.py"):
            hits = [h for h in glob.glob(os.path.join(ROOT, pkg, pkg, "**", name), recursive=True)
                    if "__pycache__" not in h]
            if hits:
                return hits[0]
        return None

    out = {}
    for pkg in ("mayatk", "blendertk"):
        hit = _find(pkg)
        if not hit:
            sys.exit(f"could not resolve {panel}.py (or {panel}_slots.py) under {pkg}/")
        out[pkg] = hit
    return out["mayatk"], out["blendertk"]


# =========================================================================== reports
def _fmt_group(w, title, rows, prefix="  - "):
    if not rows:
        return
    w(f"**{title}**")
    for kind, key, detail in rows:
        w(f"{prefix}`{key}` ({kind}) — {detail}")
    w("")


def _print_single(panel, maya_path, blend_path, ledger):
    is_slot = "/slots/" in maya_path.replace("\\", "/")
    key = os.path.splitext(os.path.basename(maya_path))[0]
    domain = key if is_slot else None
    d = diff_pair(maya_path, blend_path, key, ledger, is_slot, domain)
    rel = lambda p: os.path.relpath(p, ROOT)  # noqa: E731
    print(f"# Parity matrix — {panel}")
    print(f"  mayatk:    {rel(maya_path)}\n  blendertk: {rel(blend_path)}\n")
    for title, rows in (
        (">> UNTRIAGED (real gap or missing ledger entry)", d["untriaged"]),
        ("PENDING (ledgered open work)", d["pending"]),
        ("triaged divergences (OK)", d["triaged"]),
        ("static-equivalent in .ui (OK)", d["static_equiv"]),
        ("hidden-until-ported on Blender", d["hidden"]),
        ("STALE Maya dead code (delete)", d["stale"]),
        ("blendertk extras (review)", d["extras"]),
    ):
        if rows:
            print(f"## {title}")
            for kind, k, detail in rows:
                print(f"  {k:34} {kind:10} {detail}")
            print()
    if d["prop_deltas"]:
        print("## default/property deltas on same-named controls (review)")
        for k, p, mv, bv in d["prop_deltas"]:
            print(f"  {k:30} {p:16} maya={mv!r}  blender={bv!r}")
        print()
    if d["item_deltas"]:
        print("## combo item deltas (review)")
        for k, nm, nb, missing, extra in d["item_deltas"]:
            print(f"  {k}: {nm} -> {nb} items; missing={missing} extra={extra}")
        print()
    if d["signal_deltas"]:
        print("## wiring/signal deltas (review)")
        for row in d["signal_deltas"]:
            print(f"  {row}")
        print()
    if d["spec_options"]:
        print("## dynamic AttributeSpec bodies (informational)")
        for cls, keys in d["spec_options"].items():
            print(f"  {cls}: {sorted(set(keys))}")
        print()
    if d["dynamic"]:
        print("## unresolved dynamic sites (verify at runtime)")
        for line in d["dynamic"]:
            print(f"  {line}")
        print()
    if d["lint"]:
        print("## .ui lint")
        for line in d["lint"]:
            print(f"  {line}")
        print()
    n_unt = len(d["untriaged"])
    print(f"## SUMMARY: {n_unt} untriaged, {len(d['pending'])} pending, {len(d['triaged'])} triaged-OK, "
          f"{len(d['stale'])} stale-maya, {len(d['prop_deltas'])} prop deltas, "
          f"{len(d['item_deltas'])} item deltas.")
    return 1 if n_unt or d["lint"] else 0


def _sweep_report(ledger):
    L, rc = [], 0
    w = L.append
    w("# tentacle / blendertk — Maya->Blender Parity Matrix")
    w("")
    w("> **Auto-generated by `m3trik/scripts/compare_panel_surface.py --all --write`.** Do not "
      "edit by hand. Name-level companion to `PARITY_AUDIT.md`: every Maya control / widget / "
      "handler is matched against its Blender twin — loops over literal tables are unrolled, "
      "menu aliases and f-string names resolved, `__main__` demo blocks excluded, and twin "
      "`.ui` files diffed as XML. Every delta is classified through the triage ledger "
      "[`parity_map.py`](parity_map.py): **UNTRIAGED** rows fail the sweep (exit 1) — either "
      "fix the gap or ledger the divergence with a reason. `pending` = acknowledged open work; "
      "`stale` = dead Maya code to delete (not a Blender gap).")
    w("")

    open_work = []   # (pair, key, detail)
    stale_all = []   # (pair, key, detail)
    lint_all = []

    # ---------------- co-located panels
    mp, bp = _classes("mayatk"), _classes("blendertk")
    pairs = sorted(set(mp) & set(bp))
    missing_panels = sorted(set(mp) - set(bp))
    w("## mayatk <-> blendertk co-located `*Slots` panels")
    w("")
    w("| panel | untriaged | pending | triaged OK | prop deltas | status |")
    w("|:--|--:|--:|--:|--:|:--|")
    details = []
    for cn in pairs:
        key = os.path.splitext(os.path.basename(mp[cn]))[0]
        d = diff_pair(mp[cn], bp[cn], key, ledger, is_slot=False)
        nu, np_, nt, nd = len(d["untriaged"]), len(d["pending"]), len(d["triaged"]), len(d["prop_deltas"])
        rc = rc or int(bool(nu or d["lint"]))
        status = "**GAP**" if nu else ("open" if np_ else "OK")
        w(f"| {cn.replace('Slots', '')} | {nu} | {np_} | {nt} | {nd} | {status} |")
        open_work += [(cn.replace("Slots", ""), k, det) for _, k, det in d["pending"]]
        lint_all += d["lint"]
        if nu or nd or d["item_deltas"]:
            details.append((cn.replace("Slots", ""), d))
    w("")
    if details:
        w("### Panel deltas")
        w("")
        for name, d in details:
            w(f"#### {name}")
            _fmt_group(w, "UNTRIAGED", d["untriaged"])
            if d["prop_deltas"]:
                w("**property deltas (review)**")
                for k, p, mv, bv in d["prop_deltas"]:
                    w(f"  - `{k}.{p}` maya=`{mv!r}` blender=`{bv!r}`")
                w("")
            if d["item_deltas"]:
                w("**combo item deltas (review)**")
                for k, nm, nb, missing, extra in d["item_deltas"]:
                    w(f"  - `{k}` {nm}->{nb} items; missing={missing} extra={extra}")
                w("")

    # missing panels through the ledger
    na_p, pend_p, cp_p, unt_p = [], [], [], []
    for cn in missing_panels:
        e = ledger["panels"].get(cn)
        if not e:
            unt_p.append(cn)
            rc = 1
        elif e["status"] == "pending":
            pend_p.append((cn, e["reason"]))
        elif e["status"] == "counterpart":
            cp_p.append((cn, e.get("to", ""), e["reason"]))
        else:
            na_p.append((cn, e["reason"]))
    if unt_p:
        w(f"**UNTRIAGED missing panels ({len(unt_p)}):** " + ", ".join(unt_p))
        w("")
    if pend_p:
        w(f"**Open panel ports ({len(pend_p)}):**")
        for cn, reason in pend_p:
            w(f"- **{cn.replace('Slots', '')}** — {reason}")
            open_work.append((cn.replace("Slots", ""), "panel", reason))
        w("")
    if na_p:
        w(f"**N/A by design ({len(na_p)}):** " + "; ".join(
            f"{cn.replace('Slots', '')} ({r})" for cn, r in na_p))
        w("")
    if cp_p:
        for cn, to, reason in cp_p:
            w(f"**[counterpart-set OK]** {cn.replace('Slots', '')} <-> {to.replace('Slots', '')} — {reason}")
        w("")
    bonly = sorted(set(bp) - set(mp))
    if bonly:
        w("Blender-only panels: " + ", ".join(c.replace("Slots", "") for c in bonly))
        w("")

    # ---------------- tentacle marking-menu slots
    sm, sb_ = _slot_files("maya"), _slot_files("blender")
    slot_pairs = sorted(set(sm) & set(sb_))
    slot_missing = sorted(set(sm) - set(sb_))
    w("## tentacle marking-menu slots (`slots/maya` <-> `slots/blender`)")
    w("")
    w("| slot file | untriaged | pending | triaged OK | stale (Maya) | prop deltas | status |")
    w("|:--|--:|--:|--:|--:|--:|:--|")
    slot_details = []
    for n in slot_pairs:
        stem = os.path.splitext(n)[0]
        d = diff_pair(sm[n], sb_[n], stem, ledger, is_slot=True, domain=stem)
        nu, np_, nt, ns, nd = (len(d["untriaged"]), len(d["pending"]), len(d["triaged"]),
                               len(d["stale"]), len(d["prop_deltas"]))
        rc = rc or int(bool(nu or d["lint"]))
        status = "**GAP**" if nu else ("open" if np_ else "OK")
        w(f"| {n} | {nu} | {np_} | {nt} | {ns} | {nd} | {status} |")
        open_work += [(stem, k, det) for _, k, det in d["pending"]]
        stale_all += [(stem, k, det) for _, k, det in d["stale"]]
        lint_all += d["lint"]
        if nu or nd or d["item_deltas"]:
            slot_details.append((n, d))
    w("")
    if slot_details:
        w("### Slot deltas")
        w("")
        for n, d in slot_details:
            w(f"#### {n}")
            _fmt_group(w, "UNTRIAGED", d["untriaged"])
            if d["prop_deltas"]:
                w("**default/property deltas (review — a flipped default changes first-use behavior)**")
                for k, p, mv, bv in d["prop_deltas"]:
                    w(f"  - `{k}.{p}` maya=`{mv!r}` blender=`{bv!r}`")
                w("")
            if d["item_deltas"]:
                w("**combo item deltas (review)**")
                for k, nm, nb, missing, extra in d["item_deltas"]:
                    w(f"  - `{k}` {nm}->{nb} items; missing={missing} extra={extra}")
                w("")

    # missing slot files: native-menu counterpart set vs genuine
    native = native_menu_keys()
    stubs = [n for n in slot_missing if os.path.splitext(n)[0] in native]
    genuine_missing = [n for n in slot_missing if os.path.splitext(n)[0] not in native]
    if stubs:
        cp = ledger["file_counterparts"].get("maya_native_menus", {})
        w(f"**[counterpart-set OK] {len(stubs)} Maya-native-menu stubs** <-> "
          f"{cp.get('blender_counterpart', 'blender.py')} — {cp.get('reason', '')}")
        w("")
        w("<sub>" + ", ".join(sorted(stubs)) + "</sub>")
        w("")
    if genuine_missing:
        w(f"**UNTRIAGED missing slot files ({len(genuine_missing)}):** " + ", ".join(genuine_missing))
        rc = 1
        w("")

    # ---------------- rollups
    if stale_all:
        w("## Stale Maya dead code (cleanup list — not Blender gaps)")
        w("")
        for pair, k, det in stale_all:
            w(f"- `{pair}.py` `{k}` — {det}")
        w("")
    if open_work:
        w("## Open work (ledgered `pending`)")
        w("")
        for pair, k, det in open_work:
            w(f"- **{pair}** `{k}` — {det}")
        w("")
    if lint_all:
        w("## .ui lint")
        w("")
        for line in sorted(set(lint_all)):
            w(f"- {line}")
        w("")

    w(f"## Totals: {len(pairs)} panels paired; {len(slot_pairs)} tentacle slots paired; "
      f"{len(stubs)} native-menu stubs (counterpart-set); {len(open_work)} open-work items; "
      f"{len(stale_all)} stale Maya handlers. Sweep {'FAILS (untriaged deltas)' if rc else 'PASSES'}.")
    return rc, "\n".join(L) + "\n"


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):  # Windows console defaults to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ledger = load_ledger()
    if argv and argv[0] == "--all":
        rc, text = _sweep_report(ledger)
        if "--write" in argv:
            with open(SURFACE_OUT, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"Wrote {os.path.relpath(SURFACE_OUT, ROOT)} (exit {rc})")
        else:
            print(text)
        return rc
    if len(argv) == 2 and argv[0] == "--panel":
        return _print_single(argv[1], *_resolve(argv[1]), ledger)
    if len(argv) == 2:
        return _print_single(os.path.splitext(os.path.basename(argv[0]))[0], argv[0], argv[1], ledger)
    sys.exit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
