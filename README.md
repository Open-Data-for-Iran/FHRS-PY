# FHRS Python

Load and validate FHRS dataset manifests from local files or fsspec URLs.
Requires Python 3.13 or newer.

```sh
uv sync
```

Install optional DataFrame libraries with `uv sync --extra pandas` or
`uv sync --extra polars`, or both with `uv sync --extra pandas --extra polars`.
For pip, use `pip install "fhrs-py[pandas,polars]"`. The pandas extra includes
`openpyxl` for Excel workbooks; the polars extra includes `fastexcel`. Both
include `pyarrow`.

```python
import fhrs
from pathlib import Path

dataset = fhrs.load("sci_dataset_list")
dataset = fhrs.load(Path(".fhrs"))
dataset = fhrs.load("./.fhrs")
dataset = fhrs.load("https://example.org/manifest.yaml")
```

`fhrs.load(source)` returns a runtime dataset from a package, manifest path, or
URL. `PathLike` objects always select manifest loading. Strings containing `/`,
`\`, or `:`, ending in `.yaml`, `.yml`, or `.json` (case insensitive), or equal to
`.`, `..`, or `.fhrs` also select manifest loading. Other strings select package
loading. Pass `Path("dataset")` to load a bare directory name unambiguously.
Errors propagate from the selected loader; loading never falls back to another
interpretation. `storage_options=` configures manifest access and is accepted
only for paths and URLs. `working_directory=` applies to both kinds of source.

Pass `manage=True` to select managed runtime subclasses:

```python
dataset = fhrs.load("sci_dataset_list", manage=True)
```

This returns `fhrs.runtime.ManagedDataset`, with managed collections, resources,
resource members, tables, and storages, including working storage. Each managed
class inherits its ordinary runtime counterpart. Sources remain ordinary
runtime addresses. Loading performs no maintenance
actions. The default `manage=False` keeps ordinary runtime types. Both
`fhrs.runtime.load_manifest()` and `fhrs.runtime.load_package()` accept the flag.

Use `ManagedResource.put()` to place file or directory contents in working storage:

```python
resource = dataset.resource("report")
path = resource.put("download.csv")
path = resource.put(b"id,value\n1,10\n", overwrite=True)
directory = dataset.resource("parts").put("downloaded_parts")
```

Inputs may be a local path, bytes, or an open binary stream (including
`io.BytesIO`). Streams are read from their current position and left open.
The destination uses the resource's dataset-relative key and declared suffix,
under `working_directory`; parent directories are created as needed. It returns
the destination `Path`. Existing files require `overwrite=True`. Writes are
staged in a temporary file before publication, and failed copies leave any
existing destination intact. Directory resources accept local directory paths
only. Their contents, including nested and empty directories, are copied directly
into the resource's working directory. `overwrite=True` replaces the entire
directory, removing stale contents. Directory replacement is not atomic: it uses
a temporary backup and restores the original if publication fails. If restoration
also fails, the backup is retained and its path is reported in the error.
Read-only backup files are made writable before deletion. If cleanup still
fails after a successful replacement, `.put()` returns the destination and emits
a `RuntimeWarning` with the retained temporary directory's path.
The method does not change manifest locations, size, or checksums. The name
`working` is reserved for runtime storage and cannot be declared as a storage
name or a location name.


Use `ManagedResource.add(path, data, *, overwrite=False)` to write one file inside
an existing or new directory resource in working storage:

```python
pages = dataset.resource("dataset_pages")
path = pages.add("20797.html", response.content)
path = pages.add("nested/20798.html", "downloaded_page.html", overwrite=True)
```

`add()` works only on directory resources; file resources raise `TypeError`.
The destination path uses forward slashes and must identify a file inside the
resource. Absolute paths, traversal, glob patterns, and symlinks escaping the
resource are rejected. Parent directories are created automatically. Inputs,
stream ownership, staged writes, return values, and explicit overwrite behavior
match file `put()`. Other files and the manifest are preserved.


Use `ManagedResource.remove(path)` to remove a single file from a directory
resource's working storage:

```python
pages.remove("20797.html")
```

`remove()` uses the same path restrictions as `add()` and works only on directory
resources. It returns `None`, raises `FileNotFoundError` for missing files, and
rejects directories with `IsADirectoryError`. Other files, parent directories,
and the manifest are preserved. An internal file symlink is unlinked without
removing its target; links escaping the resource are rejected.

For package names, this imports `<package_name>.fhrs_setup.dataset` from an
installed or otherwise importable Python package and returns a runtime dataset.
The declaration must be a `fhrs.manifest.models.Dataset`. Hyphens in package names are
accepted as underscores, so `sci-dataset-list` works too. Relative resource paths,
embedded storage, and collection manifest references resolve beside
`fhrs_setup.py`. Loading copies the declaration, leaving the package's dataset
object unchanged. Pass `working_directory=` to choose the local working folder.
As with any Python import, loading executes the package's setup module.

Package loading is also available as `fhrs.runtime.load_package()` (defined
in `fhrs.runtime.loader`). Both functions accept `setup_module="fhrs_setup"` to
choose the module relative to the package:

```python
dataset = fhrs.load("sci_dataset_list", setup_module="custom_setup")
# Equivalent:
dataset = fhrs.runtime.load_package(
    "sci_dataset_list", setup_module="custom_setup"
)
```

Use `fhrs.manifest.load()` for manifest declarations and `fhrs.runtime.load_manifest()`
for runtime datasets loaded from manifest paths or URLs:

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

Write manifest declarations with `dump()`:

```python
from fhrs.manifest import dump

dump(dataset)  # ./manifest.yaml, with all collections inline
dump(dataset, destination=".fhrs", format="json")  # .fhrs/manifest.json
dump(
    dataset,
    destination=".fhrs",
    layout={
        f"waves/{year}": f"waves/{year}.yaml"
        for year in dataset.collections["waves"].collections
    },
)
```

`destination` is a local or fsspec directory; remote connection settings use
`storage_options`. `layout` maps dataset-relative collection keys to filenames
relative to that directory. Unselected collections remain inline. Selected
collections are replaced with references relative to their containing file,
including when both a collection and its descendants are split out. Linked
filenames must stay inside the destination and use the selected YAML or JSON
format. Unknown collection keys and conflicting filenames fail before writing.

YAML and JSON dumps use the field order defined by the FHRS manifest models,
including nested objects and linked collections. The order of named entries in
resource, table, storage, and collection mappings is preserved.
Dataset roots use this explicit order: `fhrs_version`, `name`, `title`,
`description`, `schema_version`, `release`, `storages`, `resources`, `tables`,
`collections`. Optional fields whose value is `None` are omitted.

Pass a manifest `Dataset`, or `dataset.manifest` for a runtime dataset. Resolve
manifest references with `load()` before dumping. The dumper overwrites target
files and leaves the input unchanged. It serializes declarations only: resource
files are not copied, resource/storage paths are not rebased, and original YAML
comments and formatting are not preserved. When dumping elsewhere, review relative
storage paths. Load a root `manifest.yaml` by its file path unless its directory
is named `fhrs` or `.fhrs`, which supports directory discovery.

A dataset manifest can carry defaults for dumping:

```yaml
dump_options:
  destination: .fhrs
  format: yaml
  layout:
    waves/1403: waves/1403.yaml
```

These options are accepted when loading or constructing a manifest but excluded
from serialization, including `model_dump()` and written manifests. Both
`manifest.dump(dataset)` and runtime `dataset.dump()` use them. Explicit non-`None`
arguments override the stored defaults; pass `layout={}` for flat output or
`storage_options={}` to clear stored connection settings. Without stored options,
dumping still defaults to flat YAML in the current directory.

To construct runtime objects with dataset and parent links:

```python
from fhrs import runtime

dataset = runtime.load_manifest("examples/manifest-pointers")
wave = dataset.collection("waves").collection("1403")
print(wave.title)
```

Runtime datasets expose the same manifest dumper through `dataset.dump()`:

```python
dataset.dump()  # ./manifest.yaml
dataset.dump(".fhrs", format="json")
dataset.dump(".fhrs", layout={"waves/1403": "waves/1403.yaml"})
```

The method accepts the same `destination`, `format`, `layout`, and
`storage_options` arguments as `fhrs.manifest.dump()`.

Resources bind `sources` during initialization in declared location order,
without accessing resource contents:

```python
dataset = runtime.load_manifest("examples/basic")
for source in dataset.resource("data").sources:
    print(source.urlpath)
    print(source.to_fsspec())
```

`resource.source()` selects the first declared location. If no locations are
declared, it selects the local `working` source. Table `.load()` and directory
member `.files()` follow the same rule. This does not check whether files exist:
a missing selected source raises its normal read error rather than trying another
source. Working paths are not added to manifest locations or `.sources`.

Every runtime resource also supports an explicitly selected `working` source:

```python
dataset = runtime.load_manifest("examples/basic", working_directory="local-data")
local = dataset.resource("data").source("working")
working = dataset.storage("working")  # Also available in dataset.storages.
local = working.resolve("data")
```

`resource.working_path` is a convenience property returning the local working
address as a `pathlib.Path`, for both ordinary and managed resources:

```python
path = dataset.resource("data").working_path
```

It works for files and directories, includes the declared file suffix and nested
collection path, and always selects working storage even when the resource has
remote locations. Access does not open resource contents or create anything;
working-storage path checks still apply.

The working directory defaults to `data/<dataset.name>` under the current
directory. Dataset initialization replaces `<dataset.name>` with the manifest's
name in any supplied path and resolves it to an absolute path.
Dataset and collection names use 1–64 lowercase ASCII letters, digits,
underscores, or hyphens. Surrounding whitespace is stripped. Uppercase input,
dots, and Unicode names are rejected; use `title` for display text.
Dataset names are required; collection names may be omitted or `None`.
An explicit `working_directory` overrides this entire path; it can also be passed
to `runtime.Dataset(..., working_directory=...)`. Local resource paths use
`resource.key + (resource.suffix or "")` beneath that directory. Directories
support the same selection through `member.source("working")` and
`member.files(source="working")`. Selecting a working source creates no files
or directories. It is excluded from `sources` and manifest dumps, so default
reads use the first declared location, or working storage when no locations are declared. The storage name and location name `working`
are reserved and rejected during manifest validation. Use `working_directory`
to configure the generated local storage.

Directory resource manifests may declare `members`, mapping nonempty names to nonempty
glob strings. Manifest `members` defaults to `None`, meaning no declaration;
`None` is omitted when writing manifests. An explicit empty mapping is preserved
for directories. File resources reject any non-`None` value, including an empty
mapping. Declarations are stored without accessing files or expanding patterns:

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
When the manifest declares no members, the runtime mapping is empty.
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
from the first declared mirror (or working storage if none are declared),
or `member.files(source="local")` to select a
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
manifest's `reader` value. CSV and Parquet readers are registered. Excel
can be declared but requires a reader implementation before loading.

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
Each resource exposes `key`, its dataset-relative lookup path, such as
`waves/1403/raw_csv`. It uses collection and resource mapping keys, independently
of storage locations and manifest display names. Root resource keys contain
only the resource name; `dataset.resource(resource.key)` returns that resource.
Missing path components raise `KeyError`. Runtime collections always contain
runtime `Collection` objects. Direct runtime construction rejects unresolved
manifest references with `TypeError`, including references in nested collections.
Use `fhrs.load()` or `runtime.load_manifest()` to load and resolve references
before runtime binding, or pass declarations from `fhrs.manifest.load()` to a
runtime constructor.

Table references are read in declared order and concatenated using the chosen
backend. Source selection and reader options are forwarded to each reference.
The default selects each resource's first declared mirror, or working storage
when no locations are declared. Unknown readers or backends
raise `ValueError`. Add a reader instance with `READERS["format"] = MyReader()`;
custom readers implement `BaseReader.read_pandas()` and `read_polars()`.

File resources with a declared `.csv` or `.parquet` suffix automatically get a
runtime table with the same name and matching reader. Suffix matching ignores
case and applies within nested collections, for ordinary and managed datasets.
Explicit tables override automatic tables with the same name. Directory resources,
compressed suffixes such as `.csv.gz`, and resources without a supported declared
suffix do not get automatic tables; filenames in locations are not inspected.
Automatic tables appear in `.tables` but are not added to saved manifests.
Binding tables performs no file access or column-schema inference.

```python
# resources={"rss_catalog": Resource(suffix=".csv")}
frame = dataset.table("rss_catalog").load(source="working")
```

The Parquet reader supports pandas and Polars, named sources, column selection
with `columns=[...]`, and directory members selecting Parquet files. Like CSV,
member files are read in sorted order and multiple resources are concatenated in
reference order. Bare directory resources require an explicit member selector.
Backend options are forwarded to `pandas.read_parquet` or `polars.read_parquet`.
Install the existing pandas or polars extra for the corresponding dependencies.
`ParquetReader` is also available from `fhrs.runtime.readers` for direct use.

The CSV reader can be used directly:

```python
from fhrs.runtime.readers import CSVReader

reader = CSVReader()
frame = reader.read_pandas(resource.member("household_size"), source="embedded")
frame = reader.read_polars(resource.member("member:parts/*.csv"))
```

It accepts file resources and members, uses the default source selection, and
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

Resources may omit `locations` or declare an empty list when only metadata is
available. They bind with no sources; reading a file or listing a member without
a source raises `ValueError`. Looking up an unknown named source raises `KeyError`.

File resources may also declare `suffix`, available as `resource.suffix`
(`None` if omitted). Include the leading dot, for example `.pdf` or `.tar.gz`.
Each dot-separated component contains letters, digits, underscores or hyphens;
paths and separators are rejected. Directories cannot declare a file suffix.
Use `resource.key + (resource.suffix or "")` to form a dataset-relative file
path. This declaration does not change source URLs or infer an extension from them.

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

Datasets also accept optional `schema_version` and `release` fields, exposed
on runtime datasets under the same names:

```python
declaration = fhrs.manifest.models.Dataset(
    name="survey", schema_version="2.3.1", release="2026-10-26.1"
)
dataset = fhrs.runtime.Dataset(declaration)
dataset.schema_version  # "2.3.1"
dataset.release         # "2026-10-26.1"
dataset.status          # "in_development" (default)
dataset.version         # "2.3.1@2026-10-26.1~dev"
```

Both are nonblank strings when provided and default to `None`. `schema_version`
identifies the data contract; `release` identifies the published data snapshot.
They are preserved when manifests are dumped and reloaded. They are independent
of `fhrs_version`; neither changes the Python package version. These fields
describe the loaded dataset; version selection uses the explicit catalog below,
without schema compatibility matching. Collections do not inherit these fields.

`version` is a Pydantic computed field on manifest datasets and a read-only
property on runtime datasets. It is derived from `schema_version`, `release`,
and `status`, and included in `model_dump()` and `model_dump_json()` output.
Saved manifests exclude computed fields so they can be loaded without supplying
read-only values. It is `None` if either version component is missing. The characters
`@` and `~` are reserved and cannot appear in either component.

With `status="published"`, the example version becomes `"2.3.1@2026-10-26.1"`.
A `~dev` suffix marks a mutable development reference: loading the same version
later may yield different contents. Published versions identify immutable
snapshots within a dataset; publishers must assign a new identifier when the
snapshot changes. FHRS does not enforce storage immutability.

Publishers should use semantic versioning for `schema_version`: major changes
break the data contract, minor changes add compatible features, and patch
changes make compatible corrections to the contract. Data-only updates change
`release`. Compatibility matching and semantic-version validation are not
implemented by these properties.

### Reading available versions

Ordinary loading reads the current dataset without opening version indexes or
historical manifests. To discover versions, combine inline entries and external
index files explicitly:

```python
from fhrs import manifest

index = manifest.load_versions("dataset/manifest.yaml")
list(index.root)  # Available version identifiers; target manifests are not opened.
fixed = manifest.load("dataset/manifest.yaml", version="1.0@001")
```

The main manifest declares entries and any number of index files:

```yaml
versions:
  entries:
    "1.0@001":
      manifest: releases/001/manifest.yaml
  indexes:
    - versions/main.yaml
    - versions/experimental.json
```

Each index file is a plain mapping of version identifiers to references, without
an `entries` or `versions` wrapper. Index paths resolve beside the main manifest;
relative version manifest paths resolve beside the file declaring the entry.
Version references can also supply a full URL and optional fsspec options:

```yaml
"1.0@002":
  manifest: s3://archive/releases/002/manifest.yaml
  storage_options:
    anon: true
```

An explicit `protocol` in `storage_options` makes `manifest` a direct backend
path rather than a path relative to the declaring file. Explicit options replace
inherited options, including when set to `{}`. Without explicit options, relative
references inherit the main manifest's connection options; full URLs and absolute
paths use their own default connection settings. Version references do not use
named dataset storages.

Discovery and selection both read all declared indexes and reject duplicate
identifiers, including identical entries. Missing indexes and invalid declarations
raise their original errors; unknown version identifiers raise `KeyError`.
Selection opens only the chosen version manifest and resolves its collections.
That manifest supplies its own resource locations and storages; its version
indexes remain unopened.

`fhrs.load()`, `runtime.load_manifest()`, and `runtime.load_package()` also accept
`version=`. Package version paths resolve beside the setup module. Working
directory and managed dataset options apply to the selected dataset as usual.

See [the examples](examples/README.md) for layouts, storage declarations, and
manifest pointers.

Run checks with:

```sh
uv run python -m unittest discover -s tests
uv run ruff check src/fhrs/manifest tests
uv run ruff format --check src/fhrs/manifest tests
```
