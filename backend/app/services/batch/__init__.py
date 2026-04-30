"""Batch upload services: persistence, manifest parsing, processing.

The public surface is intentionally narrow:

- ``storage`` exposes a single ``BatchStore`` class wrapping all DB I/O.
- ``manifest`` exposes ``parse_manifest`` returning validated rows.
- ``processor`` exposes ``process_application`` callable from BackgroundTasks.

See ``docs/tradeoffs.md`` "Batch upload" for the design decisions.
"""
