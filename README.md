# FHRS Python

Load and validate FHRS dataset manifests from local files or fsspec URLs.
Requires Python 3.14 or newer.

```sh
uv sync
```

```python
from fhrs.manifest import load

dataset = load("examples/manifest-pointers")
wave = dataset.collections["waves"].collections["1403"]
print(wave.title)
```

`load()` accepts a manifest file or a directory containing an FHRS entry point.
It recursively loads collection pointers relative to their declaring files,
rejects circular references, and permits shared manifests across branches.
Pass backend connection settings using `storage_options`.

Metadata fields (`name`, `title`, and `description`) are declared directly on
datasets and collections. `fhrs_version` defaults to `"0.1"`. Named local,
HTTP(S), and S3 storage declarations map their options to fsspec; install the
`s3` extra to use the S3 backend.

See [the examples](examples/README.md) for layouts, storage declarations, and
manifest pointers.

Run checks with:

```sh
uv run python -m unittest discover -s tests
uv run ruff check src/fhrs/manifest tests
uv run ruff format --check src/fhrs/manifest tests
```
