# Metaphi AI docs

The documentation at docs.metaphi.ai. One page per `.mdx` file; `docs.json` is the navigation and the look. Mintlify builds main on push.

```
npm i -g mint
mint dev
```

`harwell/` and the Harwell tab of `docs.json` are rendered from [harwell-project/harwell](https://github.com/harwell-project/harwell) `docs/` by `.github/workflows/sync-harwell.yml` (`scripts/sync_harwell.py`). Edit Harwell's pages there, never here.
