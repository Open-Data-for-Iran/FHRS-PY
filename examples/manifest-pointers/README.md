# Manifest pointers

The root manifest contains an inline `waves` collection with pointers to two
yearly YAML manifests. Each yearly manifest points to the same JSON notes
manifest using a path relative to its own file:

```text
fhrs.yaml
└── waves (inline)
    ├── 1402 → waves/1402.yaml → ../shared/notes.json
    └── 1403 → waves/1403.yaml → ../shared/notes.json
```

Sharing the notes manifest across branches is allowed. Its README resource is
relative to `shared/notes.json`, so `../README.md` identifies this document.

From the FHRS-PY directory:

```python
from fhrs.manifest import load

dataset = load("examples/manifest-pointers")
wave = dataset.collections["waves"].collections["1403"]
print(wave.title)                       # Survey wave 1403
print(wave.collections["notes"].title)  # Shared survey notes
```

The `cycle/` directory is deliberately invalid: `fhrs.yaml` points to
`child.yaml`, which points back to `fhrs.yaml`. Loading it raises `ValueError`
with the loop's manifest paths:

```python
load("examples/manifest-pointers/cycle")
```

Run the example tests with:

```sh
python -m unittest discover -s tests -p test_manifest_pointer_example.py
```
