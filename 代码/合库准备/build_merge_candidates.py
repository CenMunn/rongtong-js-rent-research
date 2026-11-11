"""Offline, non-destructive observation inventory and linkage candidates. No training."""
import argparse
import csv
import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BASE = '成员成果/王玮/成员成果验收'
WX = '成员成果/王玮/Y01/公众号整理版_v2/公众号采集结果_整理版_v2.csv'
B01 = BASE + '/2026-11-10_首批/原始提交展开/B01_20261108/B01_统一采集表.csv'
B01_REVIEW = BASE + '/2026-11-10_B01重点5条/重点5条_28字段复核副本.csv'
B02 = BASE + '/2026-11-10_首批/B02_可接收公开观察_28字段.csv'
X03 = '成员成果/王玮/X03/2026-11-09_首批样例/统一填写样例_真实9条.csv'
C02 = '成员成果/游依宸/C02_汉桑禾盛/C02_结构化历史合同表.csv'
SHARED = '共享资料/南京苏州交易明细.csv'
ASK = '成员成果/席风翔/项目证据/苏州外部挂牌候选/挂牌明细.json'
C03 = BASE + '/2026-11-11_C03高力补证/13条指标接收状态更新版.csv'
B03 = BASE + '/2026-11-10_B03_C04_v2接收/原始反馈/B03_首批样本条款核验表_v2.csv'
Y02 = '成员成果/游依宸/Y02_珍珠北路/Y02_历轮条件对照表.csv'
LAYER = '成员成果/王玮/Y01/省域分层与状态汇总_2026-11-10/逐条省域与核验状态索引.csv'
CHECK_PATH = ROOT / '代码/数据质量检查/check_data_v1_3.py'
spec = importlib.util.spec_from_file_location('quality_v13', CHECK_PATH)
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


def price_kind(text):
    if any(s in text for s in ['无明确价格', '面议', '无价']):
        return 'NO_PRICE'
    if '关联方' in text:
        return 'RELATED_CONTRACT'
    if '调租' in text:
        return 'CONTRACT_ADJUSTMENT'
    if '成交' in text:
        return 'PUBLISHED_TRANSACTION'
    if '合同' in text:
        return 'DISCLOSED_CONTRACT'
    if '底价' in text or '起拍' in text:
        return 'RESERVE_PRICE'
    if '挂牌' in text or '报价' in text:
        return 'ASKING_PRICE'
    return 'UNCLASSIFIED'


def canonical_url(url):
    """Remove known WeChat tracking only; preserve identity query parameters."""
    u = urlsplit(url.strip())
    pairs = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if k not in {'chksm', 'scene', 'sessionid', 'from', 'isappinstalled'}]
    return u._replace(query=urlencode(sorted(pairs)), fragment='').geturl()


def numeric_price(text):
    parsed = quality.price_values(text)
    values = [(unit, value) for unit, entries in parsed.items() for value in entries]
    if len(values) != 1:
        return '', '', '原价无法唯一解析或有多值；不自动选值'
    unit, value = values[0]
    return str(value), {'年': '元/年', '月': '元/月', '㎡/月': '元/平方米/月'}[unit], '仅表达解析，非源值验收'


def row_uid(source, oid):
    return source + '::' + oid


def asset_uid(source, asset):
    return source + '::' + asset if asset else ''


def build(out):
    if out.exists():
        raise FileExistsError('禁止覆盖旧批次；请换 --out')
    inputs = {}
    mappings = []

    def read(rel):
        p = ROOT / rel
        inputs[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        with p.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def js(rel):
        p = ROOT / rel
        inputs[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return json.loads(p.read_text('utf-8-sig'))

    with (ROOT / '共享资料/统一采集空表.csv').open(encoding='utf-8-sig', newline='') as f:
        fields = next(csv.reader(f))
    inputs['共享资料/统一采集空表.csv'] = hashlib.sha256((ROOT / '共享资料/统一采集空表.csv').read_bytes()).hexdigest()
    assert len(fields) == 28
    inventory = []
    records = []
    by_uid = {}
    overlay_rows = []

    def add(source, rel, n, row, oid=None, asset=None, scope='江苏', evidence='成员提交；本轮未新增原件验收'):
        row = {f: row.get(f, '') for f in fields}
        oid = oid or row['observation_id']
        node = asset or row['asset_id']
        uid = row_uid(source, oid)
        assert uid not in by_uid, uid
        item = dict(row)
        item.update(source_record_uid=uid, source_dataset=source, source_file=rel,
                    source_data_row=str(n), source_observation_id=oid,
                    asset_node_uid=asset_uid(source, node), asset_node_basis='沿用来源ID或本表临时范围键，非正式跨库合并ID',
                    geographic_layer=scope, evidence_scope=evidence,
                    modeling_ready='否；本批仅准备候选，未批准训练或测试集')
        records.append(item)
        by_uid[uid] = item
        return item

    def mapfields(source, mapping):
        for target in fields:
            mappings.append({'来源集': source, '目标28字段': target,
                             '来源字段或规则': mapping.get(target, '未提供则留空；见来源原始记录'),
                             '处理': '另建派生视图，不覆盖来源；价格性质/面积/日期不得跨层补齐'})

    wx = read(WX)
    layers = {x['观察ID']: x for x in read(LAYER)}
    for source, rel in [('WX', WX), ('B01', B01), ('B02', B02), ('X03', X03)]:
        rows = wx if source == 'WX' else read(rel)
        overrides = {x['observation_id']: x for x in read(B01_REVIEW)} if source == 'B01' else {}
        if overrides:
            assert len(overrides) == 5
        for n, row in enumerate(rows, 1):
            applied = overrides.get(row['observation_id'], row)
            add(source, rel, n, applied, scope=layers[row['observation_id']]['省域层'] if source == 'WX' else '江苏',
                evidence=(layers[row['observation_id']]['本轮复核状态'] if source == 'WX' else
                          ('已发布重点5条复核副本；覆盖范围仅指定字段' if row['observation_id'] in overrides else
                           '沿用本批已发布接收状态；未扩大人工签核')))
            if row['observation_id'] in overrides:
                overlay_rows.append({'来源记录UID': row_uid(source, row['observation_id']), '补充来源': B01_REVIEW,
                                     '关系': '同一观察的已发布复核副本', '应用': '派生视图使用复核副本；原提交不改'})
        mapfields(source, {f: f for f in fields})
        inventory.append({'来源集': source, '来源文件': rel, '原记录数': len(rows), '价格观察候选数': len(rows),
                          '粒度': '物业/范围×价格观察；保留历史与重复候选', '用途': '逐条分层，不直接认定训练样本'})

    for n, r in enumerate(read(C02), 1):
        aid = ('HS7F1' if r['观察ID'] in ['C02-HS-01', 'C02-HS-02'] else
               'HSHE-ZJ9' if r['观察ID'].startswith('C02-HSHE') else r['观察ID'])
        mapped = dict(asset_id='', observation_id=r['观察ID'], lessor_entity=r['出租方'],
                      rongtong_relation='外部合同披露参考，非融通自有', use_legal_actual='披露用途=' + r['用途'],
                      address_scope_floor=r['地址及范围'],
                      area_building_chargeable_land=('披露面积=' + r['面积㎡'] + '㎡；计租/建筑类型待核') if r['面积㎡'] else '',
                      price_type=r['价格性质'], raw_price_unit=r['原价'] + r['原单位'],
                      publish_sign_start_end_dates=r['价格期间'], related_party=r['关联关系'], tax_fee=r['费用税费'],
                      monthly_normalized=r['名义月单价元每㎡月'], source_url_page=r['原件定位'],
                      verification_status=r['核验状态'], comparison_decision=r['比较决定'], missing_reason=r['缺失与限制'])
        add('C02', C02, n, mapped, asset=aid, evidence='成员原件披露转录；HS-01另有既存指定字段辅助核对，其余未扩大验收')
    mapfields('C02', {'asset_id': '原表无正式资产ID，留空；临时范围键仅另列asset_node_uid',
                     'observation_id': '观察ID', 'lessor_entity': '出租方', 'address_scope_floor': '地址及范围',
                     'area_building_chargeable_land': '面积㎡，仅标披露面积；不猜计租', 'price_type': '价格性质',
                     'raw_price_unit': '原价+原单位；多值保留', 'publish_sign_start_end_dates': '价格期间，非采集日',
                     'related_party': '关联关系', 'tax_fee': '费用税费', 'source_url_page': '原件定位（可能只有本地页码）',
                     'monthly_normalized': '名义月单价元每㎡月；仅照录，不补单位到未知表达',
                     'rongtong_relation': '固定标外部合同披露参考，非融通自有',
                     'use_legal_actual': '用途，标为披露用途而非合法用途',
                     'verification_status': '核验状态', 'comparison_decision': '比较决定', 'missing_reason': '缺失与限制'})
    inventory.append({'来源集': 'C02', '来源文件': C02, '原记录数': 6, '价格观察候选数': 6,
                      '粒度': '合同披露价格期间；一条宿舍记录含两期房间报价', '用途': '历史合同、调租、关联价和间/月分列'})

    shared = read(SHARED)
    shared_count = 0
    for n, r in enumerate(shared, 1):
        for code, pricecol, kind, urlcol, datecol in [
                ('P', '挂牌或公示底价元每年', '挂牌底价', '挂牌原文', '挂牌日期或归档日'),
                ('C', '成交元每年', '成交公示年租金', '成交原文', '成交日期')]:
            if not r[pricecol].strip():
                continue
            oid = f'SH47-{n:03}-{code}'
            mapped = dict(asset_id='', observation_id=oid, round_contract_id=r['挂牌编号或标识'] + '；' + r['成交编号'],
                          lessor_entity=r['出租方'], rongtong_relation='外部公开观察，关系待核',
                          address_scope_floor=r['标的归并名'] + '；' + r['物业或范围'],
                          area_building_chargeable_land=('披露面积=' + r['同轮出租面积㎡'] + '㎡') if r['同轮出租面积㎡'] else '',
                          price_type=kind, raw_price_unit=r[pricecol] + '元/年',
                          publish_sign_start_end_dates=r[datecol], source_url_page=r[urlcol],
                          verification_status='历史共享试采，未逐行新增原件核验', comparison_decision='仅候选；须关联后续补证版本',
                          missing_reason=r['口径说明'])
            add('SH47', SHARED, n, mapped, asset=f'ROW{n:03}', evidence='早期试采汇总；拆开挂牌/成交，不视为两笔成交')
            shared_count += 1
    mapfields('SH47', {'observation_id': '由原数据行号+P/C生成，非官方观察编号',
                      'raw_price_unit': '挂牌或公示底价元每年 / 成交元每年分别拆成观察',
                      'address_scope_floor': '标的归并名+物业或范围', 'area_building_chargeable_land': '同轮出租面积㎡，仅披露口径',
                      'source_url_page': 'P取挂牌原文，C取成交原文', 'publish_sign_start_end_dates': 'P取挂牌日期或归档日，C取成交日期',
                      'round_contract_id': '挂牌编号或标识+成交编号；原字段保留，不当同一编号',
                      'lessor_entity': '出租方', 'rongtong_relation': '固定标外部公开观察，关系待核',
                      'price_type': 'P=挂牌底价，C=成交公示年租金',
                      'verification_status': '固定标历史共享试采、未新增逐原件核验',
                      'comparison_decision': '固定标仅候选、须关联后续补证版本', 'missing_reason': '口径说明'})
    inventory.append({'来源集': 'SH47', '来源文件': SHARED, '原记录数': len(shared), '价格观察候选数': shared_count,
                      '粒度': '每行可含挂牌和成交两个观察，历史表不改', '用途': '关联/补证索引；尚未逐行准入'})

    asks = js(ASK)
    for n, r in enumerate(asks, 1):
        mapped = dict(observation_id=f'ASK-SZ-{n:02}', address_scope_floor=r['项目名称'] + '；' + r['坐落位置'] + '；' + r['所在楼层'],
                      area_building_chargeable_land='数量=' + r['数量'] + r['数量单位'] + '；含义以原文为准',
                      price_type='挂牌底价', raw_price_unit=r['租金挂牌底价'], publish_sign_start_end_dates=r['发布日期'],
                      source_url_page=r['原网址'] + '；' + '成员成果/席风翔/项目证据/苏州外部挂牌候选/' + r['项目正文'],
                      rongtong_relation='苏州外部挂牌候选', verification_status='成员新增自动采集；本轮未逐原件验收',
                      missing_reason='数量单位与资产范围待核；尚未做目标资产可比筛选')
        add('ASK9', ASK, n, mapped, asset=f'ROW{n:02}', evidence='新增挂牌索引；不等于成交或独立可比')
    mapfields('ASK9', {'observation_id': '生成ASK-SZ序号，非官方编号', 'raw_price_unit': '租金挂牌底价原样保留；无/年不补年',
                      'area_building_chargeable_land': '数量+数量单位；“个”不转平方米',
                      'address_scope_floor': '项目名称+坐落位置+所在楼层', 'publish_sign_start_end_dates': '发布日期',
                      'source_url_page': '原网址+原采集文本相对路径', 'price_type': '固定标挂牌底价',
                      'rongtong_relation': '固定标苏州外部挂牌候选', 'verification_status': '固定标成员自动采集、本轮未原件验收',
                      'missing_reason': '固定说明数量、范围和可比尚待核'})
    inventory.append({'来源集': 'ASK9', '来源文件': ASK, '原记录数': len(asks), '价格观察候选数': len(asks),
                      '粒度': '外部挂牌线索；包含平方米及点位单位', '用途': '待原件和数量口径复筛'})

    # Auxiliary tables supplement observations; never count them as additional deals.
    b03 = read(B03)
    terms = []
    for r in b03:
        matches = [x for x in records if x['source_observation_id'] == r['观察ID']]
        assert len(matches) == 1, r['观察ID']
        for f in ['租期及支付', '免租或装修期', '递增', '税费及其他费用', '出租范围及交付', '押金或保证金', '未解决项及使用限制']:
            terms.append({'来源记录UID': matches[0]['source_record_uid'], '补充表': B03, '补充字段': f,
                          '值': r[f], '应用限制': '挂牌披露不冒充成交签署合同；不新增价格观察、不自动覆写'})
    overlays = [('B03', B03, len(b03), '同观察条款补充，7条不重复计样'),
                ('C03', C03, len(read(C03)), '城市/机构/业态/统计期市场指标；独立背景表'),
                ('Y02', Y02, len(read(Y02)), '轮次与公众号观察关联；不重记成交')]
    for source, rel, count, use in overlays:
        inventory.append({'来源集': source, '来源文件': rel, '原记录数': count, '价格观察候选数': 0,
                          '粒度': use, '用途': use})

    # Field/range-specific review support; no global "all manually approved" flag.
    reviewed_b01 = {x['observation_id'] for x in read(B01_REVIEW)} | {'CYF-B01-CJ-N0117FCZZ250804-4'}
    b02_checks = {x['观察ID']: x for x in read(BASE + '/2026-11-10_首批/B02_逐条验收记录.csv')}
    review_rows = []
    for x in records:
        source, oid = x['source_dataset'], x['source_observation_id']
        kind = price_kind(x['price_type'])
        amount, unit, parse_note = numeric_price(x['raw_price_unit'])
        x.update(price_nature_code=kind, parsed_price=amount, parsed_price_unit=unit, price_parse_note=parse_note)
        # Numeric view of already-stated monthly values only, never fill unknown denominator.
        m = re.match(r'^([\d,]+(?:\.\d+)?)', x['monthly_normalized'])
        normalized = m[1].replace(',', '') if m else ''
        arithmetic = []
        def flag(code, level, message):
            arithmetic.append(code + ':' + message)
        if x['monthly_normalized']:
            quality.check_normalized(x['monthly_normalized'], x['raw_price_unit'], x['area_building_chargeable_land'], flag)
        monthly_note = '既有名义数值照录；非有效租金' if normalized else '缺少已填名义平方米月价，不在本批猜分母'
        status = '待源值/范围复核'
        reason = '本轮整理字段与关联，未扩大原件验收'
        if kind in {'RESERVE_PRICE', 'ASKING_PRICE'}:
            status, reason = '底价/挂牌参考层', '可用于自身定价对照或外部报价背景，不能当真实成交标签'
        if source == 'WX':
            if x['geographic_layer'] != '江苏':
                status, reason = '省外或省域待定隔离', '省外/待定观察保留，不混入江苏模型候选'
            elif kind == 'NO_PRICE':
                status, reason = '无价线索层', '未披露数值，未知不填0'
        if source == 'B01' and oid in reviewed_b01:
            status, reason = '公开成交名义候选，待可比筛选', '既有指定字段辅助核验；实际计租/合同/税费未齐'
        if source == 'B02' and kind == 'PUBLISHED_TRANSACTION':
            status, reason = '公开成交名义候选，待可比筛选', b02_checks[oid]['费用与范围限制']
        if source == 'X03' and kind == 'PUBLISHED_TRANSACTION':
            status, reason = '公开成交名义候选，待可比筛选', '沿用原文抽核观察；跨表重复及日期/范围仍须处理'
        if kind in {'DISCLOSED_CONTRACT', 'CONTRACT_ADJUSTMENT'}:
            status, reason = '历史合同候选，待期间与费用筛选', '披露合同不等于实收；不同期间保留，不解释为城市趋势'
        if kind == 'RELATED_CONTRACT' or (source == 'X03' and oid == 'O06'):
            status, reason = '关联方及费用混合背景隔离', '关联方且18.5含物业等费用，不能当独立净租金标签'
        blocks = []
        if source == 'B01' and '231107' in oid:
            blocks.append('湖南路2023地下空间与6300㎡关系未定；单价留空')
        if source == 'B01' and '240212' in oid:
            blocks.append('湖南路2024分段交付与免租；仅全范围名义分摊，不自动准入')
        if (source == 'B02' and oid == 'B02-NJ03-C') or (source == 'X03' and oid == 'O02'):
            blocks.append('珠江路同轮跨编号面积桥未补；跨表不能消除问题')
        if source == 'WX' and oid in {'WX-20261108-000127', 'WX-20261108-000136', 'WX-20261108-000510'}:
            blocks.append('已登记图文金额/面积差异未定；不选正式采用值')
        if '元/间/月' in x['raw_price_unit'] or (source == 'ASK9' and '个' in x['area_building_chargeable_land']):
            blocks.append('数量单位为间或个，不进入平方米回归')
            normalized = ''
        if blocks:
            status, reason = '条件限制或单位隔离', '；'.join(blocks)
        if kind == 'NO_PRICE' or not amount:
            normalized = '' if kind == 'NO_PRICE' else normalized
        x.update(existing_monthly_numeric=normalized, monthly_value_scope=monthly_note,
                 arithmetic_messages='；'.join(arithmetic), preparation_layer=status,
                 preparation_reason=reason, actual_chargeable_area_confirmed='未由本批确认',
                 feature_availability_cutoff='待定；保留发布时间/价格期间原文，不用采集日冒充',
                 leakage_note='成交价作为目标时，不用成交后条款/结果/未来市场期；同资产关联组须整体隔离')
        manual = ''
        if source == 'B01' and oid == 'CYF-B01-CJ-N0117FCZZ250441':
            manual = '王玮已确认编号、披露面积、成交年租金、名义换算4字段；不扩展税费/合同'
        if source == 'X03' and oid in {'O01', 'O04', 'O06'}:
            manual = '王玮已确认指定原文及字段；范围见原verification_status，不扩展其他记录'
        review_rows.append({'来源记录UID': x['source_record_uid'], '价格性质': kind,
                            '准备层': status, '原因': reason, '原名义单价': x['monthly_normalized'],
                            '原价解析': parse_note, '已有字段人工确认范围': manual,
                            '训练准入': x['modeling_ready'], '原件与字段限制': x['missing_reason']})

    links = []
    def link(left, right, relation, basis, confidence='候选，待确认', applies='关系登记，不删行、不合并金额'):
        assert left in by_uid and right in by_uid, (left, right)
        if left == right:
            return
        links.append({'左记录UID': left, '右记录UID': right, '关系类型': relation,
                      '依据': basis, '关系状态': confidence, '处理': applies})

    # Existing explicit relationships, with uncertain ones kept uncertain.
    for a, b in [('O04', 'C02-HS-01'), ('O05', 'C02-HS-02'), ('O06', 'C02-HS-03'),
                 ('O07', 'C02-HSHE-01'), ('O08', 'C02-HSHE-02')]:
        link(row_uid('X03', a), row_uid('C02', b), '同资产同价格期间的跨表转录候选',
             '原文抽核观察与C02同门牌范围、原价、单位及价格期间对应；并非独立新增合同', '既有明确对应，正式统一ID待确认')
    for source, pairs in [('X03', [('O04', 'O05'), ('O07', 'O08')]),
                          ('C02', [('C02-HS-01', 'C02-HS-02'), ('C02-HSHE-01', 'C02-HSHE-02')])]:
        for a, b in pairs:
            link(row_uid(source, a), row_uid(source, b), '同资产不同价格期间',
                 '来源表明确同资产；保留每期，不作重复删除', '来源已说明；范围仍沿用披露')
    link('B02::B02-NJ02-C', 'B01::CYF-B01-CJ-N0117FCZZ250804-4', '同轮成交跨表重复候选',
         '已发布B02既有重复关系表，同轮编号及年租金额对应', '既有关系已登记，最终统一ID待确认')
    for b02, row, code in [('B02-NJ02-C', 6, 'C'), ('B02-NJ03-P', 28, 'P'), ('B02-NJ03-C', 29, 'C')]:
        target = f'SH47::SH47-{row:03}-{code}'
        if target in by_uid:
            link('B02::' + b02, target, '共享表与后续补证重复候选',
                 '已发布B02_既有观察重复关系_不删记录.csv；跨编号限制原样保留')
    # Exact URL + nature + price is only a review lead: batch URLs can include multiple assets.
    url_index = defaultdict(list)
    existing_pairs = {frozenset((z['左记录UID'], z['右记录UID'])) for z in links}
    for x in records:
        if not x['parsed_price']:
            continue
        for url in set(re.findall(r'https?://[^\s|；<>"，]+', x['source_url_page'])):
            url_index[(canonical_url(url), x['price_nature_code'],
                       str(Decimal(x['parsed_price']).normalize()), x['parsed_price_unit'])].append(x)
    for key, entries in url_index.items():
        for i, left in enumerate(entries):
            for right in entries[i + 1:]:
                pair = frozenset((left['source_record_uid'], right['source_record_uid']))
                if left['source_dataset'] == right['source_dataset'] or pair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                link(left['source_record_uid'], right['source_record_uid'], '同网址同性质同金额的跨表待核关联',
                     key[0] + '；金额/单位相同，仍须核包范围、面积和价格期间；批量网址不能独立证明同资产')
    # Same source asset IDs imply repeated asset-level observations, not duplicate prices.
    groups = defaultdict(list)
    for x in records:
        if x['asset_node_uid']:
            groups[x['asset_node_uid']].append(x['source_record_uid'])
    for node, uids in groups.items():
        if len(uids) > 1:
            for uid in uids[1:]:
                link(uids[0], uid, '来源内同资产ID的多观察',
                     node + '；ID可能为临时生成，不保证跨期范围完全一致')

    # Round-to-WX links are only supplemental metadata; WX-PUB is not an official package ID.
    round_links = []
    for r in read(Y02):
        ids = re.findall(r'WX-\d{8}-\d{6}', r['公众号观察ID'])
        for oid in ids:
            uid = 'WX::' + oid
            assert uid in by_uid
            round_links.append({'来源记录UID': uid, '补充来源': Y02, '轮次ID': r['轮次ID'],
                                '官方资产包编号': r['官方资产包编号'], '关系': '同轮元数据候选；非新增价格观察',
                                '结果状态原文': r['结果状态'], '核验边界': r['证据状态'] + '；不把转录流拍状态当实证负样本'})

    # X01/X02 link by existing source IDs, never use conditions to create extra price labels.
    card_links = []
    for filename in ['南京_板仓街328号.csv', '苏州_名人广场包1.csv']:
        rel = '成员成果/席风翔/X02_资产条件卡/' + filename
        p = ROOT / rel
        inputs[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        rr = list(csv.reader(p.open(encoding='utf-8-sig', newline='')))
        rows = [dict(zip(rr[2], z)) for z in rr[3:]]
        aid = next(z['值'] for z in rows if z['字段'] == 'asset_id')
        matches = [z for z in records if z['source_dataset'] == 'WX' and z['asset_id'] == aid]
        for z in matches:
            card_links.append({'条件卡': rel, '来源记录UID': z['source_record_uid'], '来源资产ID': aid,
                               '关联状态': 'ID引用相符，公告轮次/包范围须复核后应用条款',
                               '应用限制': '仅条件补充候选；X02待成员回填v2，不自动覆盖所有历史期'})
        inventory.append({'来源集': 'X02', '来源文件': rel, '原记录数': len(rows), '价格观察候选数': 0,
                          '粒度': '字段条件卡，不是42个物业或新价格样本', '用途': '按范围和轮次补充条件，待v2'})
    for rel, name in [('成员成果/席风翔/C01_产品适用性核查/核查总表.csv', 'C01'),
                      ('成员成果/席风翔/X01_资产身份与主体关系/资产主表.csv', 'X01'),
                      ('成员成果/席风翔/Y03_定向补缺原帖/原帖台账.csv', 'Y03')]:
        p = ROOT / rel
        inputs[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        rr = list(csv.reader(p.open(encoding='utf-8-sig', newline='')))
        inventory.append({'来源集': name, '来源文件': rel, '原记录数': len(rr) - 3, '价格观察候选数': 0,
                          '粒度': '产品核查/资产候选/线索登记，非独立价格标签', '用途': '只作来源、身份或原帖定位辅助'})

    # Link candidates get a source-local leakage group; cross-table identity is not resolved.
    relation_counts = Counter()
    for edge in links:
        relation_counts[edge['左记录UID']] += 1
        relation_counts[edge['右记录UID']] += 1
    for x in records:
        x['link_candidate_count'] = str(relation_counts[x['source_record_uid']])
        x['provisional_split_group'] = x['asset_node_uid'] or x['source_record_uid']
        x['split_group_limit'] = '仅来源内临时组；正式切分前须处理跨表关联，不可直接随机切行'

    out.mkdir(parents=True)
    def write(name, rows, headers=None):
        assert rows or headers, name
        with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=headers or list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    write('合库候选_28字段及来源.csv', records)
    write('建模准备分层清单.csv', review_rows)
    write('资产观察关联候选.csv', links)
    write('同观察条款补充关联.csv', terms)
    write('同观察已发布复核副本关联.csv', overlay_rows)
    write('官方轮次补充关联.csv', round_links)
    write('条件卡与公众号关联候选.csv', card_links)
    write('28字段来源映射.csv', mappings)
    write('来源粒度与计数.csv', inventory)
    write('市场指标_独立背景层.csv', read(C03))
    summary = []
    for (source, kind, layer), count in sorted(Counter((x['source_dataset'], x['price_nature_code'], x['preparation_layer']) for x in records).items()):
        summary.append({'来源集': source, '价格性质': kind, '准备层': layer, '观察记录数_非独立样本': count})
    write('候选分层汇总.csv', summary)
    taxonomy = [
        ('PUBLISHED_TRANSACTION', '公开成交公示价', '公开成交名义单价候选', '非签署合同或实收；费用及计租另核'),
        ('DISCLOSED_CONTRACT', '法律文件/公司披露合同价', '对应历史期间的合同名义候选', '不可当当前价；面积及费用保留'),
        ('CONTRACT_ADJUSTMENT', '合同调租价', '历史调租观察', '与原合同同资产，不当城市涨跌'),
        ('RELATED_CONTRACT', '关联方合同价', '单列背景', '关联交易及费用混合，不能冒充独立市场净租金'),
        ('RESERVE_PRICE', '招租/挂牌底价', '自身定价或外部底价参考', '不能代替成交训练标签'),
        ('ASKING_PRICE', '一般挂牌报价', '报价参考', '要约不等于成交'),
        ('NO_PRICE', '无价/面议/OCR线索', '线索层', '未知不填0'),
        ('UNCLASSIFIED', '性质未确定', '待分类', '不因出现数字就认定租金'),
    ]
    write('价格性质与用途规则.csv', [{'代码': a, '含义': b, '允许用途': c, '限制': d} for a, b, c, d in taxonomy])
    write('来源文件哈希.csv', [{'来源文件': p, 'SHA256': s} for p, s in inputs.items()])
    totals = Counter(x['preparation_layer'] for x in records)
    stats = {'version': '0.1', 'built_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
             'observations_not_independent_samples': len(records), 'by_source': dict(Counter(x['source_dataset'] for x in records)),
             'by_layer': dict(totals), 'link_candidates': len(links), 'market_indicators_separate': 13,
             'training_admission_performed': False, 'deduplication_performed': False,
             'originals_modified': False, 'source_hashes': inputs}
    for path, digest in inputs.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    assert len(by_uid) == len(records)
    assert all(x['modeling_ready'].startswith('否') for x in records)
    assert len([x for x in records if x['source_dataset'] == 'WX']) == 1157
    assert all(x['effective_rent'] == '' for x in records)
    (out / '运行摘要.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in stats.items() if k != 'source_hashes'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    build(parser.parse_args().out.resolve())
