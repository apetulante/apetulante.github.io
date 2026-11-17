#!/usr/bin/env python3
"""Build the blog copy of the Transformer Colab notebook.

Takes the Colab export (``~/Downloads/Transformer_Tutorial.ipynb`` by default)
and writes a read-only blog copy into ``posts/Transformer/`` for the Quarto
site, applying every transform needed for it to render on the static site.

The script is a *pure function of its input*: it always reads the source
notebook fresh and fully regenerates the output, so it is re-runnable and
idempotent. Never hand-edit the generated blog copy -- fix the Colab notebook,
re-download it, and re-run this script.

Standard library only.

Transforms applied
------------------
1.  Front matter + badge. Prepends a raw cell with the Quarto YAML (title,
    date, description, categories, sort-order, image, ``execute: enabled:
    false``) and inserts an "Open in Colab" badge cell after the title H1.
2.  No execution. ``execute: enabled: false`` is written into the front matter
    as a safeguard (Quarto does not execute .ipynb by default anyway). The
    saved outputs are the content.
3.  Metadata cleanup. Strips notebook-level ``widgets`` (a known nbconvert/
    Quarto render-error source), ``colab`` and ``accelerator`` metadata, plus
    per-cell Colab cruft (``colab``, ``outputId``, ``executionInfo``,
    ``cellView``).
4.  Single-$ display math. Converts any markdown line that is a lone ``$`` into
    ``$$`` (Colab's MathJax accepts a lone ``$`` to open/close display math,
    Pandoc does not). Wrapping in ``$$`` also stops Pandoc from list-parsing
    ``1.``/``2.`` lines inside the math.
5.  ``\\( \\)`` / ``\\[ \\]`` math. Converts to ``$...$`` / ``$$...$$`` so it
    renders without relying on Pandoc's non-default tex_math_single_backslash.
6.  Colab ``#scrollTo=<id>`` links. Rewrites each to a real in-page anchor and
    installs that anchor at the target cell (resolved via the cell's
    ``metadata.id``): an explicit ``{#id}`` on heading targets, a leading
    ``<a id>`` on prose targets, and an inserted anchor cell before code-cell
    targets. Also fixes the malformed ``<a id="#A1">`` / ``<a id="#A2">``
    anchors (the ``#`` inside ``id`` is invalid).
7.  Diagram images. Downloads the GitHub-hosted diagram PNGs into the post's
    ``images/diagrams/`` folder and rewrites ``<img src>`` to relative paths
    (survives repo renames, renders offline).
8.  ipywidgets. Strips the non-interactive widget outputs (Colab sliders have
    no kernel on a static page) and inserts a note pointing readers to the
    Colab version. If a screenshot exists at ``images/widgets/<cellid>.png`` it
    is embedded in the note.
9.  ``!pip install`` cell. Hidden on the blog with ``#| include: false``.

Note: the listing thumbnail ``posts/Transformer/images/header.png`` is a
committed asset placed by hand (as with every other post), not something this
script generates. The front matter points ``image:`` at it.
"""

import json
import os
import re
import sys
import urllib.request

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.expanduser("~/Downloads/Transformer_Tutorial.ipynb")

POST_DIR = os.path.join(REPO_ROOT, "posts", "Transformer")
OUT_NB = os.path.join(POST_DIR, "transformer_tutorial.ipynb")
DIAGRAM_SUBDIR = os.path.join("images", "diagrams")   # relative to POST_DIR
WIDGET_SHOT_SUBDIR = os.path.join("images", "widgets")  # relative to POST_DIR

# The public Colab notebook the "Open in Colab" badge opens. NOTE: this is the
# copy in the apetulante/Tutorials repo -- push the current notebook there so
# the badge matches what the blog shows.
COLAB_URL = ("https://colab.research.google.com/github/apetulante/Tutorials/"
             "blob/master/Architectures/Basic_Transformer_Tutorial/"
             "Transformer_Tutorial.ipynb")

FRONT_MATTER = """---
title: "The Transformer Architecture"
author: "Abbie Petulante"
date: "2026-11-17"
sort-order: 7
categories: [architectures, LLMs, attention]
description: "A from-scratch guide to the full encoder-decoder transformer architecture. An overview of components, assembling and training, and how to evaluate, built up piece by piece."
image: "images/header.png"
toc: true
toc-depth: 3
execute:
  enabled: false
---
"""

BADGE = (
    '<a target="_blank" href="%s">\n'
    '  <img src="https://colab.research.google.com/assets/colab-badge.svg" '
    'alt="Open In Colab"/>\n'
    '</a>' % COLAB_URL
)

# Per-cell Colab metadata keys to drop.
CELL_META_DROP = ("colab", "outputId", "executionInfo", "cellView")
# Notebook-level metadata keys to drop.
NB_META_DROP = ("widgets", "colab", "accelerator")

WIDGET_MIME = "application/vnd.jupyter.widget-view+json"
WIDGET_STATE_MIME = "application/vnd.jupyter.widget-state+json"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def as_text(source):
    """nbformat `source` is a str or list[str]; return a single str."""
    return source if isinstance(source, str) else "".join(source)


def as_lines(text):
    """nbformat `source` should be a list of lines (each keeping its trailing
    newline). Quarto's .ipynb reader mishandles a single multi-line *string*
    source -- it drops blank lines (merging each heading into the paragraph
    that follows) and fails to detect a raw front-matter cell -- so every cell
    we write must use the list form."""
    lines = text.splitlines(keepends=True)
    return lines if lines else [""]


def md_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def raw_cell(text):
    return {"cell_type": "raw", "metadata": {}, "source": text}


def first_nonblank_line(text):
    for line in text.split("\n"):
        if line.strip():
            return line
    return ""


def is_heading(text):
    return bool(re.match(r"\s*#{1,6}\s", first_nonblank_line(text)))


# --------------------------------------------------------------------------- #
# Transform: math
# --------------------------------------------------------------------------- #
def fix_lone_dollar_math(text):
    """A markdown line that is exactly `$` becomes `$$` (display math)."""
    out = []
    for line in text.split("\n"):
        out.append("$$" if line.strip() == "$" else line)
    return "\n".join(out)


def fix_backslash_math(text):
    """`\\[ ... \\]` -> `$$ ... $$`, `\\( ... \\)` -> `$ ... $`."""
    text = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", text, flags=re.S)
    text = re.sub(r"\\\((.+?)\\\)", r"$\1$", text, flags=re.S)
    return text


def escape_text_underscores(text):
    """Escape literal `_` inside `\\text{...}`. In a `\\text{}` group you are in
    text mode, where a bare `_` is illegal LaTeX, so MathJax throws
    "'_' allowed only in math mode". Colab's MathJax is lenient about it;
    Pandoc/MathJax here is not. e.g. `\\text{vocab_size}` -> `\\text{vocab\\_size}`."""
    def fix(m):
        inner = re.sub(r"(?<!\\)_", r"\\_", m.group(1))
        return r"\text{" + inner + "}"
    return re.sub(r"\\text\{([^{}]*)\}", fix, text)


# list markers used in this notebook: bullets, `1.` and `1)` ordered styles
# list markers used in this notebook: bullets, `1.` and `1)` ordered styles
_LIST_ITEM_RE = re.compile(r"\s*([-*+]|\d+[.)])\s+\S")


def _is_block_start(line):
    """A list item or a blockquote line -- both need a blank line before them."""
    return bool(_LIST_ITEM_RE.match(line)) or line.lstrip().startswith(">")


def fix_block_blank_lines(text):
    """Ensure a blank line precedes a list or blockquote that directly follows a
    paragraph.

    Colab/Jupyter render these even with no blank line before them; Pandoc does
    not -- it folds `- item` / `> quote` lines into the preceding paragraph
    (lists become literal dashes, blockquotes stop indenting). We insert the
    missing blank line, but must NOT touch lines inside `$$...$$` display math
    (e.g. a `1.`/`2.`/`3.` enumerated derivation), so we track math state and
    skip it. Run this AFTER lone-$ -> $$ conversion."""
    out = []
    in_math = False
    for line in text.split("\n"):
        if (not in_math) and _is_block_start(line) and out:
            prev = out[-1]
            if prev.strip() and not _is_block_start(prev):
                out.append("")
        out.append(line)
        if line.count("$$") % 2 == 1:
            in_math = not in_math
    return "\n".join(out)


def colorize_note_blockquotes(text):
    """Color each paragraph of a note blockquote independently.

    The Colab notes open `<font color=C>` on some blockquote paragraphs but not
    all (and close across paragraph boundaries), which can't work in HTML -- a
    `<span>` can't stay open across the `<p>` boundaries Pandoc creates for each
    blockquote paragraph, so trailing paragraphs render uncolored. For any
    blockquote run that uses a `<font color>`, we strip the original font tags
    and wrap every non-empty quoted line in its own `<span style="color:C">`."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith(">"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                j += 1
            run = lines[i:j]
            m = FONT_COLOR_RE.search("\n".join(run))
            if m:
                color = m.group(1)
                for line in run:
                    bare = re.sub(r"</?font[^>]*>", "", line, flags=re.I)
                    mm = re.match(r"^(\s*>+\s?)(.*)$", bare)
                    if mm and mm.group(2).strip():
                        out.append('%s<span style="color:%s">%s</span>'
                                   % (mm.group(1), color, mm.group(2)))
                    else:
                        out.append(bare)
                # a note's closing </font> is sometimes on its own line *outside*
                # the blockquote; consume it so it doesn't leak as a stray tag
                if j < len(lines) and re.match(r"^\s*</font>\s*$", lines[j], re.I):
                    j += 1
            else:
                out.extend(run)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Transform: deprecated <font> tags
# --------------------------------------------------------------------------- #
FONT_OPEN_RE = re.compile(r"<font\b[^>]*>", re.I)
FONT_CLOSE_RE = re.compile(r"</font\s*>", re.I)
FONT_COLOR_RE = re.compile(r'<font\s+color=["\']?([^"\'>\s]+)["\']?\s*>', re.I)


def fix_font_tags(text):
    """Convert deprecated `<font color=C>` notes to `<span style="color:C">`
    and balance each cell.

    The Colab notes re-open `<font>` on every blockquote paragraph but close
    it only once, leaving unclosed tags. An unclosed raw-HTML tag leaks in
    Pandoc and corrupts the document structure after it (swallowing later
    sections into a heading). Counting the font tags *before* conversion lets
    us append exactly the missing number of `</span>` closes so every cell is
    self-balanced.
    """
    deficit = len(FONT_OPEN_RE.findall(text)) - len(FONT_CLOSE_RE.findall(text))
    text = FONT_COLOR_RE.sub(r'<span style="color:\1">', text)
    # any remaining <font ...> without a recognized color attr -> plain span
    text = FONT_OPEN_RE.sub("<span>", text)
    text = FONT_CLOSE_RE.sub("</span>", text)
    if deficit > 0:
        text = text.rstrip() + "</span>" * deficit
    return text


# --------------------------------------------------------------------------- #
# Transform: images
# --------------------------------------------------------------------------- #
def raw_url(github_url):
    """Convert a github.com blob URL (?raw=true) to a raw.githubusercontent URL."""
    u = github_url.split("?")[0]
    u = u.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return u


def download_diagrams(cells):
    """Find every <img src> pointing at the Tutorials repo, download it into
    images/diagrams/, and return a {original_src: relative_path} map."""
    srcs = []
    for c in cells:
        for m in re.findall(r'<img[^>]+src="([^"]+)"', as_text(c["source"])):
            if "apetulante/Tutorials" in m and m not in srcs:
                srcs.append(m)

    dest_dir = os.path.join(POST_DIR, DIAGRAM_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)

    mapping = {}
    for src in srcs:
        name = raw_url(src).rsplit("/", 1)[-1]
        dest = os.path.join(dest_dir, name)
        rel = os.path.join(DIAGRAM_SUBDIR, name).replace(os.sep, "/")
        mapping[src] = rel
        if os.path.exists(dest):
            print("  image present, skipping download: %s" % rel)
            continue
        print("  downloading %s" % name)
        urllib.request.urlretrieve(raw_url(src), dest)
    return mapping


def rewrite_img_srcs(text, mapping):
    for original, rel in mapping.items():
        text = text.replace(original, rel)
    return text


# --------------------------------------------------------------------------- #
# Transform: scrollTo links + anchors
# --------------------------------------------------------------------------- #
SCROLLTO_RE = re.compile(r"#scrollTo=([A-Za-z0-9_\-]+)[^)\"'\s]*")


def collect_scrollto_targets(cells):
    """Return the set of scrollTo target ids referenced anywhere."""
    ids = set()
    for c in cells:
        for m in SCROLLTO_RE.findall(as_text(c["source"])):
            ids.add(m)
    return ids


def rewrite_scrollto_links(text):
    """`...#scrollTo=ID&junk...` -> `#ID` in both markdown links and href=."""
    text = re.sub(r'href="[^"]*#scrollTo=([A-Za-z0-9_\-]+)[^"]*"',
                  r'href="#\1"', text)
    text = re.sub(r"\(\s*[^)\s]*#scrollTo=([A-Za-z0-9_\-]+)[^)]*\)",
                  r"(#\1)", text)
    return text


LEADING_ANCHOR_RE = re.compile(
    r'^\s*<a\s+id=["\']#?[\w\-]+["\']\s*>\s*</a>\s*\n+', re.I)


def install_heading_anchor(text, anchor):
    """Append `{#anchor}` to the first heading line (idempotent).

    Colab sometimes puts a bare `<a id="#A1"></a>` anchor line immediately
    above a heading with no blank line between them, which stops Pandoc from
    parsing the heading. Drop that stray anchor and rely on the `{#anchor}`
    heading attribute instead."""
    text = LEADING_ANCHOR_RE.sub("", text)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.match(r"\s*#{1,6}\s", line):
            if ("{#%s}" % anchor) in line:
                return text
            lines[i] = line.rstrip() + " {#%s}" % anchor
            break
    return "\n".join(lines)


def install_prose_anchor(text, anchor):
    """Ensure a leading `<a id="anchor"></a>`.

    If the cell already opens with an <a id=...> anchor (possibly the malformed
    Colab `id="#A1"` form), rewrite that anchor's id; otherwise prepend one.
    """
    lead = re.match(r'(\s*)<a\s+id=["\']#?[\w\-]+["\']\s*>\s*</a>', text)
    if lead:
        return re.sub(r'<a\s+id=["\']#?[\w\-]+["\']\s*>\s*</a>',
                      '<a id="%s"></a>' % anchor, text, count=1)
    return '<a id="%s"></a>\n\n%s' % (anchor, text)


# --------------------------------------------------------------------------- #
# Transform: ipywidgets
# --------------------------------------------------------------------------- #
def strip_widget_outputs(cell):
    """Drop widget-view outputs from a code cell. Return True if any removed."""
    if cell["cell_type"] != "code":
        return False
    changed = False
    kept = []
    for out in cell.get("outputs", []):
        data = out.get("data", {})
        if WIDGET_MIME in data or WIDGET_STATE_MIME in data:
            changed = True
            data.pop(WIDGET_MIME, None)
            data.pop(WIDGET_STATE_MIME, None)
            # keep the output only if some other, renderable mime remains
            leftover = {k: v for k, v in data.items() if k != "text/plain"}
            if leftover:
                out["data"] = data
                kept.append(out)
            # else: drop entirely (text/plain is just the widget repr)
        else:
            kept.append(out)
    cell["outputs"] = kept
    return changed


def widget_note_cell(cell_id):
    shot_rel = os.path.join(WIDGET_SHOT_SUBDIR, "%s.png" % cell_id).replace(os.sep, "/")
    shot_abs = os.path.join(POST_DIR, shot_rel)
    note = ("> ▶ **Interactive in the [Colab version](%s).** The control "
            "above is a live `ipywidgets` slider; on this static page there is "
            "no kernel to recompute it, so open the notebook in Colab to drag "
            "the sliders yourself." % COLAB_URL)
    if os.path.exists(shot_abs):
        note = "![](%s)\n\n%s" % (shot_rel, note)
    return md_cell(note)


# --------------------------------------------------------------------------- #
# Transform: pip install
# --------------------------------------------------------------------------- #
def hide_pip_cell(cell):
    if cell["cell_type"] != "code":
        return
    text = as_text(cell["source"])
    if "!pip install" in text and "#| include:" not in text:
        cell["source"] = "#| include: false\n" + text


# --------------------------------------------------------------------------- #
# Metadata cleanup
# --------------------------------------------------------------------------- #
def clean_cell_metadata(cell):
    meta = cell.get("metadata", {})
    for k in CELL_META_DROP:
        meta.pop(k, None)
    cell["metadata"] = meta


# --------------------------------------------------------------------------- #
# Main build
# --------------------------------------------------------------------------- #
def build(source_path):
    with open(source_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    cells = nb["cells"]

    # Resolve scrollTo targets via metadata.id BEFORE stripping metadata.
    id2cell = {}
    for c in cells:
        cid = c.get("metadata", {}).get("id")
        if cid:
            id2cell[cid] = c

    target_ids = collect_scrollto_targets(cells)
    # Which cells are anchor targets, and what action each needs.
    heading_targets = {}   # cell id(obj) -> anchor   (append {#anchor})
    prose_targets = {}     # cell id(obj) -> anchor   (leading <a id>)
    code_targets = {}      # id(obj) of code cell -> anchor (insert cell before)
    unresolved = []
    for tid in sorted(target_ids):
        tgt = id2cell.get(tid)
        if tgt is None:
            unresolved.append(tid)
            continue
        text = as_text(tgt["source"])
        # a heading may sit directly behind a bare Colab anchor line; look past it
        unanchored = LEADING_ANCHOR_RE.sub("", text)
        if tgt["cell_type"] == "markdown" and is_heading(unanchored):
            heading_targets[id(tgt)] = tid
        elif tgt["cell_type"] == "markdown":
            prose_targets[id(tgt)] = tid
        else:  # code (or raw)
            code_targets[id(tgt)] = tid
    if unresolved:
        print("  WARNING: unresolved scrollTo targets: %s" % unresolved)

    # Download diagrams and build the src->relpath map.
    print("Diagrams:")
    img_map = download_diagrams(cells)

    # Rebuild the cell list, applying per-cell transforms.
    out_cells = []
    badge_inserted = False
    for c in cells:
        clean_cell_metadata(c)

        # Insert an anchor cell before a code-cell scrollTo target.
        if id(c) in code_targets:
            out_cells.append(md_cell('<a id="%s"></a>' % code_targets[id(c)]))

        if c["cell_type"] == "markdown":
            text = as_text(c["source"])
            text = fix_lone_dollar_math(text)
            text = fix_backslash_math(text)
            text = escape_text_underscores(text)
            text = fix_block_blank_lines(text)
            text = colorize_note_blockquotes(text)
            text = fix_font_tags(text)
            text = rewrite_scrollto_links(text)
            text = rewrite_img_srcs(text, img_map)
            if id(c) in heading_targets:
                text = install_heading_anchor(text, heading_targets[id(c)])
            if id(c) in prose_targets:
                text = install_prose_anchor(text, prose_targets[id(c)])
            c["source"] = text
            out_cells.append(c)

            # After the first H1, drop in the Colab badge.
            if not badge_inserted and re.match(r"\s*#\s", first_nonblank_line(text)):
                out_cells.append(md_cell(BADGE))
                badge_inserted = True

        elif c["cell_type"] == "code":
            hide_pip_cell(c)
            had_widget = strip_widget_outputs(c)
            out_cells.append(c)
            if had_widget:
                out_cells.append(widget_note_cell(c.get("metadata", {}).get("id", "widget")))
        else:
            out_cells.append(c)

    if not badge_inserted:  # no H1 found; put badge right after front matter
        out_cells.insert(0, md_cell(BADGE))

    # Prepend the front matter raw cell.
    out_cells.insert(0, raw_cell(FRONT_MATTER))

    # Notebook-level metadata cleanup.
    for k in NB_META_DROP:
        nb.get("metadata", {}).pop(k, None)

    # Normalize every cell's source to the list-of-lines form (see as_lines).
    for c in out_cells:
        c["source"] = as_lines(as_text(c["source"]))
    nb["cells"] = out_cells

    os.makedirs(POST_DIR, exist_ok=True)
    with open(OUT_NB, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")

    print("\nWrote %s (%d cells)" % (os.path.relpath(OUT_NB, REPO_ROOT), len(out_cells)))
    print("Anchors installed: %d heading, %d prose, %d code-cell"
          % (len(heading_targets), len(prose_targets), len(code_targets)))


def main(argv):
    source = os.path.expanduser(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    if not os.path.exists(source):
        sys.exit("source notebook not found: %s" % source)
    if os.path.abspath(source) == os.path.abspath(OUT_NB):
        sys.exit("refusing to run: source and output are the same file")
    print("Source: %s" % source)
    build(source)


if __name__ == "__main__":
    main(sys.argv)
