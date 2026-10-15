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

Runtime `table.resources` is always a list of bound `Resource` or `ResourceMember`
objects, in declared order; a single reference produces a one-element list.
Resource names resolve in the table's owning node. Append `#name` to select a
declared member or `#member:pattern` to create an inline member:

```yaml
tables:
  household_size:
    resource: raw_csv#household_size
    reader: csv
  combined:
    resource: [standalone_csv, "raw_csv#member:parts/*.csv"]
    reader: csv
```

`dataset.resource()` and `collection.resource()` accept these same local
references. Missing declared members raise `KeyError` during runtime binding;
inline patterns use the member path checks. Binding does not list or open files.
The table's `dataset` and `parent` refer to the owning dataset/collection even
when its first resource is a member.

`Table.load()` selects the reader from `fhrs.runtime.readers.READERS` using the
manifest's `reader` value. CSV is currently registered; `parquet` and `excel`
can be declared but require reader implementations before loading.

```python
frame = table.load()  # pandas
frame = table.load(backend="polars", source="embedded")
```

`dataset.table("waves/1403/01")` is equivalent to
`dataset.collection("waves").collection("1403").table("01")`.
Table paths resolve relative to the dataset or collection where lookup starts.
Resource lookup supports the same collection paths, followed by an optional
member selector, such as `dataset.resource("waves/1403/raw_csv#household_size")`
or `dataset.resource("waves/1403/raw_csv#member:nested/*.csv")`. Slashes after
`#` belong to the member selector and are not traversed as collections.
Missing path components raise `KeyError`; traversing an unresolved manifest
reference raises `TypeError` (use `runtime.load()` to resolve manifests first).

Table references are read in declared order and concatenated using the chosen
backend. Source selection and reader options are forwarded to each reference.
The default selects each resource's first mirror. Unknown readers or backends
raise `ValueError`. Add a reader instance with `READERS["format"] = MyReader()`;
custom readers implement `BaseReader.read_pandas()` and `read_polars()`.

The CSV reader can be used directly:

```python
from fhrs.runtime.readers import CSVReader

reader = CSVReader()
frame = reader.read_pandas(resource.member("household_size"), source="embedded")
frame = reader.read_polars(resource.member("member:parts/*.csv"))
```

It accepts file resources and members, reads the first mirror by default, and
concatenates member files in sorted path order. Bare directory resources require
a member selecting the files; empty matches raise `FileNotFoundError`. Reader
options are forwarded to the chosen backend (`sep` for pandas, `separator` for
Polars, for example). pandas chunk/iterator output is unsupported. Multiple
pandas frames are concatenated with a fresh row index; Polars uses its default
vertical concatenation and schema checks. Each backend is imported only when
its read method is called.

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
