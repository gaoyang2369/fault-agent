# Telemetry query correctness notes

## Coarse SQL time filtering

`RealDataRepository` uses `create_time` only as a coarse, parameterized SQL
filter. The requested `observed_at` range is expanded by the configured
`REAL_DATA_CREATE_TIME_FILTER_BUFFER_SECONDS`, and normalized `observed_at`
is still used for the final exact range check in Python.

TODO-DOMAIN: confirm whether `create_time` is ingestion time, which timezone
applies to its timezone-naive values, and the bounded lag/drift relationship
between `create_time` and `observed_at`. Until confirmed, the configured
buffer is an operational query setting rather than an industrial or domain
threshold. Reaching the bounded scan limit is reported as incomplete data.

## Data-quality configuration

The nominal sampling interval, gap threshold, and completeness thresholds are
runtime configuration. They are not inferred from signal values and are not
device safety thresholds. Trend and duration analyses are gated by the
resulting structured `DataQualitySummary`.

## Duplicate source rows

Rows are deduplicated by `(device_name, inverter_name, observed_at)`. The row
with the latest `create_time` is retained; when `create_time` is equal, the
largest source `id` is retained. Discarded rows remain visible through source
record ids in `DUPLICATE_SOURCE_RECORD` warnings and the duplicate count.
