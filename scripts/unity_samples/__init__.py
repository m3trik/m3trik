"""The recipes ``sync_unity_samples.py`` exports unitytk's samples from: one module per feature.

A recipe is a plain module the workspace imports twice: here, for what the
Package Manager lists (:data:`NAME`, :data:`DESCRIPTION`), and in an owned
headless mayapy, where :func:`build` makes the sample's scene through the
producer's public API and exports it as a user does. It declares:

- ``NAME``: the sample's folder under ``Samples~/`` and its display name.
- ``DESCRIPTION``: one sentence, the Package Manager's Samples tab.
- ``RECORDS``: the scene records the feature reads (``("animation",)``): the
  sample is held to its recipe by these and the delivery's structure (takes,
  nodes, meshes), never by a record it does not read or the ``handoff``'s prose.
- ``build(out_dir) -> list``: run in a new, empty Maya scene; exports into
  *out_dir* and returns the names of the files it wrote. Imports Maya and
  mayatk inside, so the module imports anywhere.

A module whose name starts with ``_`` (``_images``: the one PNG writer) is a
helper the recipes import as ``unity_samples._images``, never a recipe.

Everything else in the sample's folder (the demo recipe in C#, its ``.meta``
files) is written by hand and kept; only the files :func:`build` returns are
generated.
"""
