from __future__ import annotations

import csv
import hashlib
import io
import uuid
from pathlib import Path

import pytest

from datamendry.engine import (
    DatasetError, RepairOptions, column_names, export_csv_chunks, fetch_preview,
    import_csv, safe_csv_cell, simulate, transform_row,
)


def load(tmp_path: Path, value: str) -> tuple[Path, dict]:
    source = tmp_path / f'input-{uuid.uuid4().hex}.csv'
    source.write_text(value, encoding='utf-8')
    db = tmp_path / f'data-{uuid.uuid4().hex}.sqlite'
    meta = import_csv(source, db)
    meta['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    return db, meta


def test_streamed_import_and_profile(tmp_path):
    db, meta = load(tmp_path, 'id,name,price\n001, Alice ,10\n001, Alice ,10\n002,  ,\n')
    assert meta['rows'] == 3
    assert meta['columns'] == ['id', 'name', 'price']
    assert meta['duplicate_rows'] == 1
    assert meta['missing_cells'] == 2
    assert fetch_preview(db, meta['columns'])['rows'][0][0] == '001'


def test_simulation_idempotence_and_export(tmp_path):
    db, meta = load(tmp_path, 'id,name\n001, Jane \n001,Jane\n002, \n')
    opts = RepairOptions(trim_whitespace=True, normalize_blanks=True, remove_exact_duplicates=True)
    result = simulate(db, meta, opts)
    assert result['after']['rows'] == 2
    assert result['impact']['removed_rows'] == 1
    assert result['impact']['changed_cells_in_kept_rows'] == 2
    exported = b''.join(export_csv_chunks(db, meta['columns'], opts)).decode('utf-8-sig')
    assert list(csv.reader(io.StringIO(exported))) == [['id', 'name'], ['001', 'Jane'], ['002', '']]
    assert simulate(db, meta, opts) == result


def test_csv_formula_injection_defense(tmp_path):
    db, meta = load(tmp_path, 'name,formula\nme,=CMD(1)\nyou," +SUM(2,2)"\n')
    output = b''.join(export_csv_chunks(db, meta['columns'], RepairOptions())).decode('utf-8-sig')
    values = list(csv.reader(io.StringIO(output)))
    assert values[1][1] == "'=CMD(1)"
    assert values[2][1].startswith("' ")
    assert safe_csv_cell('regular') == 'regular'
    assert safe_csv_cell('-45') == "'-45"  # conservative: negative numbers are text in this version


def test_invalid_headers(tmp_path):
    with pytest.raises(DatasetError, match='unique'):
        load(tmp_path, 'Name,name\na,b\n')
    with pytest.raises(DatasetError, match='non-empty'):
        load(tmp_path, 'id,\na,b\n')


def test_reject_malformed(tmp_path):
    with pytest.raises(DatasetError, match='expected'):
        load(tmp_path, 'a,b\n1\n')
    with pytest.raises(DatasetError, match='header'):
        load(tmp_path, 'a,b\n')
    with pytest.raises(DatasetError, match='empty'):
        load(tmp_path, '')


def test_blank_preserves_zero(tmp_path):
    assert transform_row(['0', '  ', '0003'], RepairOptions(normalize_blanks=True)) == (['0', None, '0003'], 1, 1)


def test_many_rows_without_dataframe(tmp_path):
    source = tmp_path / 'data.csv'
    with source.open('w', encoding='utf-8') as handle:
        handle.write('id,payload\n')
        for i in range(15_000):
            handle.write(f'{i:06d},hi{i % 17}\n')
    db = tmp_path / 'data.sqlite'
    meta = import_csv(source, db)
    assert meta['rows'] == 15_000
    assert meta['duplicate_rows'] == 0
    meta['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert simulate(db, meta, RepairOptions())['after']['rows'] == 15_000
    assert len(b''.join(export_csv_chunks(db, meta['columns'], RepairOptions()))) > 180_000
