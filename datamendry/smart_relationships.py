"""Private, bounded, type-aware comparisons for arbitrary *valid CSV* schemas.

This module intentionally does not force text/identifiers into Pearson correlation.
Only aggregate statistics are returned, no individual rows. No external services.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import math
import re
import statistics
from pathlib import Path

from datamendry.analytics_relationships import _coefficient
from datamendry.analytics_v1 import _numeric
from datamendry.engine import make_connection

PROFILE_ROWS = 1000
PAIR_ROWS = 10000
CELL_PREFIX = 160
MAX_CLASSES = 7
MAX_MONTHS = 18

_ID = re.compile(r"(^|[^a-z])(id|index|uuid|identifier|phone|mobile|contact.number|zip|postal|postcode|ssn|passport|email|e.mail|first.name|last.name|surname|full.name|name|address|url|account.number|card.number|ip.address)([^a-z]|$)", re.I)
_DATE = re.compile(r"date|birthday|dob|timestamp|created.at|updated.at|^time$|start.time|end.time", re.I)
_MEASURE = re.compile(r"score|age|salary|amount|price|cost|height|weight|cgpa|gpa|iq|mark|result|profit|sales|revenue|total|rate|percent|temperature|duration|distance|quantity|qty|count|income", re.I)
_BOOL = {'true', 'false', 'yes', 'no', 'male', 'female', 'm', 'f'}
_DATE_FORMATS = ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d.%m.%Y', '%b %d %Y', '%d %b %Y')


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = str(value).strip()
    if not (6 <= len(value) <= 32):
        return None
    # Fast reject ordinary text, email addresses, and identifiers.
    if not (re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', value)
            or re.match(r'^\d{1,2}[./-]\d{1,2}[./-]\d{4}$', value)
            or re.match(r'^[A-Za-z]{3} \d{1,2} \d{4}$', value)
            or re.match(r'^\d{1,2} [A-Za-z]{3} \d{4}$', value)):
        return None
    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]', value):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _schema_classification(name: str, values: list[str | None], n: int) -> dict:
    present = [str(v).strip() for v in values if v is not None and str(v).strip()]
    distinct = len(set(present))
    count = len(present)
    numeric = sum(_numeric(v) is not None for v in present)
    dated = sum(parse_date(v) is not None for v in present) if present and (bool(_DATE.search(name)) or numeric / count < .8) else 0
    unique_ratio = distinct / count if count else 0
    hint_id = bool(_ID.search(name))
    # Safeguard for misleading/uninformative headers: never return raw contact labels.
    if count and (sum(bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v)) for v in present) / count >= .5
                  or sum(bool(re.fullmatch(r'(?:\+?\d[ -]?){10,15}', v)) for v in present) / count >= .8):
        hint_id = True
    hint_date = bool(_DATE.search(name))
    if not count:
        kind, note = 'empty', 'No nonblank values in the sampled rows.'
    elif hint_date and dated / count >= .7 or dated / count >= .9 and dated >= 3:
        kind, note = 'date', 'Parsed dates; trends are grouped by calendar month.'
    elif hint_id:
        kind, note = 'identifier', 'Likely identifying or personal data; comparisons use quality statistics without exposing values.'
    elif numeric / count >= .9 and numeric >= 3:
        # Treat clear row sequence/unique serial numbers as identifiers unless the header is a measurement.
        is_serial = unique_ratio > .98 and count >= 20 and not _MEASURE.search(name)
        kind = 'identifier' if is_serial else 'numeric'
        note = 'Near-unique numeric identifiers are excluded from correlations.' if is_serial else 'Mostly numeric measurements.'
    elif all(v.casefold() in _BOOL for v in present) or distinct <= 15:
        kind, note = 'category', 'Low-cardinality values suitable for frequency comparison.'
    elif _MEASURE.search(name) and numeric >= 3 and numeric / count >= .7:
        kind, note = 'numeric', 'Mostly numeric measurements with some unparseable cells.'
    elif distinct <= 300 and count >= 50 and unique_ratio < .35:
        kind, note = 'category', 'Categorical values; comparisons may group infrequent values.'
    else:
        kind, note = 'text', 'High-cardinality or mixed text; display safe aggregate quality measures instead of misleading correlations.'
    return {'name': name, 'kind': kind, 'sampled': n, 'present': count,
            'missing': n - count, 'unique': distinct, 'note': note}


def _read_columns(db_path: Path, columns: list[str], indices: list[int], limit: int) -> tuple[list[tuple[str | None, ...]], bool]:
    if not indices:
        return [], False
    projection = ', '.join(f'substr(c{i},1,{CELL_PREFIX})' for i in indices)
    con = make_connection(db_path)
    try:
        rows = con.execute(f'SELECT {projection} FROM records ORDER BY id LIMIT ?', (limit + 1,)).fetchall()
    finally:
        con.close()
    return rows[:limit], len(rows) > limit


def smart_overview(db_path: Path, columns: list[str]) -> dict:
    records, more = _read_columns(db_path, columns, list(range(len(columns))), PROFILE_ROWS)
    profiles = [_schema_classification(name, [row[i] for row in records], len(records)) for i, name in enumerate(columns)]
    rank = {'category': 0, 'numeric': 1, 'date': 2, 'text': 3, 'identifier': 4, 'empty': 5}
    # Suggest a comparison that can yield meaningful insights; if not, fall back to a quality comparison.
    candidate = sorted((c for c in profiles if c['kind'] not in {'identifier', 'empty', 'text'}), key=lambda c: rank[c['kind']])
    all_names = [c['name'] for c in profiles]
    if len(candidate) >= 2:
        suggested = [candidate[0]['name'], candidate[1]['name']]
    else:
        suggested = all_names[:2]
    return {'columns': profiles, 'suggested': suggested, 'sampled_rows': len(records),
            'truncated': more, 'data_sent_externally': False,
            'note': 'Type detection is heuristic (first 1,000 rows). Choose any two columns for a suitable comparison or a safe descriptive fallback. Identifiers and personal fields are not used for inferential statistics.'}


def _summary(values: list[float]) -> dict:
    if not values:
        return {'count': 0, 'mean': None, 'min': None, 'max': None}
    return {'count': len(values), 'mean': sum(values)/len(values), 'min': min(values), 'max': max(values)}


def _num(value: str | None) -> float | None:
    return _numeric(value) if value is not None else None


def _label(value: str | None) -> str:
    return str(value).strip()[:60] if value is not None and str(value).strip() else '(Blank)'


def _group_categories(values: list[str], limit: int = MAX_CLASSES) -> tuple[list[str], bool]:
    count = Counter(values)
    top = [label for label, _ in sorted(count.items(), key=lambda item: (-item[1], item[0]))[:limit]]
    collapsed = len(count) > len(top)
    if collapsed:
        top.append('(Other)')
    return top, collapsed


def _map_group(value: str, labels: list[str]) -> str:
    return value if value in labels else '(Other)'


def _compare_quality(x: dict, y: dict, xs: list[str | None], ys: list[str | None], reason: str) -> dict:
    """Quality checks for both complete sampled columns, without publishing values."""
    n = len(xs)
    def summarize(schema: dict, values: list[str | None]) -> dict:
        present = [str(v).strip() for v in values if v is not None and str(v).strip()]
        return {'name':schema['name'], 'kind':schema['kind'], 'note':schema['note'],
                'sampled':n, 'present':len(present), 'missing':n-len(present),
                'unique':len(set(present))}
    left, right = summarize(x,xs), summarize(y,ys)
    return {'mode': 'quality', 'columns': [left, right], 'reason': reason,
            'metrics': {'rows_inspected': n, 'left_complete_pct': round(left['present'] * 100 / max(n, 1), 2),
                        'right_complete_pct': round(right['present'] * 100 / max(n, 1), 2)},
            'note': 'Both columns are analyzed for completeness and distinctness. A statistical association would not be meaningful or privacy-preserving for this pair.'}


def _compare_numeric(xs: list[str | None], ys: list[str | None]) -> dict:
    pairs = [(a, b) for a, b in zip((_num(x) for x in xs), (_num(y) for y in ys)) if a is not None and b is not None]
    if len(pairs) < 3:
        return {'mode': 'quality', 'reason': 'Not enough paired valid numbers.', 'metrics': {'paired_values': len(pairs)}}
    r = _coefficient(pairs)
    lx, hx = min(x for x, _ in pairs), max(x for x, _ in pairs)
    ly, hy = min(y for _, y in pairs), max(y for _, y in pairs)
    bins = [[0] * 10 for _ in range(10)]
    for x, y in pairs:
        xi = min(9, max(0, int((x-lx)/(hx-lx)*10))) if hx > lx else 0
        yi = min(9, max(0, int((y-ly)/(hy-ly)*10))) if hy > ly else 0
        bins[9-yi][xi] += 1
    return {'mode':'numeric_numeric', 'r':r, 'bins': bins, 'x_range':[lx,hx], 'y_range':[ly,hy],
            'metrics': {'paired_values': len(pairs)},
            'note': 'Pearson r and 10×10 aggregated density. Correlation is not causation; constant values have undefined r.'}


def _compare_categories(xs: list[str | None], ys: list[str | None]) -> dict:
    pairs = [(_label(x), _label(y)) for x, y in zip(xs, ys) if x and x.strip() and y and y.strip()]
    if not pairs:
        return {'mode': 'quality', 'reason': 'No paired nonblank category values.', 'metrics': {'paired_values': 0}}
    xvals, yvals = [x for x, _ in pairs], [y for _, y in pairs]
    xlabels, collapse_x = _group_categories(xvals)
    ylabels, collapse_y = _group_categories(yvals)
    xix = {label: i for i, label in enumerate(xlabels)}
    yix = {label: i for i, label in enumerate(ylabels)}
    cells = [[0 for _ in xlabels] for _ in ylabels]
    for x, y in pairs:
        cells[yix[_map_group(y, ylabels)]][xix[_map_group(x, xlabels)]] += 1
    # Cramer's V is only meaningful here if categories were not collapsed.
    v = None
    if not collapse_x and not collapse_y and len(xlabels) > 1 and len(ylabels) > 1:
        total = len(pairs)
        row_counts = [sum(row) for row in cells]
        col_counts = [sum(row[j] for row in cells) for j in range(len(xlabels))]
        chi2 = sum((cells[i][j] - row_counts[i]*col_counts[j]/total)**2 / (row_counts[i]*col_counts[j]/total)
                   for i in range(len(ylabels)) for j in range(len(xlabels))
                   if row_counts[i] and col_counts[j])
        v = min(1.0, math.sqrt(chi2 / (total * min(len(xlabels)-1, len(ylabels)-1))))
    return {'mode': 'category_category','x_labels':xlabels,'y_labels':ylabels,'cells':cells,
            'cramers_v':v, 'categories_collapsed':collapse_x or collapse_y,
            'metrics': {'paired_values':len(pairs)},
            'note': "Category cross-tab. Cramér's V is shown only when no categories are grouped into Other; descriptive association, not causation."}


def _compare_groups(categories: list[str | None], numeric: list[str | None], category_name: str, numeric_name: str) -> dict:
    rows = [(_label(c), v) for c, v in zip(categories, (_num(n) for n in numeric)) if c and c.strip() and v is not None]
    if not rows:
        return {'mode':'quality', 'reason':'No paired category/numeric observations.', 'metrics':{'paired_values':0}}
    groups, collapsed = _group_categories([c for c, _ in rows])
    data = defaultdict(list)
    for label, value in rows:
        data[_map_group(label, groups)].append(value)
    series = [{'category': label, **_summary(data[label])} for label in groups if data[label]]
    return {'mode':'category_numeric','category_column':category_name,'numeric_column':numeric_name,
            'groups':series,'categories_collapsed':collapsed,'metrics': {'paired_values':len(rows)},
            'note':'Group means are descriptive and affected by group sizes. Infrequent categories are grouped as Other.'}


def _compare_date_numeric(dates: list[str | None], values: list[str | None], date_name: str, num_name: str) -> dict:
    monthly = defaultdict(list)
    for day, raw in zip(dates, values):
        d = parse_date(day)
        v = _num(raw)
        if d and v is not None:
            monthly[d.strftime('%Y-%m')].append(v)
    keys = sorted(monthly)[-MAX_MONTHS:]
    return {'mode':'date_numeric','date_column':date_name,'numeric_column':num_name,
            'months':[{'month':month, **_summary(monthly[month])} for month in keys],
            'metrics': {'paired_values':sum(map(len, monthly.values())), 'months_total':len(monthly)},
            'note':f'Monthly mean of numeric values; displaying up to the most recent {MAX_MONTHS} months. Date parsing may be ambiguous for slash-formatted dates.'}


def _compare_date_category(dates: list[str | None], categories: list[str | None], date_name: str, category_name: str) -> dict:
    pairs = [(d.strftime('%Y-%m'), _label(c)) for raw, c in zip(dates, categories) if (d := parse_date(raw)) and c and c.strip()]
    if not pairs:
        return {'mode':'quality','reason':'No dates paired with nonblank categories.','metrics':{'paired_values':0}}
    labels, collapsed = _group_categories([c for _, c in pairs], 4)
    months = defaultdict(Counter)
    for month, category in pairs:
        months[month][_map_group(category, labels)] += 1
    keys = sorted(months)[-MAX_MONTHS:]
    return {'mode':'date_category','date_column':date_name,'category_column':category_name,
            'categories':labels,'months':[{'month':k,'counts':[months[k][c] for c in labels]} for k in keys],
            'categories_collapsed':collapsed,'metrics':{'paired_values':len(pairs), 'months_total':len(months)},
            'note':'Counts by month and category; displayed months and categories are limited for readability.'}


def _compare_dates(xs: list[str | None], ys: list[str | None]) -> dict:
    offsets = [(b-a).days for x,y in zip(xs,ys) if (a:=parse_date(x)) and (b:=parse_date(y))]
    if not offsets:
        return {'mode':'quality','reason':'No paired dates could be parsed.', 'metrics':{'paired_values':0}}
    return {'mode':'date_date','metrics':{'paired_values':len(offsets),'mean_difference_days':statistics.mean(offsets),
                                        'median_difference_days':statistics.median(offsets),
                                        'min_difference_days':min(offsets),'max_difference_days':max(offsets)},
            'note':'Day differences are calculated as second date minus first date for paired parseable records.'}


def smart_pair(db_path: Path, columns: list[str], x: str, y: str) -> dict:
    if x not in columns or y not in columns or x == y:
        raise ValueError('Choose two different columns from this dataset')
    overview = smart_overview(db_path, columns)
    schema = {col['name']: col for col in overview['columns']}
    a, b = schema[x], schema[y]
    records, more = _read_columns(db_path, columns, [columns.index(x), columns.index(y)], PAIR_ROWS)
    xs = [row[0] for row in records]
    ys = [row[1] for row in records]
    ka, kb = a['kind'], b['kind']
    # Explicitly avoid returning potentially sensitive raw category labels for identifiers/free text.
    if ka in {'identifier', 'text', 'empty'} or kb in {'identifier', 'text', 'empty'}:
        detail = _compare_quality(a,b,xs,ys, 'Contains identifier, personal, unstructured, or entirely blank data.')
    elif ka == kb == 'numeric':
        detail = _compare_numeric(xs,ys)
    elif ka == kb == 'category':
        detail = _compare_categories(xs,ys)
    elif {ka,kb} == {'numeric','category'}:
        detail = _compare_groups(xs,ys,x,y) if ka == 'category' else _compare_groups(ys,xs,y,x)
    elif {ka,kb} == {'numeric','date'}:
        detail = _compare_date_numeric(xs,ys,x,y) if ka == 'date' else _compare_date_numeric(ys,xs,y,x)
    elif {ka,kb} == {'category','date'}:
        detail = _compare_date_category(xs,ys,x,y) if ka == 'date' else _compare_date_category(ys,xs,y,x)
    elif ka == kb == 'date':
        detail = _compare_dates(xs,ys)
    else:
        detail = _compare_quality(a,b,xs,ys,'No reliable two-variable statistic is available for these field types.')
    return {'x':x,'y':y,'x_kind':ka,'y_kind':kb,'sampled_rows':len(records),
            'truncated':more,'data_sent_externally':False,
            'method': 'type-aware comparison',**detail}
