# FHRS Python

Load and validate FHRS dataset manifests from local files or fsspec URLs.
Requires Python 3.14 or newer.

```sh
uv sync
```

Install optional DataFrame libraries with `uv sync --extra pandas` or
`uv sync --extra polars`, or both with `uv sync --extra pandas --extra polars`.
For pip, use `pip install "fhrs-py[pandas,polars]"`. The pandas extra includes
`openpyxl` for Excel workbooks; the polars extra includes `fastexcel`. Both
include `pyarrow`.

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

To construct runtime objects with dataset and parent links:

```python
from fhrs import runtime

dataset = runtime.load("examples/manifest-pointers")
wave = dataset.collection("waves").collection("1403")
print(wave.title)
```

Resources bind `sources` during initialization in declared location order,
without accessing resource contents:

```python
dataset = runtime.load("examples/basic")
for source in dataset.resource("data").sources:
    print(source.urlpath)
    print(source.to_fsspec())
```

Directory resource manifests may declare `members`, mapping nonempty names to nonempty
glob strings. File resources must omit `members`, including an empty mapping.
Omission defaults to an empty dictionary; declarations are stored
without accessing files or expanding patterns:

```yaml
resources:
  extracted:
    type: directory
    locations:
      - uri: data/1403/
    members:
      households: "[UR]1403P3S01.csv"
      all_csv: "**/*.csv"
```

Runtime resources expose a read-only `members` mapping and `member(name)` lookup.
Each `ResourceMember` carries its `name`, `pattern`, parent `resource`, and ordered
`sources`, with one pattern address per directory mirror. Construction does not
access files. `member.source(name)` uses the resource's location-name-first,
storage-name-second lookup:

```python
member = resource.member("households")
for source in member.source("local").glob():
    with source.open() as stream:
        ...  # Read each matched file.
```

Patterns resolve inside the directory with or without a trailing slash. Runtime
binding rejects absolute paths, parent (`..`) segments, schemes, and backslashes.
Use forward slashes in patterns. Expand one mirror at a time with `Source.glob()`;
matching files from different mirrors are alternatives, not additional partitions.
Missing member or source names raise `KeyError`; file resources have no members.

`resource.member()` also accepts `member:pattern` to create a temporary inline
member. Its name is the pattern itself; it is not added to `resource.members` or
the manifest. The `member:` prefix is reserved for inline patterns. Unknown
unprefixed names still raise `KeyError`.

```python
declared = resource.member("household_size")
inline = resource.member("member:*.csv")
exact = resource.member("member:nested/01.csv")
```

These selectors represent the part after `#` in addresses such as
`raw_csv#household_size` and `raw_csv#member:*.csv`. Full resource/collection
address resolution is not implemented yet. Inline members use the same directory
path checks and mirror selection as declared members; files are listed only when
calling `inline.source("local").glob()`.

Use `member.files()` to return a sorted tuple of matching file `Source` objects
from the first declared mirror, or `member.files(source="local")` to select a
location/storage by name. It refreshes matches on each call, returns `()` when
none match, and propagates filesystem errors. It does not combine mirrors or
automatically fall back to another one. Works for declared and inline members:

```python
for source in resource.member("household_size").files(source="embedded"):
    with source.open() as stream:
        ...
```

A table's `resource` accepts one resource name or a nonempty ordered list:

```yaml
tables:
  households:
    resource: [urban, rural]
    reader: csv
```

Runtime `table.resources` is always a list of bound `Resource` objects, in declared
order; a single name produces a one-element list. Every name must exist in the
table's owning node.

Tables can declare `reader: excel` for Excel workbook resources, alongside
`csv` and `parquet`. `Table.load()` currently defines typed pandas/polars outputs
and reader options; its implementation remains a stub.

Each source exposes `filesystem` and its backend `path`. They are initialized
together on first access and cached for reuse. `source.exists()` uses this pair
and checks existence anew on every call.
Use `source.open()` for a binary stream, or pass a mode and reader options:

```python
with source.open("rt", encoding="utf-8") as stream:
    text = stream.read()
```


Use `source.glob()` to expand an address containing a filesystem glob such as
`[UR]1403*.csv`. It returns a tuple of file sources sorted by path, preserving
connection options. No matches returns an empty tuple; expansion happens only
when called and requires a backend that supports file listing. `open()` opens
one file without expanding patterns. Locations remain alternative mirrors;
files matched by one pattern are read separately.

```python
from fhrs.runtime import Source

pattern = Source("data/1403/[UR]1403P3S01.csv")
for matched in pattern.glob():
    with matched.open() as stream:
        ...  # Read this file with pandas or polars.
```

`resource.source("name")` returns the source matching a location name first,
then a storage name. Each search uses declared order; no match raises `KeyError`.

File resources may declare optional `size`: a nonnegative integer giving the
complete file size in bytes, available as `resource.size` (`None` if omitted).
It applies to every mirror and is forbidden for directories. Different sizes
prove different contents; equal sizes still require a checksum comparison.

Embedded storage describes data shipped with the code itself.
An unqualified resource path resolves beside the dataset manifest, including
resources in child collections. Named `embedded` storage resolves its base
from the dataset manifest, using the
same filesystem and connection options. For a GitHub manifest, `embedded` means
the same repository and revision. HTTP and S3 storage declarations use their
own configured backends. Resolved locations retain the options required by
`fsspec.open()`.

Metadata fields (`name`, `title`, and `description`) are declared directly on
datasets and collections. Only datasets accept `fhrs_version`, which defaults
to `"0.1"`; internal collections omit it. Named embedded,
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
