#!/usr/bin/python
# coding=utf-8
"""Tests for generate_readme_diagrams.py -- the READMEs' relationship diagrams.

The diagrams restate what the workspace declares (the ecosystem set, each
pyproject's dependencies, the twin pair), so these pin the measuring (link
kinds, implied links dropped), the drawing (a valid, deterministic SVG that
fits its text, links routed clear of the cards), the narrated flows, the tiled
form (slices that cover the drawing once and keep motion whole), the README
sync (markers filled, drift and stale files found, line endings kept), and
that the committed outputs match the generator.
"""
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_readme_diagrams as g  # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"


def _pyproject(root: Path, pkg: str, deps=(), extras=None, dist=None) -> None:
    lines = ["[project]", f'name = "{dist or pkg}"', f"dependencies = {list(deps)!r}".replace("'", '"')]
    if extras:
        lines.append("[project.optional-dependencies]")
        lines += [f"{k} = {v!r}".replace("'", '"') for k, v in extras.items()]
    (root / pkg).mkdir(parents=True)
    (root / pkg / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestMeasuring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _pyproject(self.root, "core", ["numpy>=1"])
        # A distribution named apart from its folder (tentacle ships as tentacletk).
        _pyproject(self.root, "ui", ["core>=1", "qtpy"], dist="ui-kit")
        _pyproject(self.root, "host", ["core>=1", "ui-kit>=1"])
        _pyproject(self.root, "apps", ["ui-kit>=1"])
        _pyproject(self.root, "product", ["core", "ui-kit"], {"host": ["host>=1"], "apps": ["apps>=0.1,<0.2"]})
        self.packages = ("core", "ui", "host", "product", "apps")

    def edges(self):
        return g.ecosystem_edges(self.root, self.packages, products=("product", "apps"))

    def test_link_kinds_follow_the_pyproject_tables(self):
        kinds = {(e.src, e.dst): (e.kind, e.label) for e in self.edges()}
        self.assertEqual(kinds[("core", "ui")], ("requires", ""))
        self.assertEqual(kinds[("ui", "host")], ("requires", ""))  # named by its distribution
        self.assertEqual(kinds[("host", "product")], ("extra", "[host]"))
        # An extra naming a product is opened by name, never imported.
        self.assertEqual(kinds[("apps", "product")], ("opens", "[apps]"))
        # Outside packages (numpy, qtpy) are not nodes.
        self.assertFalse({e.src for e in self.edges()} - set(self.packages))

    def test_implied_links_are_dropped(self):
        kept = {(e.src, e.dst) for e in g.reduce_edges(self.edges())}
        self.assertNotIn(("core", "host"), kept)  # core -> ui -> host
        self.assertNotIn(("core", "product"), kept)  # core -> ui -> product, all required
        self.assertIn(("ui", "host"), kept)
        self.assertIn(("apps", "product"), kept)

    def test_a_path_through_an_install_extra_implies_no_requirement(self):
        # product requires ui; ui -> host -> product only holds with the [host]
        # extra, and a plain install of product still needs ui.
        kept = {(e.src, e.dst) for e in g.reduce_edges(self.edges())}
        self.assertIn(("ui", "product"), kept)

    def test_no_path_runs_through_an_opened_product(self):
        edges = [g.Edge("a", "b", "opens"), g.Edge("b", "c", "requires"), g.Edge("a", "c", "requires")]
        self.assertIn(g.Edge("a", "c", "requires"), g.reduce_edges(edges))


def _flow(**overrides) -> g.Diagram:
    diagram = g.Diagram(
        key="t",
        title="Test flow",
        nodes=[g.Node("a", "alpha", "first", "bolt"), g.Node("b", "beta", "second", "hub"),
               g.Node("c", "gamma", "third", "code", product=True), g.Node("d", "delta", "fourth", "grid")],
        edges=[g.Edge("a", "b", "requires"), g.Edge("b", "c", "extra", "[x]"), g.Edge("b", "d", "requires")],
        pairs=[g.Pair("c", "d", "paired")],
        legend=[("requires", "required by"), ("product", "imported by nothing")],
    )
    for key, value in overrides.items():
        setattr(diagram, key, value)
    return diagram


def _skip(**overrides) -> g.Diagram:
    """a feeds b and b2, and c needs a and b: a -> c must run through b's row."""
    return _flow(**{
        "nodes": [g.Node("a", "alpha", "x", "bolt"), g.Node("b", "beta", "x", "hub"),
                  g.Node("b2", "beta two", "x", "hub"), g.Node("c", "gamma", "x", "code")],
        "edges": [g.Edge("a", "b", "requires"), g.Edge("a", "b2", "requires"),
                  g.Edge("b", "c", "requires"), g.Edge("a", "c", "requires")],
        "pairs": [], "legend": [], **overrides,
    })


def _narrated(**overrides) -> g.Diagram:
    return _flow(**{
        "nodes": [g.Node("a", "alpha", "x", "user"), g.Node("b", "beta", "x", "layers"),
                  g.Node("c", "gamma", "x", "cube")],
        "edges": [g.Edge("a", "b", "flow"), g.Edge("b", "c", "flow")],
        "pairs": [], "legend": [],
        "steps": [g.Step("First a calls b.", (g.Message("a", "b", "call()"),)),
                  g.Step("Then b reaches c, and a hears back.",
                         (g.Message("b", "c", "run"), g.Message("b", "a", "done")))],
        **overrides,
    })


def _in_row(lay: g.Layout, x: float, row: int, pad: float = 0.0) -> bool:
    """Whether *x* falls on a card of display *row*."""
    return any(lay.box[n][0] - pad <= x <= lay.box[n][0] + lay.card_w + pad for n in lay.rows[row])


class TestDrawing(unittest.TestCase):
    def test_rows_rank_by_longest_path(self):
        lay = g.layout(_flow())
        self.assertEqual([sorted(r) for r in lay.rows], [["a"], ["b"], ["c", "d"]])
        self.assertLess(lay.box["a"][1], lay.box["b"][1])  # a flow reads downward
        self.assertEqual(lay.box["c"][1], lay.box["d"][1])

    def test_a_stack_builds_upward_with_its_top_nodes_above_all(self):
        # Listed in top, c and d share the top row; upward puts rank 0 at the bottom.
        lay = g.layout(_flow(upward=True, top=("c", "d"), pairs=[]))
        self.assertEqual(sorted(lay.rows[0]), ["c", "d"])
        self.assertEqual(lay.rows[-1], ["a"])

    def test_an_opened_product_beside_its_opener_is_linked_along_the_row(self):
        link = g.Edge("d", "c", "opens", "[apps]")
        diagram = _flow(edges=_flow().edges + [link], pairs=[], upward=True, top=("c", "d"))
        lay = g.layout(diagram)
        self.assertIn(link, lay.side)
        (x0, _), (x1, _) = lay.side[link]
        self.assertGreaterEqual(x1 - x0, g._pill_width("[apps]"))  # the gap holds its pill
        ET.fromstring(g.render(diagram, "light"))

    def test_svg_is_valid_and_deterministic(self):
        for theme in g.THEMES:
            first = g.render(_flow(), theme)
            self.assertEqual(first, g.render(_flow(), theme))
            root = ET.fromstring(first)
            self.assertEqual(root.tag, f"{SVG}svg")
            self.assertEqual(root.get("role"), "img")
            self.assertIn("alpha", root.find(f"{SVG}desc").text)

    def test_focus_dims_what_does_not_run_through_it(self):
        svg = g.render(_flow(), "light", focus="c")
        on = g.lit(_flow(), "c")
        self.assertEqual(on.nodes, {"a", "b", "c", "d"})  # d is c's pair
        self.assertNotIn(g.Edge("b", "d", "requires"), on.edges)
        self.assertIn("YOU ARE HERE", svg)
        self.assertIn('class="dim"', svg)

    def test_a_pair_whose_cards_are_both_lit_stays_lit(self):
        # Highlighting a, both c and d are downstream: their pair is lit too.
        self.assertEqual(g.lit(_flow(), "a").pairs, {g.Pair("c", "d", "paired")})

    def test_motion_respects_reduced_motion(self):
        svg = g.render(_flow(), "dark")
        self.assertIn("<animateMotion", svg)
        self.assertIn("prefers-reduced-motion", svg)

    def test_a_packet_leaves_as_the_one_before_it_arrives(self):
        root = ET.fromstring(g.render(_flow(edges=[g.Edge("a", "b", "requires"), g.Edge("b", "c", "requires")],
                                             pairs=[]), "light"))
        leaves = {m.get("begin") for m in root.iter(f"{SVG}animateMotion")}
        pulses = {r.find(f"{SVG}animate").get("begin") for r in root.iter(f"{SVG}rect") if r.get("class") == "pulse"}
        self.assertEqual(len(leaves), 2)
        self.assertTrue(leaves - {"0s"} <= pulses, f"packets leave at {leaves}, nodes pulse at {pulses}")

    def test_a_link_that_skips_a_row_runs_between_its_cards(self):
        lay = g.layout(_skip())
        pts = lay.wire[g.Edge("a", "c", "requires")]
        self.assertEqual(len(pts), 4)  # its ports, and its way through b's row
        (x, _), (x2, _) = pts[1], pts[2]
        self.assertEqual(x, x2)
        self.assertFalse(_in_row(lay, x, lay.row_of("b"), pad=g.CLEARANCE - 1), f"the wire crosses a card at x={x}")
        ET.fromstring(g.render(_skip(), "dark"))

    def test_a_link_never_runs_through_the_gap_a_pair_holds(self):
        # c hangs from b and b2 alike, so the straight line from a to c falls
        # midway between them, where their pair's link runs: the wire must go
        # round the row instead.
        edges = _skip().edges + [g.Edge("b2", "c", "requires")]
        lay = g.layout(_skip(edges=edges, pairs=[g.Pair("b", "b2", "twins")]))
        (x, _), _ = lay.wire[g.Edge("a", "c", "requires")][1:3]
        (lo, _), (hi, _) = lay.side[g.Pair("b", "b2", "twins")]
        self.assertFalse(lo - g.CLEARANCE <= x <= hi + g.CLEARANCE, f"the wire crosses the pair's link at x={x}")

    def test_text_that_cannot_fit_is_refused(self):
        long = _flow(nodes=[g.Node("a", "alpha", "a caption far too long for any card", "bolt")] + _flow().nodes[1:])
        with self.assertRaisesRegex(g.DiagramError, "wider than its box"):
            g.render(long, "light")
        wordy = _flow(nodes=[g.Node("a", "alpha", "x", "bolt", blurb="word " * 40)] + _flow().nodes[1:])
        with self.assertRaisesRegex(g.DiagramError, "runs past"):
            g.render(wordy, "light")

    def test_unknown_icon_and_cycle_are_refused(self):
        with self.assertRaisesRegex(g.DiagramError, "icon"):
            g.render(_flow(nodes=[g.Node("a", "alpha", "x", "nope")] + _flow().nodes[1:]), "light")
        with self.assertRaisesRegex(g.DiagramError, "cycle"):
            g.layout(_flow(edges=_flow().edges + [g.Edge("c", "a", "requires")], pairs=[]))


class TestNarration(unittest.TestCase):
    def _shown(self, svg: str, cls: str) -> List[Tuple[float, float]]:
        """When each element of *cls* is visible, as fractions of the loop."""
        spans = []
        for el in ET.fromstring(svg).iter():
            if cls in (el.get("class") or "").split():
                anim = next(a for a in el if a.tag == f"{SVG}animate")
                keys = [float(k) for k in anim.get("keyTimes").split(";")]
                values = anim.get("values").split(";")
                on = [k for k, v in zip(keys, values) if v == "1"]
                spans.append((on[0], on[-1]))
        return spans

    def test_each_step_shows_in_turn(self):
        svg = g.render(_narrated(), "light")
        said = self._shown(svg, "say")
        self.assertEqual(len(said), 2)
        self.assertLess(said[0][1], said[1][0])  # the first sentence is gone before the second
        self.assertEqual(len(self._shown(svg, "msg")), 3)  # one label per message

    def test_a_reply_rides_its_link_backwards(self):
        root = ET.fromstring(g.render(_narrated(), "light"))
        keys = [m.get("keyPoints") for m in root.iter(f"{SVG}animateMotion")]
        self.assertEqual(keys, ["0;0;1;1", "0;0;1;1", "1;1;0;0"])

    def test_reduced_motion_shows_the_first_step_still(self):
        svg = g.render(_narrated(), "dark")
        self.assertIn(".st{display:none}.s0{display:inline;opacity:1!important}", svg)
        self.assertIn('class="say st s0"', svg)

    def test_the_text_alternative_tells_the_steps(self):
        self.assertIn("(2) Then b reaches c", g.describe(_narrated()))

    def test_a_message_must_ride_a_link(self):
        bad = _narrated(steps=[g.Step("a reaches c directly.", (g.Message("a", "c", "jump"),))])
        with self.assertRaisesRegex(g.DiagramError, "runs along no link"):
            g.render(bad, "light")

    def test_the_flows_draw(self):
        for name, build in g.FLOWS.items():
            with self.subTest(flow=name):
                ET.fromstring(g.render(build(), "dark"))


class TestTiles(unittest.TestCase):
    def setUp(self):
        diagram = _skip(pairs=[g.Pair("b", "b2", "twins")], legend=[("requires", "required")], upward=True)
        diagram.nodes = [g.Node(n.id, n.name, n.caption, n.icon, link=f"https://example.com/{n.id}",
                                tip=f"{n.id} tip") for n in diagram.nodes]
        self.diagram = diagram
        self.lay = g.layout(diagram, title=False)
        self.lines = g.tiles(diagram, self.lay)

    def test_the_slices_cover_the_drawing_once(self):
        area = sum((t.box[2] - t.box[0]) * (t.box[3] - t.box[1]) for line in self.lines for t in line)
        self.assertAlmostEqual(area, self.lay.width * self.lay.height, places=3)
        for line in self.lines:
            self.assertEqual(line[0].box[0], 0)
            self.assertEqual(line[-1].box[2], self.lay.width)
            for left, right in zip(line, line[1:]):
                self.assertEqual(left.box[2], right.box[0])
        tops = [line[0].box[1] for line in self.lines]
        self.assertEqual(tops, sorted(tops))

    def test_each_card_is_its_own_slice(self):
        cards = [t.node for line in self.lines for t in line if t.node]
        self.assertEqual(sorted(cards), sorted(n.id for n in self.diagram.nodes))
        for tile in (t for line in self.lines for t in line if t.node):
            x0, y0, x1, y1 = self.lay.rect(tile.node)
            self.assertTrue(tile.box[0] <= x0 and x1 <= tile.box[2] and tile.box[1] <= y0 and y1 <= tile.box[3])

    def test_a_cut_never_splits_a_link(self):
        through = self.lay.wire[g.Edge("a", "c", "requires")][1:-1]
        for line in self.lines:
            for tile in line[1:]:
                cut = tile.box[0]
                self.assertFalse(any(abs(x - cut) < 3 and tile.box[1] <= y <= tile.box[3] for x, y in through))

    def test_motion_stays_within_one_slice(self):
        slices = [t for line in self.lines for t in line]
        _, items = g.draw(self.diagram, tiled=True)
        for item in items:
            if "<animateMotion" in item.svg:
                self.assertEqual(sum(g._overlap(item.box, t.box) for t in slices), 1, item.svg[:80])

    def test_the_block_links_each_card_and_keeps_its_rows_whole(self):
        nodes = {n.id: n for n in self.diagram.nodes}
        rows = [[(t, nodes.get(t.node), g._tile_alt(self.diagram, t)) for t in line] for line in self.lines]
        text = g.block("ecosystem", "alt", rows=rows)
        body = text.split("\n", 2)[2]
        self.assertNotIn("\n\n", body)  # a blank line would end the HTML block
        self.assertIn('<a href="https://example.com/a" title="a tip">', text)
        for line in body.split("<br>"):
            shares = [float(w) for w in re.findall(r'width="([\d.]+)%"', line)]
            self.assertAlmostEqual(sum(shares), g.ROW_SHARE, places=3)
            self.assertTrue(all('align="top"' in img for img in re.findall(r"<img [^>]*>", line)))

    def test_an_unlinked_card_is_no_link(self):
        nodes = {n.id: n for n in self.diagram.nodes}
        nodes["a"] = g.Node("a", "alpha", "x", "bolt")
        rows = [[(t, nodes.get(t.node), "") for t in line] for line in self.lines]
        self.assertNotIn("example.com/a", g.block("ecosystem", "alt", rows=rows))


class TestReadmeSync(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        self.readme = self.ws / "pkg" / "README.md"
        self.readme.parent.mkdir()
        patcher = mock.patch.object(g, "readmes", lambda ws: [self.readme])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, text: str, crlf: bool = False) -> None:
        self.readme.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))

    def test_marker_is_filled_and_svgs_planned(self):
        self._write("# pkg\n\n<!-- diagram:tentacle-launch -->\n<!-- /diagram:tentacle-launch -->\n")
        wanted, unused = g.plan(self.ws)
        out = self.ws / g.OUT_SUBDIR
        self.assertEqual(set(wanted), {self.readme, out / "tentacle-launch-light.svg", out / "tentacle-launch-dark.svg"})
        block = wanted[self.readme]
        self.assertIn("<picture>", block)
        self.assertIn(g.RAW_BASE + "tentacle-launch-dark.svg", block)
        self.assertIn("generate_readme_diagrams.py", block)  # says it is generated
        self.assertNotIn("<a href", block)  # only a package's own view links to the overview
        self.assertEqual(unused, [])

    def test_a_package_view_links_to_the_whole_ecosystem(self):
        text = g.block("ecosystem/uitk", "alt")
        self.assertIn(f'<a href="{g.OVERVIEW}">', text)
        self.assertLess(text.index("<a href"), text.index("<picture>"))

    def test_markers_inside_code_are_left_alone(self):
        text = ("# pkg\n\nWrite `<!-- diagram:<name> -->` to ask.\n\n```\n<!-- diagram:nope -->\n"
                "<!-- /diagram:nope -->\n```\n")
        self._write(text)
        self.assertEqual(g.plan(self.ws), ({}, []))

    def test_written_tree_is_in_sync_and_keeps_crlf(self):
        self._write("# pkg\n\n<!-- diagram:tentacle-launch -->\nstale text\n<!-- /diagram:tentacle-launch -->\n", crlf=True)
        wanted, _ = g.plan(self.ws)
        for path in g.drift(wanted):
            g.write(path, wanted[path])
        self.assertEqual(g.drift(g.plan(self.ws)[0]), [])
        raw = self.readme.read_bytes()
        self.assertNotIn(b"stale text", raw)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))

    def test_an_svg_nothing_asks_for_is_reported_and_kept_unless_pruned(self):
        # A published PyPI page embeds these URLs for good: never delete silently.
        self._write("# pkg\n")
        out = self.ws / g.OUT_SUBDIR
        out.mkdir(parents=True)
        old = out / "old-light.svg"
        old.write_text("<svg/>", encoding="utf-8")
        self.assertEqual(g.plan(self.ws)[1], [old])
        with mock.patch.object(g, "WORKSPACE", self.ws):
            self.assertEqual(g.main(["--check"]), 0)
            self.assertEqual(g.main([]), 0)
            self.assertTrue(old.is_file())
            self.assertEqual(g.main(["--prune"]), 0)
        self.assertFalse(old.exists())

    def test_main_exit_codes(self):
        self._write("<!-- diagram:tentacle-launch -->\n<!-- /diagram:tentacle-launch -->\n")
        with mock.patch.object(g, "WORKSPACE", self.ws):
            self.assertEqual(g.main(["--check"]), 1)  # drift, and nothing written
            self.assertFalse((self.ws / g.OUT_SUBDIR).exists())
            self.assertEqual(g.main([]), 0)
            self.assertEqual(g.main(["--check"]), 0)
            self._write("<!-- diagram:nope -->\n<!-- /diagram:nope -->\n")
            self.assertEqual(g.main(["--check"]), 2)

    def test_bad_markers_are_refused(self):
        self._write("<!-- diagram:nope -->\n<!-- /diagram:nope -->\n")
        with self.assertRaisesRegex(g.DiagramError, "unknown diagram"):
            g.plan(self.ws)
        self._write("<!-- diagram:tentacle-launch -->\n")
        with self.assertRaisesRegex(g.DiagramError, "no <!-- /diagram"):
            g.plan(self.ws)
        for malformed in ("<!-- diagram:Tentacle-Launch -->", "<!-- diagram:tentacle_launch -->",
                          "<!--diagram:tentacle-launch-->", "<!-- /diagram:tentacle-launch -->"):
            self._write(f"# pkg\n\n{malformed}\n")
            with self.assertRaisesRegex(g.DiagramError, "marker", msg=malformed):
                g.plan(self.ws)


@unittest.skipUnless(
    all((g.WORKSPACE / p / "pyproject.toml").is_file() for p in g.CARDS),
    "the ecosystem siblings are not checked out",
)
class TestCommittedState(unittest.TestCase):
    def test_every_ecosystem_package_has_a_card(self):
        with mock.patch.dict(g.CARDS):
            del g.CARDS["unitytk"]
            with self.assertRaisesRegex(g.DiagramError, "no card for unitytk"):
                g.ecosystem()

    def test_a_card_links_its_repo_unless_declared_unlinked(self):
        self.assertLessEqual(set(g.UNLINKED), set(g.CARDS))  # no stale row
        for node in g.ecosystem().nodes:
            with self.subTest(package=node.id):
                if node.id in g.UNLINKED:
                    self.assertEqual(node.link, "")
                else:
                    self.assertEqual(node.link, f"https://github.com/m3trik/{node.id}")
                self.assertTrue(node.tip)  # the pyproject's description

    def test_committed_diagrams_match_the_generator(self):
        # The same comparison as `generate_readme_diagrams.py --check`.
        wanted, _ = g.plan()
        self.assertEqual([p.as_posix() for p in g.drift(wanted)], [])

    def test_tentacle_requires_uitk_in_the_picture(self):
        # tentacle's hosts are install extras, so only its own requirement
        # stands for uitk (a plain `pip install tentacletk` brings uitk).
        self.assertIn(g.Edge("uitk", "tentacle", "requires"), g.ecosystem().edges)


if __name__ == "__main__":
    unittest.main()
