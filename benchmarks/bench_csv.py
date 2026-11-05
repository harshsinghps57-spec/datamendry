"""Local synthetic benchmark. Results depend on CPU and disk; no SLA claim."""
from __future__ import annotations
import argparse
import sys
import hashlib
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamendry.engine import RepairOptions, export_csv_chunks, import_csv, simulate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.rows <= 10_000_000:
        parser.error('--rows must be between 1 and 10,000,000')
    with tempfile.TemporaryDirectory(prefix='datamendry-bench-') as directory:
        source = Path(directory) / 'input.csv'
        with source.open('w', encoding='utf-8', newline='') as f:
            f.write('id,region,amount,note\n')
            for i in range(args.rows):
                f.write(f'{i:08d},zone{i % 30},{i % 1000}, remark{i % 9} \n')
        db = Path(directory) / 'data.sqlite'
        tracemalloc.start()
        start = time.perf_counter()
        meta = import_csv(source, db)
        imported = time.perf_counter()
        meta['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        report = simulate(db, meta, RepairOptions(trim_whitespace=True, remove_exact_duplicates=True))
        simulated = time.perf_counter()
        exported_bytes = sum(len(chunk) for chunk in export_csv_chunks(db, meta['columns'], RepairOptions(trim_whitespace=True)))
        end = time.perf_counter()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        print(f'Rows: {args.rows:,}; Input bytes: {source.stat().st_size:,}; Output bytes: {exported_bytes:,}')
        print(f'Ingest: {imported-start:.2f}s; Simulate+dedupe: {simulated-imported:.2f}s; Export: {end-simulated:.2f}s')
        print(f'Peak traced Python allocations: {peak/(1024**2):.2f} MiB (excludes SQLite/native memory and OS caches)')
        print(f'Database bytes: {db.stat().st_size:,}; kept rows: {report["after"]["rows"]:,}')


if __name__ == '__main__':
    main()
