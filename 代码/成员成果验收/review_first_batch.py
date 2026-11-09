"""2026-11-10限定首批验收：离线核对B02，盘点B01/C02/Y02；不改成员原件或共享底表。"""
import argparse
from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / '成员成果/王玮/成员成果验收/2026-11-10_首批'

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def write(path, rows, fields=None):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader(); w.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rel(path):
    return path.relative_to(ROOT).as_posix()

def text(path):
    soup = BeautifulSoup(path.read_bytes(), 'html.parser')
    for node in soup(['script', 'style', 'noscript']):
        node.decompose()
    return re.sub(r'\s+', ' ', ' '.join(soup.stripped_strings))

def compact(value):
    return re.sub(r'\s+', '', value)

def extract_zip(source, dest):
    inventory = []
    with zipfile.ZipFile(source) as archive:
        for entry in archive.infolist():
            name = entry.filename
            if not entry.flag_bits & 0x800:
                try:
                    name = name.encode('cp437').decode('gbk')
                except UnicodeError:
                    pass
            target = (dest / name).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError('压缩包路径超出展开目录')
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
                inventory.append({'原始包': rel(source), '包内名称': name,
                                  '展开位置': rel(target), '字节数': entry.file_size,
                                  'SHA256': sha(target)})
    return inventory


# 审阅存档正文后建立的逐字段预期，不由成员填表值反向生成。
FACTS = {
    'NJ01': ('2026320100FA00002', '1014.35', '50.0000', '万元/年', None,
             '租金价格(万元/年)： 50.0000', '建筑面积(㎡)： 1014.35(以实际可租赁面积为准)'),
    'NJ02': ('N0117FCZZ250804-4', '210.90', '361800.00', '元/年', '361800.00',
             '租金底价（元） 361800.00元/年', '租赁面积约(㎡) 210.90'),
    'NJ03': ('JSCQ_XM_34455 / GR2026JS1001839', '280', '49.056', '万元/年', '49.08',
             '租金底价 49.056万元/年', '租赁面积 280平方米'),
    'SZ02': ('SCJR20262001', '39', '21060', '元/年', '21060',
             '租金挂牌底价 21060 元/年', '出租面积(m²) 39'),
    'SZ03': ('SCJR20262536', '250', '700000', '元/年', None,
             '租金挂牌底价 700000 元/年', '出租面积(m²) 250'),
    'SZ04': ('SCJRZ20260373', '103', '74200', '元/年', '74200',
             '租金挂牌底价 74200 元/年', '出租面积(m²) 103'),
}
RESULT_FILES = {'NJ02': 'NJ02_C', 'NJ03': 'NJ03_C',
                'SZ02': 'SZ02_C_ALT', 'SZ04': 'SZ04_C_ALT'}


def build(out):
    if out.exists():
        raise FileExistsError('已发布验收目录不得覆盖，请指定新 --out')
    originals = [ROOT / f'成员成果/陈怡帆/B0{i}_2026110{7+i}_成果与原件.zip' for i in [1, 2]]
    protected = [ROOT/'共享资料/南京苏州交易明细.csv', ROOT/'共享资料/公众号采集结果.csv',
                 ROOT/'成员成果/王玮/Y01/公众号整理版_v2/公众号采集结果_整理版_v2.csv',
                 ROOT/'成员成果/游依宸/C02_汉桑禾盛/C02_结构化历史合同表.csv',
                 ROOT/'成员成果/游依宸/Y02_珍珠北路/Y02_历轮条件对照表.csv', *originals]
    before = {rel(p): sha(p) for p in protected}
    out.mkdir(parents=True)
    file_inventory = []
    for archive in originals:
        file_inventory.extend(extract_zip(archive, out/'原始提交展开'))
    # 原始存档保留字节，不让Git自动转换换行或要求清理原网页空白。
    (out/'原始提交展开/.gitattributes').write_text('* -text -diff\n**/* -text -diff\n', encoding='utf-8')
    write(out/'原始提交文件清单.csv', file_inventory)
    b = out/'原始提交展开/B02_20261109'
    a = out/'原始提交展开/B01_20261108'
    fields, observations = read(b/'B02_统一采集表.csv')
    _, candidates = read(b/'B02_外部租金候选.csv')
    template, _ = read(ROOT/'共享资料/统一采集空表.csv')
    _, evidence = read(b/'证据索引.csv')
    assert fields == template and len(observations) == 10 and len(candidates) == 6
    assert len(set(r['observation_id'] for r in observations)) == 10
    assert len(set(r['asset_id'] for r in observations)) == 6
    evidence_byid = {r['证据编号']: r for r in evidence}
    pages = {}
    evidence_checks = []
    for row in evidence:
        path = b/row['存档路径']
        assert path.is_file() and sha(path) == row['SHA256'], row['证据编号']
        pages[row['证据编号']] = text(path)
        evidence_checks.append({**row, '验收存档位置': rel(path),
                                '本次哈希核对': '与成员证据索引一致',
                                '核对边界': '离线存档；未以哈希代替官方真实性或当前在线可达性验证'})
    write(out/'B02_证据完整性核对.csv', evidence_checks)
    assert len(evidence_checks) == 10
    _, shared = read(ROOT/'共享资料/南京苏州交易明细.csv')
    _, b01 = read(a/'B01_统一采集表.csv')
    assert read(a/'底表/南京苏州交易明细.csv') == read(ROOT/'共享资料/南京苏州交易明细.csv')
    overlaps, audit, quotes, changes, accepted = [], [], [], [], []
    def quote(oid, eid, kind, fragment, limit=450):
        pos = compact(pages[eid]).find(compact(fragment))
        assert pos >= 0, (oid, eid, fragment)
        # 定位使用正文规范化字符串；完整HTML及SHA256仍单独保留。
        plain = compact(pages[eid])
        quotes.append({'观察ID': oid, '字段或依据': kind, '证据编号': eid,
                       '摘录': plain[max(0, pos-30):pos+min(len(compact(fragment))+80, limit)],
                       '规范化正文偏移': pos, '来源URL': evidence_byid[eid]['原始链接'],
                       '存档': rel(b/evidence_byid[eid]['存档路径']), '存档SHA256': evidence_byid[eid]['SHA256']})
    for row in observations:
        oid = row['observation_id']; key, phase = oid.split('-')[1:]
        round_id, area, p_price, unit, c_price, price_phrase, area_phrase = FACTS[key]
        p_id = key+'_P'; eid = p_id if phase == 'P' else RESULT_FILES[key]
        quote(oid, p_id, '披露面积及分母来源', area_phrase)
        amount = Decimal(p_price if phase == 'P' else c_price)
        multiplier = Decimal(10000 if unit.startswith('万元') else 1)
        annual = amount*multiplier
        source_raw = row['raw_price_unit'].replace(',', '').strip()
        m = re.fullmatch(r'([\d.]+)\s*(万元/年|元/年)', source_raw)
        assert m and Decimal(m[1]) == amount and m[2] == unit, oid
        assert Decimal(re.search(r'[\d.]+', row['area_building_chargeable_land'])[0]) == Decimal(area), oid
        assert row['round_contract_id'] == round_id, oid
        if phase == 'P':
            quote(oid, p_id, '挂牌原价和年度单位', price_phrase)
        else:
            fragment = {'NJ02': '成交年租金（元） 361,800.00',
                        'NJ03': '成交年租金 49.08 万元',
                        'SZ02': '成交年租金(元/年)', 'SZ04': '成交年租金(元/年)'}[key]
            quote(oid, eid, '成交年租金及单位表头', fragment)
            # 年租列与标的行同时保存，防止仅找到表头就推定金额。
            if key in ['SZ02','SZ04']:
                quote(oid, eid, '成交表项目行', FACTS[key][0] + (' 宝带西路1155号' if key=='SZ02' else ' 人民路1058号'))
                assert ('21060' if key=='SZ02' else '74200') in pages[eid]
            if key != 'NJ03':
                assert round_id in pages[p_id] and round_id in pages[eid]
            else:
                for piece in ['江苏省地质局', '珠江路700号山水大酒店一楼部分临街商业用房', '49.056']:
                    assert compact(piece) in compact(pages[p_id]) and compact(piece) in compact(pages[eid])
        calc = (annual/Decimal(12)/Decimal(area)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        assert Decimal(row['monthly_normalized']) == calc, oid
        limitation = '披露面积下的名义分摊；实际计租、合同起止、实收及有效租金未核'
        pair = ('挂牌本页明确披露，与成交分开记录'+('；本批未取得成交原件' if c_price is None else '')) if phase=='P' else '同项目编号、主体及标的/挂牌期配对；成交页未再次披露面积，分母取同编号挂牌'
        acceptance = '可接收—公开价格观察（限定字段）'
        if key=='NJ03':
            pair = '挂牌网页ID与成交标的ID不同；名称、地址范围、出租方及评估/底价支持关联，未取得直接编号桥'
            if phase=='C':
                acceptance = '条件接收—跨编号同轮配对待补证'
            limitation += '；挂牌/成交不作唯一同轮关系已确认，成交单价分母为候选配对'
        if key=='SZ02':
            limitation += '；费用栏与其他条款关于物业费/水费冲突，不作净租金统一'
        if key=='NJ01': limitation += '；实际可租面积待核；成交留空是合理缺失'
        if key=='SZ03': limitation += '；1—3层合包，不拆成首层价；成交留空是合理缺失'
        if key=='SZ04': limitation += '；三室合包；物业费另计且成交合同未取得'
        source_matches = []
        for n, old in enumerate(shared,1):
            url_col = '挂牌原文' if phase=='P' else '成交原文'
            price_col = '挂牌或公示底价元每年' if phase=='P' else '成交元每年'
            if old[url_col] and old[price_col] and old[url_col] in row['source_url_page']:
                source_matches.append(f'共享47行：数据行{n}')
                overlaps.append({'B02观察ID':oid,'既有资料':'共享资料/南京苏州交易明细.csv',
                                 '既有行或ID':str(n),'匹配依据':'同一挂牌/成交URL及相同价格性质',
                                 '处理':'重复观察候选，保留两份溯源；不算两笔独立新增交易；未自动删行'})
        for old in b01:
            if phase=='C' and old['round_contract_id'] == round_id:
                source_matches.append('B01：'+old['observation_id'])
                overlaps.append({'B02观察ID':oid,'既有资料':'B01_统一采集表.csv',
                                 '既有行或ID':old['observation_id'],'匹配依据':'同轮编号、成交性质和年租金对应',
                                 '处理':'后续关联正式ID；保留提交记录，不并算独立样本'})
        audit.append({'观察ID':oid,'城市':next(x['城市'] for x in candidates if x['候选ID']==key),
                      '价格性质':row['price_type'],'原价':str(amount),'原单位':unit,'核对年租金元':str(annual),
                      '披露面积㎡':area,'分母来源':p_id+'：'+area_phrase,
                      '原月单价':row['monthly_normalized'],'复算元每披露㎡月':str(calc),
                      '算术检查':'一致（两位小数）','配对核对':pair,'接收结论':acceptance,
                      '费用与范围限制':limitation,'重复关系':'；'.join(source_matches) or '本次对比共享47行和B01未见同观察；不是全库唯一性证明',
                      '核对方式':'Codex离线存档辅助验收，未代替成员人工签核'})
        clone = dict(row)
        def edit(field, value, reason):
            if clone[field] != value:
                changes.append({'观察ID':oid,'字段':field,'原值':clone[field],'验收副本值':value,
                                '原因':reason,'证据':rel(b/evidence_byid[p_id]['存档路径']),
                                '处理性质':'辅助核验说明及口径整理，非成员新增签核'})
                clone[field] = value
        edit('monthly_normalized', f'{calc}元/披露㎡/月（名义；年租金{annual}元÷12÷披露面积{area}㎡）'+('；成交分母配对待补证' if key=='NJ03' and phase=='C' else ''),
             '只补单位、公式和分母标签，数值不改')
        fee = {'SZ02':'挂牌费用栏称底价含物业费及水费；其他条件又称水电气热及物业费由承租方支付，存在冲突；合同费用待核',
               'SZ03':'挂牌仅可开具江苏省非税收入统一票据，不提供增值税专用或普通发票；其他费用按原件，非净租金',
               'SZ04':'挂牌物业费10元/㎡/月另行与物业公司签约，以实际签署为准；不并入当前租金，成交合同费用未核'}
        if key in fee:
            edit('tax_fee', fee[key], '将已在来源和缺失说明中披露的费用口径移入专用字段，不擅自解决冲突或认定成交合同沿用挂牌')
        if key=='NJ01':
            assert '租金递增方式：无递增' in compact(pages[p_id])
            edit('rent_free_escalation', row['rent_free_escalation']+'；挂牌第5条：无递增', '补已明确的挂牌递增信息，未取得签约合同')
        edit('verification_status', row['verification_status']+'\n2026-11-10 Codex辅助验收：金额、原单位、披露面积和名义换算已对照本批存档；'+acceptance+'；非成员人工签核',
             '保留提交者原状态，另列本次辅助核验范围')
        edit('comparison_decision', row['comparison_decision']+'；仅接收至公开价格观察层，非融通自有资产、非最终可比/训练样本；'+limitation,
             '限定使用层，不作甲方已匹配或成交合同全部条款已核')
        edit('missing_reason', row['missing_reason']+'\n本次验收仍待核：'+limitation+'；'+('同轮直接编号桥待补。' if key=='NJ03' else '')+
             ('已知重复关系：'+'；'.join(source_matches) if source_matches else ''), '保留旧缺失和重复溯源，未知不补0')
        accepted.append(clone)
    write(out/'B02_逐条验收记录.csv', audit)
    write(out/'B02_字段证据摘录.csv', quotes)
    write(out/'B02_可接收公开观察_28字段.csv', accepted, fields)
    write(out/'B02_验收副本修改日志.csv', changes)
    write(out/'B02_既有观察重复关系_不删记录.csv', overlaps)
    assert len(overlaps) == 4 and len(set(x['B02观察ID'] for x in overlaps)) == 3
    assert all(row['effective_rent']=='' and row['related_party']=='' for row in accepted)
    # B01本轮只做收件、结构及算术检查，不把成员自报的逐原件核验当成本次重验。
    b01_formula = []
    for row in b01:
        price = Decimal(re.search(r'[\d,]+(?:\.\d+)?', row['raw_price_unit'])[0].replace(',',''))
        denominator = Decimal(re.search(r'[\d,]+(?:\.\d+)?', row['area_building_chargeable_land'])[0].replace(',',''))
        if row['monthly_normalized']:
            value = Decimal(re.search(r'\d+(?:\.\d+)?', row['monthly_normalized'])[0])
            expected = price/12/denominator
            assert abs(value-expected) <= Decimal('.00005'),row['observation_id']
            conclusion = '明示金额及披露面积公式一致；未逐原件独立复核'
        else:
            value = ''
            conclusion = '名义单价留空；不自补计租分母'
        b01_formula.append({'观察ID':row['observation_id'],'原年价元':str(price),
                            '表列披露面积㎡':str(denominator),'原名义单价':str(value),
                            '本次检查':conclusion})
    assert len(b01)==15 and sum(bool(x['monthly_normalized']) for x in b01)==14
    write(out/'B01_收件及算术初查_非原件验收.csv', b01_formula)
    assert before == {rel(p):sha(p) for p in protected},'原始提交或共享底表被修改'
    summary = {'批次':'2026-11-10首批成员材料验收','时间':datetime.now().astimezone().isoformat(timespec='seconds'),
               'B02候选标的数':6,'B02价格观察数':10,'挂牌观察':6,'成交公示观察':4,
               '证据HTML数量':10,'证据哈希与索引一致数':10,'月单价复算一致数':10,
               '公开价格观察接收':9,'跨编号成交分母条件接收':1,'费用冲突涉及观察数':2,
               '既有重复观察数':3,'重复关系条数':4,
               'B01本次结构检查观察数':15,'B01明示公式一致数':14,'B01保持空单价数':1,
               'B01所持47行底表与当前共享表字段及逐值相等':True,
               '输入文件哈希':before,'原始提交及共享底表保持':True,
               '接收边界':'仅公开价格观察及助手限定核对，不是成员人工签核、最终可比筛选或正式合库；未实时逐页回网；未取得签署合同',
               '配对边界':'NJ03两条跨编号关联有多要素支持，直接编号桥及独立同轮确认仍待补',
               'C02_Y02边界':'本次另做材料盘点和既有复核状态汇总，未声称重新验收全部原件'}
    (out/'验收运行记录.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    print(json.dumps(build(parser.parse_args().out),ensure_ascii=False,indent=2))
