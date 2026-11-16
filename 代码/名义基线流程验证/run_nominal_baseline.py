"""Offline nominal baseline workflow. Standard library only; no target pricing."""
import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics

D = Decimal

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('Empty input')
    ids = set()
    for row in rows:
        if not row['id'] or row['id'] in ids or not row['building_group']:
            raise ValueError('Missing/duplicate ID or missing building group')
        ids.add(row['id'])
        area, rent = D(row['area_disclosed_sqm']), D(row['rent_annual_cny'])
        if not area.is_finite() or not rent.is_finite() or area <= 0 or rent <= 0:
            raise ValueError('Rent and denominator must be finite and positive')
        y = rent / D(12) / area
        if abs(y - D(row['y_nominal_cny_per_disclosed_sqm_month'])) > D('0.000001'):
            raise ValueError('Stored and independently recomputed labels disagree')
        date.fromisoformat(row['transaction_date'])
        row = row  # keep original source columns; add calculated label separately
        row['_y'] = y
    return rows

def predict_fold(rows, held_building):
    train = [x for x in rows if x['building_group'] != held_building]
    test = [x for x in rows if x['building_group'] == held_building]
    if not train or not test:
        raise ValueError('Empty training or held-out set')
    assert not ({x['building_group'] for x in train} & {x['building_group'] for x in test})
    pred = statistics.median([x['_y'] for x in train])
    return train, test, pred

def evaluate(rows):
    folds = []
    for n, group in enumerate(sorted({x['building_group'] for x in rows}), 1):
        train, test, pred = predict_fold(rows, group)
        for x in test:
            error = pred - x['_y']
            folds.append({'fold': n, 'held_building': group, 'test_id': x['id'],
                'train_ids': '|'.join(t['id'] for t in train),
                'train_buildings': '|'.join(sorted({t['building_group'] for t in train})),
                'n_train': len(train), 'test_date': x['transaction_date'],
                'train_max_date': max(t['transaction_date'] for t in train),
                'contains_later_training_record': any(t['transaction_date'] > x['transaction_date'] for t in train),
                'observed_nominal_y': str(x['_y']), 'predicted_training_median': str(pred),
                'signed_error': str(error), 'absolute_error': str(abs(error)),
                'squared_error': str(error * error),
                'scope': 'PIPELINE_ONLY_NOT_REAL_PRICING_ACCURACY'})
    if len({x['test_id'] for x in folds}) != len(rows) or len(folds) != len(rows):
        raise ValueError('Each observation must be tested exactly once')
    ae = [D(x['absolute_error']) for x in folds]
    sq = [D(x['squared_error']) for x in folds]
    metrics = {'n_observations': len(rows), 'n_buildings': len({x['building_group'] for x in rows}),
        'n_folds': len({x['fold'] for x in folds}), 'MAE': str(sum(ae) / D(len(ae))),
        'RMSE': str((sum(sq) / D(len(sq))).sqrt()), 'unit': '元/披露㎡·月',
        'scope': '仅流程输出，不是实际定价精度；不作目标报价',
        'folds_with_later_training_dates': len({x['fold'] for x in folds if x['contains_later_training_record']}),
        'target_predictions_generated': 0}
    return folds, metrics

def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    batch, out = args.batch.resolve(), args.output.resolve()
    if out == batch or batch not in out.parents:
        raise ValueError('Output must be a new subdirectory of batch')
    with (batch / '冻结输入指纹.csv').open(encoding='utf-8-sig') as f:
        for item in csv.DictReader(f):
            if digest(batch / item['文件']) != item['SHA256']:
                raise ValueError('Frozen file hash mismatch: ' + item['文件'])
    cfg = json.loads((batch / '冻结规则.json').read_text(encoding='utf-8'))
    if cfg['target_pricing'] or cfg['split'] != 'leave_one_building_out':
        raise ValueError('Unsupported protocol')
    rows = load_rows(batch / cfg['input'])
    assert len(rows) == cfg['n_observations']
    assert len({x['building_group'] for x in rows}) == cfg['n_buildings']
    folds, metrics = evaluate(rows)
    out.mkdir(exist_ok=False)
    write_csv(out / '逐折预测及误差.csv', folds)
    (out / '流程指标.json').write_bytes((json.dumps(metrics, ensure_ascii=False, indent=2)+'\n').encode())
    log = {'time_Asia_Shanghai': datetime.now().astimezone().isoformat(), 'python': platform.python_version(),
        'script_SHA256': digest(Path(__file__)), 'input_SHA256': digest(batch / cfg['input']),
        'protocol_SHA256': digest(batch / '冻结规则.json'), 'network_used': False,
        'original_source_modified': False, 'teacher_review': cfg['teacher_review'],
        'checks': ['input_hashes', 'unique_ids', 'positive_denominators', 'recomputed_labels',
                   'building_disjoint', 'one_test_per_observation', 'temporal_warning', 'no_target_prediction']}
    (out / '运行日志.json').write_bytes((json.dumps(log, ensure_ascii=False, indent=2)+'\n').encode())
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
