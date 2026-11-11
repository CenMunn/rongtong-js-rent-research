"""Verify a generated inventory snapshot without re-reading external websites."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def verify(out):
    for x in read(out / '来源文件哈希.csv'):
        assert hashlib.sha256((ROOT / x['来源文件']).read_bytes()).hexdigest() == x['SHA256'], x['来源文件']
    for x in read(out / '交付文件清单.csv'):
        b = (out / x['文件']).read_bytes()
        assert len(b) == int(x['字节']) and hashlib.sha256(b).hexdigest() == x['SHA256'], x['文件']
    rows = read(out / '合库候选_28字段及来源.csv')
    uids = {x['source_record_uid'] for x in rows}
    assert len(rows) == len(uids)
    stats = json.loads((out / '运行摘要.json').read_text('utf-8'))
    assert len(rows) == stats['observations_not_independent_samples']
    links = read(out / '资产观察关联候选.csv')
    assert len(links) == stats['link_candidates']
    assert all(x['左记录UID'] in uids and x['右记录UID'] in uids for x in links)
    for x in read(out / '首批17条优先复筛.csv'):
        assert x['来源记录UID'] in uids
    assert all(x['modeling_ready'].startswith('否') and not x['effective_rent'] for x in rows)
    for source, rel in [('WX', '成员成果/王玮/Y01/公众号整理版_v2/公众号采集结果_整理版_v2.csv'),
                        ('X03', '成员成果/王玮/X03/2026-11-09_首批样例/统一填写样例_真实9条.csv'),
                        ('B02', '成员成果/王玮/成员成果验收/2026-11-10_首批/B02_可接收公开观察_28字段.csv')]:
        originals = read(ROOT / rel)
        copied = [x for x in rows if x['source_dataset'] == source]
        assert len(originals) == len(copied)
        for a, b in zip(originals, copied):
            assert all(a[k] == b[k] for k in a)
    return {'source_hashes_match': True, 'artifact_hashes_match': True,
            'unique_source_record_uids': len(uids), 'valid_link_candidates': len(links),
            'priority_records': len(read(out / '首批17条优先复筛.csv')),
            'field_mappings': len(read(out / '28字段来源映射.csv')),
            'market_indicators_separate': len(read(out / '市场指标_独立背景层.csv')),
            'original_28_field_cells_unchanged_WX_X03_B02': True,
            'no_training_admissions_or_effective_rent_fills': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    print(json.dumps(verify(p.parse_args().output.resolve()), ensure_ascii=False, indent=2))
