# Metaphi AI docs

The documentation at docs.metaphi.ai. One page per `.mdx` file; `docs.json` is the navigation and the look. Mintlify builds main on push.

```
npm i -g mint
mint dev
```

Product docs live in each product's repository beside its code. `sources.json` names them; `.github/workflows/sync-docs.yml` renders each into `<name>/` and its tab in `docs.json` (`scripts/sync_docs.py`). Edit those pages at their source, never here.
