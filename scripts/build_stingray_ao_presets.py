#!/usr/bin/env python
"""Generate mayatk's AO-capable StingrayPBS opacity presets from Maya's own.

Autodesk ships three ShaderFX presets for StingrayPBS. Only `Standard.sfx`
carries an ambient-occlusion chain; `Standard_Masked.sfx` and
`Standard_Transparent.sfx` leave the Standard Base node's 'Ambient Occlusion'
socket unconnected, so an opacity material could never carry AO -- not in the
viewport, not in the FBX (`Maya|TEX_ao_map` never written, Unity's occlusion
slot empty), not in the GLB's ORM. This script splices the opaque preset's three
AO node records -- the `use_ao_map` variable, the `ao_map` sampler and the
switch feeding that socket -- verbatim into the two opacity presets, so the slot
names are Autodesk's and every exporter/importer treats them as on the opaque
graph.

Why text, not the ShaderFX command API: the API can add the nodes live, but
there is no `saveGraph` flag and a scene save re-serialises the graph in a way
the loader then discards for API-added nodes. Records copied from a preset the
loader already accepts survive.

Why `preset_path=Custom`: on scene open the plugin re-loads the preset named in
the Standard Base record and overlays the stored state, dropping nodes that
preset lacks (measured: pointing a merged graph at `presets/Standard` reopened
as the 32-node opaque graph). A name no install carries makes it keep the stored
records, so a scene built with these presets reopens complete on any machine --
the preset file is needed at build time only.

Format notes (SFB_WIN block): one `#NT=<type> 0` record per node, index-
addressed in record order; connections live on the SOURCE record as
`C=<self> 0 <outSocket> <dstRecord> <dstSocket> <dstSocket+1> 0` under `CC=`;
socket defaults/swizzles as `SDV=` / `SCS=`. The JSON half mirrors nodes and
connections by GUID (socket connector ids are class-level constants).

Usage
-----
  python build_stingray_ao_presets.py                 # (re)write the presets
  python build_stingray_ao_presets.py --check         # exit 1 if the shipped files drift
  python build_stingray_ao_presets.py --maya PATH     # Maya install to read the stock presets from
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
OUT_DIR = os.path.join(REPO, "mayatk", "mayatk", "mat_utils", "shaderfx")
PRESETS = (
    ("Standard_Masked.sfx", "Standard_Masked_AO.sfx"),
    ("Standard_Transparent.sfx", "Standard_Transparent_AO.sfx"),
)
SOURCE = "Standard.sfx"

# Socket connector GUIDs, class-level (identical in every preset), read from Standard.sfx.
CONNECTOR = {
    "sampler_uv": "1ee9af1f-65f2-4739-ad28-5ea6a0e68fc3",
    "base_ao": "59fd1cf4-f736-470d-8510-1dd7c016639e",
    "if_a": "CED7BBF3-0B48-4335-B933-095A41CA0294",
    "if_true": "4CBB4480-79E8-4CE7-AC0F-8B09BAF12390",
}
NEW_IDS = {
    "var": "abbaabba-abba-abba-abba-abbaabbaac01",
    "tex": "abbaabba-abba-abba-abba-abbaabbaac02",
    "sw": "abbaabba-abba-abba-abba-abbaabbaac03",
}
STANDARD_BASE_TYPE = 20176
PRESET_PATH_RE = re.compile(r"preset_path=1 v=5000 [^\n]+")
PARENT_RE = re.compile(r"ParentMaterial=[^\n]+")


def stock_presets_dir(maya: str | None) -> str:
    """Maya's StingrayPBS preset folder: `--maya`, `MAYA_LOCATION`, else the newest install."""
    roots = [maya, os.environ.get("MAYA_LOCATION")]
    roots += sorted(
        glob.glob(
            os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"), "Autodesk", "Maya*"
            )
        ),
        reverse=True,
    )
    for root in roots:
        if root:
            d = os.path.join(root, "presets", "ShaderFX", "Scenes", "StingrayPBS")
            if os.path.isdir(d):
                return d
    sys.exit("no Maya install with ShaderFX presets found (pass --maya)")


def read(path: str) -> str:
    """Strict UTF-8: a byte the presets could not carry must fail, not be rewritten."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def split_records(text: str):
    """(preamble, [record texts], rest-after-records) for the SFB_WIN block."""
    hdr_end = text.index("*/")
    head, rest = text[:hdr_end], text[hdr_end:]
    parts = re.split(r"(?m)^#NT=", head)
    return parts[0], ["#NT=" + p for p in parts[1:]], rest


def rec_index(recs, name: str | None = None, nt: int | None = None) -> int:
    for i, r in enumerate(recs):
        if name and re.search(r"name=1 v=5000 " + re.escape(name) + r"\s", r):
            return i
        if nt and r.startswith(f"#NT={nt} "):
            return i
    raise KeyError(name or nt)


def node_blocks(text: str) -> dict:
    """The JSON half's node blocks, keyed by title."""
    start = text.index("nodes = [\n") + len("nodes = [\n")
    end = text.rindex("\n]\nversion = 3")
    blocks = re.findall(r"\t\{ \n[\s\S]*?\n\t\} \n", text[start:end] + "\n")
    out: dict = {}
    for b in blocks:
        m = re.search(r'title = "([^"]+)"', b)
        if m:
            out.setdefault(m.group(1), []).append(b)
    return out


def node_id(block: str) -> str:
    return re.search(r'\n\t\tid = "([^"]+)"', block).group(1)


def connection_entry(
    connector: str, dst_id: str, src_id: str, select: str | None = None
) -> str:
    sel = f'\t\tselect = [ \n\t\t\t"{select}"\n\t\t\t] \n' if select else ""
    return (
        "\t{ \n\t\tdestination = { \n"
        f'\t\t\tconnector_id = "{connector}" \n'
        f'\t\t\tinstance_id = "{dst_id}" \n'
        "\t\t} \n" + sel + "\t\tsource = { \n"
        f'\t\t\tinstance_id = "{src_id}" \n'
        "\t\t} \n\t} \n"
    )


def merge(std: str, dst: str, label: str) -> str:
    """The AO-capable text of opacity preset *dst*, given the opaque preset *std*."""
    _, recs_s, _ = split_records(std)
    pre_d, recs_d, rest_d = split_records(dst)
    r_var = recs_s[rec_index(recs_s, "use_ao_map")]
    r_tex = recs_s[rec_index(recs_s, "ao_map")]
    r_sw = recs_s[rec_index(recs_s, "Ao_Map_Swtich")]  # Autodesk's spelling
    base_d = rec_index(recs_d, nt=STANDARD_BASE_TYPE)
    rough_d = rec_index(recs_d, "roughness_map")
    n = len(recs_d)
    i_var, i_tex, i_sw = n, n + 1, n + 2

    # The UV chain's last node: whatever feeds roughness_map's UV socket (input 0).
    feed_d = feed_sock = None
    for i, r in enumerate(recs_d):
        m = re.search(rf"C={i} 0 (\d+) {rough_d} 0 1 0", r)
        if m:
            feed_d, feed_sock = i, m.group(1)
            break
    if feed_d is None:
        raise ValueError(f"{label}: UV feed of roughness_map not found")

    def renumber(rec, pattern, replacement):
        new, k = re.subn(pattern, replacement, rec)
        if k != 1:
            raise ValueError(f"{label}: connection line not found: {pattern!r}")
        return new

    r_var = renumber(
        r_var, r"C=\d+ 0 1 \d+ 0 1 0", f"C={i_var} 0 1 {i_sw} 0 1 0"
    )  # use_ao_map -> If.A
    r_tex = renumber(
        r_tex, r"C=\d+ 0 3 \d+ 2 3 0", f"C={i_tex} 0 3 {i_sw} 2 3 0"
    )  # ao_map.RGBA -> If.True (SCS=r)
    r_sw = renumber(
        r_sw, r"C=\d+ 0 5 \d+ 8 9 0", f"C={i_sw} 0 5 {base_d} 8 9 0"
    )  # If.Result -> Ambient Occlusion

    feed = recs_d[feed_d]
    cc = re.search(r"CC=(\d+)", feed)
    if not cc:
        raise ValueError(f"{label}: feed record has no CC=")
    feed = feed.replace(f"CC={cc.group(1)}", f"CC={int(cc.group(1)) + 1}", 1)
    insert_at = feed.index("\n", feed.rindex("CPC=0")) + 1
    feed = (
        feed[:insert_at]
        + f"\t\t\tC={feed_d} 0 {feed_sock} {i_tex} 0 1 0\n\t\t\tCPC=0\n"
        + feed[insert_at:]
    )
    recs_d[feed_d] = feed

    pre_d = re.sub(r"NumberOfNodes=\d+", f"NumberOfNodes={n + 3}", pre_d)
    if not recs_d[-1].endswith("\n"):
        recs_d[-1] += "\n"
    merged = pre_d + "".join(recs_d) + r_var + r_tex + r_sw + rest_d

    blocks_s, blocks_d = node_blocks(std), node_blocks(dst)
    b_var, b_tex, b_sw = (
        blocks_s["Use Ao Map"][0],
        blocks_s["Ao Map"][0],
        blocks_s["Ao Map Swtich"][0],
    )
    for new_id in NEW_IDS.values():
        if new_id in merged:
            raise ValueError(f"{label}: id {new_id} already present")
    b_var = b_var.replace(node_id(b_var), NEW_IDS["var"])
    b_tex = b_tex.replace(node_id(b_tex), NEW_IDS["tex"])
    b_sw = b_sw.replace(node_id(b_sw), NEW_IDS["sw"])
    base_id = node_id(blocks_d["Standard Base"][0])
    add_id = node_id(blocks_d["Add"][0])
    conns = (
        connection_entry(CONNECTOR["sampler_uv"], NEW_IDS["tex"], add_id)
        + connection_entry(CONNECTOR["base_ao"], base_id, NEW_IDS["sw"])
        + connection_entry(CONNECTOR["if_a"], NEW_IDS["sw"], NEW_IDS["var"])
        + connection_entry(
            CONNECTOR["if_true"], NEW_IDS["sw"], NEW_IDS["tex"], select="r"
        )
    )
    conn_end = merged.index("\n]\nnodes = [")
    merged = merged[:conn_end] + "\n" + conns.rstrip("\n") + merged[conn_end:]
    nodes_end = merged.rindex("\n]\nversion = 3")
    merged = (
        merged[:nodes_end]
        + "\n"
        + (b_var + b_tex + b_sw).rstrip("\n")
        + merged[nodes_end:]
    )

    merged, k1 = PRESET_PATH_RE.subn("preset_path=1 v=5000 Custom", merged, count=1)
    merged, k2 = PARENT_RE.subn("ParentMaterial=Custom", merged, count=1)
    if k1 != 1 or k2 != 1:
        raise ValueError(f"{label}: preset identity fields not found")
    return merged


def build(maya: str | None) -> dict:
    """``{output name: merged text}`` for every preset."""
    stock = stock_presets_dir(maya)
    std = read(os.path.join(stock, SOURCE))
    return {
        out: merge(std, read(os.path.join(stock, src)), src) for src, out in PRESETS
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the shipped presets differ from a fresh build",
    )
    ap.add_argument("--maya", help="Maya install root to read the stock presets from")
    args = ap.parse_args(argv)
    built = build(args.maya)
    if args.check:
        stale = [
            n
            for n, text in built.items()
            if not os.path.exists(os.path.join(OUT_DIR, n))
            or read(os.path.join(OUT_DIR, n)).replace("\r\n", "\n") != text
        ]
        print("stale: " + ", ".join(stale) if stale else "AO presets up to date")
        return 1 if stale else 0
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, text in built.items():
        with open(
            os.path.join(OUT_DIR, name), "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(text)
        print(
            f"wrote {os.path.relpath(os.path.join(OUT_DIR, name), REPO)} ({len(text)} chars)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
