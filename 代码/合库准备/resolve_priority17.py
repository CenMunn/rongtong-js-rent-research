"""Curated, evidence-bounded representative view of the existing 17 priority rows."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREP = ROOT / '成员成果/王玮/合库准备/2026-11-12_合库准备初版'


def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(p, rows):
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# Explicit source-row facts. No address-only matching and no chosen values for unresolved cases.
SPECS = [
    ('ZS285', 'E01', '南京', '沿街商业披露范围', 'B01::CYF-B01-CJ-N0117FCZZ250804-4', ['B02::B02-NJ02-C'],
     '361800', '元/年', '210.90', '2025-10-22', '', '', 'B02成交日与公示发布日分列；公示发布2025-11-17', '税费未知', 'COMMERCIAL_TRANSACTION', '名义成交候选；非净租金'),
    ('SCHOOL9', 'E02', '苏州', '校园商铺', 'B01::CYF-B01-CJ-N0117FCZZ250449', [],
     '810202', '元/年', '205.73', '2025-04-15', '', '', '成交记录时间；签约起止日未取得', '税费未知', 'CAMPUS_TRANSACTION', '校园经营限制及可比性待筛'),
    ('SCHOOL1', 'E03', '苏州', '校园商铺', 'B01::CYF-B01-CJ-N0117FCZZ250441', [],
     '68671.80', '元/年', '36.45', '2025-04-15', '', '', '成交记录时间；签约起止日未取得', '税费未知', 'CAMPUS_TRANSACTION', '已有指定4字段人工确认；不扩展到合同条款'),
    ('SCHOOL2', 'E04', '苏州', '校园商铺', 'B01::CYF-B01-CJ-N0117FCZZ250442', [],
     '34759.80', '元/年', '18.45', '2025-04-15', '', '', '成交日明确；挂牌截止3月24/31日并存，不据此改成交日', '税费未知', 'CAMPUS_TRANSACTION', '校园经营限制、挂牌截止差异保留'),
    ('BAODAI', 'E05', '苏州', '办公（公告用途）', 'B02::B02-SZ02-C', [],
     '21060', '元/年', '39', '2026-09-29', '', '', '成交日与公示发布日相同；合同期未知', '物业/水费包含与承担条款冲突', 'OFFICE_TRANSACTION_FEE_CONFLICT', '金额可保留；暂缓进入统一费用口径模型'),
    ('RENMIN', 'E06', '苏州', '办公三室合包（公告用途）', 'B02::B02-SZ04-C', [],
     '74200', '元/年', '103', '2026-07-06', '', '', '公示发布2026-07-07，区别于成交日', '挂牌物业费另计；成交合同费用未核', 'OFFICE_TRANSACTION', '三室合包；不拆成三个样本'),
    ('ZS34', 'E07', '南京', '商业可比候选，用途未在本批独立确认', 'X03::O01', [],
     '68000', '元/年', '61.69', '', '', '', '原表2026-02-13；已有网页头部/正文日期异常未解决', '费用不完整', 'COMMERCIAL_TRANSACTION_DATE_HOLD', '名义数值可保留；暂不进入严格时间切分'),
    ('JINGDE', 'E08', '苏州', '商业可比候选，用途未在本批独立确认', 'X03::O03', [],
     '40788', '元/年', '20', '2024-11-16', '', '', '正文成交2024-11-16；公示发布2024-11-18', '费用不完整', 'COMMERCIAL_TRANSACTION', '按披露范围接收；用途适配继续筛'),
    ('CHENGXIN', 'E09', '南京', '仓储、包装、生产加工（披露用途）', 'C02::C02-HS-01', ['X03::O04'],
     '181120', '元/月', '5660', '', '2021-05-12', '2024-05-11', '合同价格期间；截至本批为历史，非2026当前价', '税费及免租未披露', 'INDUSTRIAL_CONTRACT_UNKNOWN_FEES', '历史合同名义候选；与下一期间同资产隔离切分'),
    ('CHENGXIN', 'E10', '南京', '仓储、包装、生产加工（披露用途）', 'C02::C02-HS-02', ['X03::O05'],
     '190176', '元/月', '5660', '', '2024-05-12', '2026-05-11', '合同价格期间；截至本批已到期，续租未知', '税费及免租未披露', 'INDUSTRIAL_CONTRACT_UNKNOWN_FEES', '合同分段价格不解释为城市涨幅'),
    ('ZHUJIE', 'E11', '苏州', '厂房及配套（披露用途）', 'C02::C02-HSHE-01', ['X03::O07'],
     '32', '元/平方米/月', '12676.62', '', '', '2025-05-31', '原文仅2024年合同；不编造准确起日', '原合同完整费用未取得', 'INDUSTRIAL_CONTRACT_UNKNOWN_FEES', '历史期间部分日期已知；不与23元作统一净租金变化'),
    ('ZHUJIE', 'E12', '苏州', '厂房及配套（披露用途）', 'C02::C02-HSHE-02', ['X03::O08'],
     '23', '元/平方米/月', '12676.62', '', '2025-06-01', '', '生效2025-06-01；公告2025-08-08；终止日与2026后续未知', '含税且含厂房、场地租赁及生活物业费', 'INDUSTRIAL_CONTRACT_GROSS_BUNDLE', '综合费用价格单列，不能标净租金；预测时考虑披露滞后'),
]


def build(out):
    if out.exists():
        raise FileExistsError('Use a new batch directory')
    inputs = [PREP / '合库候选_28字段及来源.csv', PREP / '首批17条优先复筛.csv',
              PREP / '资产观察关联候选.csv', ROOT / '共享资料/原文抽核观察.csv',
              ROOT / '成员成果/游依宸/C02_汉桑禾盛/C02_结构化历史合同表.csv']
    hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    allrows = read(inputs[0]); byid = {x['source_record_uid']: x for x in allrows}
    priority_ids = {x['来源记录UID'] for x in read(inputs[1])}
    decisions, labels, evidence = [], [], []
    scope = []
    for asset, event, city, sector, rep, aliases, amount, unit, area, date, start, end, timescope, fees, group, limitation in SPECS:
        item = byid[rep]
        ids = [rep] + aliases
        assert all(uid in priority_ids for uid in ids)
        price = Decimal(amount)
        for uid in ids:
            r = byid[uid]
            assert Decimal(r['parsed_price']) == price, uid
            assert r['parsed_price_unit'] == unit, uid
            decisions.append({'原记录UID': uid, '本批事件ID': 'CAND-' + event,
                              '临时资产范围ID': 'CAND-A-' + asset, '代表记录UID': rep,
                              '本批保留决定': '选作代表视图入口' if uid == rep else '同事件补充来源，代表视图不重复计数',
                              '原记录处理': '完整保留；不改1278条候选总表、不删原表',
                              '对应依据': '来源表门牌/包范围、原价单位、期间及既有抽核记录对应；不只按地址匹配',
                              '确认边界': '本批离线辅助整理决定，非新增成员人工签核'})
            evidence.append({'事件ID': 'CAND-' + event, '原记录UID': uid,
                             '原始范围': r['address_scope_floor'], '原始价格': r['raw_price_unit'],
                             '原始面积表达': r['area_building_chargeable_land'], '原始期间': r['publish_sign_start_end_dates'],
                             '原单价': r['monthly_normalized'], '来源': r['source_file'],
                             '来源及原件定位': r['source_url_page'], '原核验范围': r['verification_status']})
        nominal = price if unit == '元/平方米/月' else price / Decimal(area) / (12 if unit == '元/年' else 1)
        for uid in ids:
            shown = byid[uid]['existing_monthly_numeric']
            assert shown and abs(Decimal(shown) - nominal) < Decimal('0.0051'), uid
        labels.append({'事件ID': 'CAND-' + event, '临时资产范围ID': 'CAND-A-' + asset,
                       '城市': city, '业态层': sector, '价格性质': item['price_nature_code'],
                       '代表记录UID': rep, '同事件来源UID': '；'.join(ids), '范围': item['address_scope_floor'],
                       '原价': amount, '原单位': unit, '披露面积平方米': area,
                       '面积口径': '原披露面积；未证明实际计租面积',
                       '名义标签候选': format(nominal.quantize(Decimal('0.000001')), 'f'),
                       '标签单位': '元/披露平方米/月' if unit != '元/平方米/月' else '元/平方米/月（原文直录）',
                       '标签依据': '年总租÷12÷披露面积' if unit == '元/年' else '月总租÷披露面积' if unit == '元/月' else '原文单价直录，不反推总租',
                       '成交日_无争议才填': date, '价格起日_明确才填': start, '价格止日_明确才填': end,
                       '日期及期间限制': timescope, '费用口径': fees, '标签分层代码': group,
                       '使用决定': limitation, '独立训练样本已准入': '否；代表观察与条件候选，未训练',
                       '切分组': 'CAND-A-' + asset, '切分限制': '仅本批10个临时范围；全库关联解决前不作最终泄漏隔离证明'})
        scope.append({'事件ID': 'CAND-' + event, '原始期间表达': item['publish_sign_start_end_dates'],
                      '时间字段取值依据': ('B02::B02-NJ02-C期间字段；B01保留公示URL与原期间' if event == 'E01' else rep),
                      '字段处理': timescope, '预测可得性': '保留发布时间/公告滞后，禁止把事后披露当提前可用特征'})
    assert len(decisions) == 17 and {x['原记录UID'] for x in decisions} == priority_ids
    assert len(labels) == 12 and len({x['临时资产范围ID'] for x in labels}) == 10
    # Original public-table aliases are kept as corroboration, not promoted to new events.
    joins = read(inputs[2]); extra = []
    decision_by_uid = {x['原记录UID']: x for x in decisions}
    seen = set()
    for edge in joins:
        for a, b in [(edge['左记录UID'], edge['右记录UID']), (edge['右记录UID'], edge['左记录UID'])]:
            if a not in decision_by_uid or not b.startswith('SH47::') or (a, b) in seen:
                continue
            seen.add((a, b))
            extra.append({'优先记录UID': a, '事件ID': decision_by_uid[a]['本批事件ID'], '共享表记录UID': b,
                          '关系决定': '同网址同价的辅助来源待确认，不能新增计样',
                          '依据': edge['依据'], '限制': '本轮未逐共享原件再验收；不自动用其日期或面积覆盖代表值'})
    out.mkdir(parents=True)
    write(out / '17条跨表对应与保留决定.csv', decisions)
    write(out / '12个事件_名义标签候选.csv', labels)
    write(out / '17条对应证据快照.csv', evidence)
    write(out / '价格期间与日期取值记录.csv', scope)
    write(out / '共享表辅助来源关联.csv', extra)
    groups = Counter((x['业态层'], x['标签分层代码']) for x in labels)
    write(out / '业态及标签口径分层.csv', [{'业态层': k[0], '标签层': k[1], '价格事件数': v,
                                          '限制': '分层候选，不合并训练；同资产多期不是独立资产'} for k, v in groups.items()])
    for rel, digest in hashes.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest
    record = {'source_hashes': hashes, 'priority_source_records': 17, 'representative_events': 12,
              'provisional_asset_scopes': 10, 'public_transaction_events': 8, 'contract_periods': 4,
              'contract_asset_scopes': 2, 'all_17_price_and_nominal_checks_passed': True,
              'raw_records_deleted': 0, 'member_signoff_added': False, 'training_performed': False}
    (out / '核查记录.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k != 'source_hashes'}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    build(p.parse_args().out.resolve())
