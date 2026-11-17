"""Compare peak process memory and runtime for two Parquet write patterns."""

import tempfile
from pathlib import Path

import delta_sharing
import pyarrow.parquet as pq

from common import arguments, measure, run

METHODS = ("incremental_write", "eager_write")


def write(args):
    snapshot = delta_sharing.SharingClient(args.profile).table(args.table).snapshot(
        limit=args.rows, version=args.version
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "result.parquet"
        if args.worker == "incremental_write":
            rows = 0
            with snapshot.to_record_batch_reader() as reader:
                with pq.ParquetWriter(path, reader.schema, compression="snappy") as writer:
                    for batch in reader:
                        writer.write_batch(batch)
                        rows += batch.num_rows
        else:
            result = snapshot.to_arrow()
            rows = result.num_rows
            pq.write_table(result, path, compression="snappy")
        assert pq.read_metadata(path).num_rows == rows
        return rows


if __name__ == "__main__":
    args = arguments()
    if args.worker:
        measure(args, write)
    else:
        run(args, Path(__file__), METHODS)
