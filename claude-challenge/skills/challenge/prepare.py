"""Build a run file for the challenge workflow.

The workflow takes its subject as text, and a real subject is too large to pass by hand.
This reads the subject (HTML, Markdown or plain text), reduces markup to plain text, joins
it with the frame (a JSON file holding every other argument) and writes a copy of
``challenge.js`` with the arguments injected. Hand that copy to the Workflow tool.

    python prepare.py --subject design.html --frame frame.json --out run.js --mode plan

Prior art weighed: html2text and BeautifulSoup do the reduction better and are not in the
standard library; a run file must build on a machine that has only Python.
"""
import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

#: The modes the workflow knows. Only ``run`` spends; a mode it does not know must never
#: reach it, because anything that is not ``plan`` or ``stub`` runs real agents.
MODES = ("plan", "stub", "run")
#: The line a run file carries its arguments on.
MARK = "const INJECTED_ARGS = "
#: Stand-ins for a space and a line break inside ``<pre>``, put back once the rest of the
#: text has had its white space folded.
SPACE, BREAK = "", ""


class PlainText(HTMLParser):
    """Reduce an HTML page to the text a reader would take from it."""

    SKIP = {"style", "script", "svg", "head", "title"}
    BLOCK = {"p", "div", "section", "header", "footer", "figure", "figcaption", "table",
             "tr", "ul", "ol", "dl", "dt", "dd", "pre", "br", "article", "nav"}
    HEADING = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skipping = []
        self.pre = 0

    def handle_starttag(self, tag, attrs):
        if tag == "svg":  # a drawing is replaced by the sentence that describes it
            label = dict(attrs).get("aria-label")
            if label and not self.skipping:
                self.parts.append("\n[Figure: %s]\n" % label)
        if tag in self.SKIP:
            self.skipping.append(tag)
            return
        if self.skipping:
            return
        if tag == "pre":
            self.pre += 1
        if tag in self.HEADING:
            self.parts.append("\n\n" + self.HEADING[tag])
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skipping:
            if tag == self.skipping[-1]:
                self.skipping.pop()
            return
        if tag == "pre" and self.pre:
            self.pre -= 1
        if tag in self.HEADING or tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skipping:
            return
        if self.pre:  # a tree or a listing means its indentation and its lines
            self.parts.append(data.expandtabs(4).replace(" ", SPACE).replace("\n", BREAK))
        else:  # elsewhere a line break in the source is only white space to a reader
            self.parts.append(re.sub(r"\s+", " ", data))

    def text(self):
        out = "".join(self.parts)
        out = re.sub(r"[ \t\r\f\v]+", " ", out)
        out = re.sub(r" ?\n ?", "\n", out)
        out = re.sub(r"\n\| ", "\n", out)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        return out.replace(SPACE, " ").replace(BREAK, "\n")


def plain_text(path):
    """The subject as plain text: markup reduced for HTML, the file as written otherwise."""
    if not Path(path).is_file():
        raise SystemExit("no such file: %s" % path)
    raw = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() in (".html", ".htm"):
        parser = PlainText()
        parser.feed(raw)
        return parser.text()
    return raw.strip()


def build(script, subject, frame, previous=None, mode=None):
    """The workflow script with its arguments injected after the ``// @args`` line.

    *script* may be a run file built earlier: its old arguments are dropped, so the result
    never declares them twice. A *mode* outside ``MODES`` is refused here, before the
    workflow can take it for a run."""
    if not isinstance(frame, dict):
        raise SystemExit("the frame must be a JSON object (brief, criteria, seats, ...), not a %s" % type(frame).__name__)
    args = dict(frame)
    args["subject"] = {"title": frame.get("title") or Path(subject).stem, "text": plain_text(subject)}
    args.pop("title", None)
    if previous:
        args["previous"] = plain_text(previous)
    if mode:
        args["mode"] = mode
    if args.get("mode", "plan") not in MODES:
        raise SystemExit("mode must be one of %s, not %r" % (", ".join(MODES), args.get("mode")))
    if not Path(script).is_file():
        raise SystemExit("no such file: %s" % script)
    lines = [line for line in Path(script).read_text(encoding="utf-8").split("\n") if not line.startswith(MARK)]
    at = next((i for i, line in enumerate(lines) if line.startswith("// @args")), None)
    if at is None:
        raise SystemExit("no '// @args' line in %s" % script)
    # ensure_ascii keeps the literal valid JavaScript whatever the subject holds.
    lines.insert(at + 1, MARK + json.dumps(args, ensure_ascii=True))
    return "\n".join(lines), args


def main(argv=None):
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--subject", required=True, help="the document under test (.html, .md, .txt)")
    parser.add_argument("--frame", required=True, help="JSON: brief, criteria, seats, rivals, scenarios, ...")
    parser.add_argument("--out", required=True, help="where to write the run file")
    parser.add_argument("--previous", help="the last revision, so reviewers concentrate on what changed")
    parser.add_argument("--mode", choices=MODES, help="overrides the frame's mode")
    parser.add_argument("--script", default=str(here / "challenge.js"))
    opts = parser.parse_args(argv)

    try:
        frame = json.loads(Path(opts.frame).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read the frame %s: %s" % (opts.frame, exc))
    text, args = build(opts.script, opts.subject, frame, opts.previous, opts.mode)
    Path(opts.out).parent.mkdir(parents=True, exist_ok=True)
    Path(opts.out).write_text(text, encoding="utf-8", newline="\n")
    size = len(args["subject"]["text"])
    print("subject: %d characters, about %d tokens" % (size, size // 4))
    print("mode: %s" % args.get("mode", "plan"))
    print("run file: %s" % opts.out)


if __name__ == "__main__":
    main()
