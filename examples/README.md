# Manifest examples

Standalone manifests are named `fhrs.yaml` or `.fhrs.yaml`. Manifests may also
live in a `fhrs/` or `.fhrs/` directory; these examples use `manifest.yaml` as the
entry file inside either directory.

- `basic/fhrs.yaml`: a standalone dataset with a local CSV resource and table.
- `s3/.fhrs.yaml`: a standalone dataset with an S3 storage declaration. Its endpoint and bucket are
  illustrative; no remote data is bundled.
- `collections/fhrs/manifest.yaml`: a dataset in a `fhrs/` directory, with inline and
  file-referenced collections. The referenced collection is defined in
  `collections/waves/1403/.fhrs.yaml`.
- `hidden-directory/.fhrs/manifest.yaml`: a dataset in a `.fhrs/` directory, sharing
  the basic example's CSV file.
- `manifest-pointers/fhrs.yaml`: nested YAML/JSON manifest pointers with a shared
  child file, plus a deliberately circular example. See
  [the example README](manifest-pointers/README.md).

Local resource locations and manifest references are relative to their defining
manifest file. Storage declarations belong to the root dataset. `load()` accepts
an explicit manifest file or discovers the entry file in a directory, then
recursively loads referenced collections:

```python
from fhrs.manifest import load

dataset = load("examples/collections/fhrs/manifest.yaml")
dataset = load("examples/manifest-pointers")
wave = dataset.collections["waves"].collections["1403"]
```

The loader accepts fsspec URLs and optional `storage_options`. Files ending
in `.json` are parsed as JSON; YAML files use the YAML parser. Circular manifest
references are rejected; references shared by separate branches are allowed.

Named local and HTTP storage declarations use fsspec protocol names and options:

```yaml
storages:
  local:
    type: local
    protocol: file
    path: ../data/
  web:
    type: http
    protocol: https
    url: https://example.org/data/
    storage_options:
      block_size: 0
```

`base_path` and `base_url` are accepted as input aliases for `path` and `url`.
These bases describe resource locations; only `storage_options` and `protocol`
are passed to the fsspec filesystem constructor. Dataset and collection
declarations accept `fhrs_version: "0.1"`, which is also the default.
