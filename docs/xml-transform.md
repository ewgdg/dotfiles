# XML Transform Selectors

`scripts/xmlformat.py` powers the `xml_sort_attr_rm_nodes` and
`xml_retain_nodes` dotdrop transforms.

Use one selector argument, `--node-matchers`, for both modes:

- Without `--overlay-file`, the node matchers are stripped from the base XML file.
- With `--overlay-file`, the node matchers are retained from the overlay XML file.

```sh
python scripts/xmlformat.py repo.xml output.xml \
  --overlay-file live.xml \
  --node-matchers 'config/WindowGeometry,config/WindowState'
```

The first positional path is always the base file. In install mode that is the
repo XML. `--overlay-file` points at the live XML, and `--node-matchers`
describes which live nodes should be copied back onto the repo base.
