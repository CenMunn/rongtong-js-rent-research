"""按统一采集字段离线检查CSV，保留原始文件。仅使用Python标准库。"""
import argparse
import csv
import hashlib
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
VERSION = '1.3'
NUM = r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
RULES = [
 ('S01','错误','表结构','缺少模板字段、重复表头或行列错位'),
 ('S02','提示','表结构','多出字段保留并提示'),
 ('I01','错误','asset_id / observation_id','资产ID或观察ID为空'),
 ('I02','错误','observation_id','观察ID重复；资产ID重复允许多期观察'),
 ('P01','需复核','price_type','缺少或无法识别价格性质'),
 ('P02','需复核','raw_price_unit','报价缺原价单位，或无价记录却有计算单价'),
 ('P03','需复核','raw_price_unit','明示年价相互冲突、数值格式存疑或金额非正'),
 ('A01','需复核','address_scope_floor / area_building_chargeable_land','地址或面积信息空白；负面积待核，零建筑面积保留'),
 ('U01','错误','monthly_normalized','明示公式的面积分母非正或单价与公式/原文直录值不符'),
 ('U02','需复核','monthly_normalized','无法解析单价、源价格/单位不匹配或公式面积不一致'),
 ('U03','提示','monthly_normalized','当前有价记录未填单价，待满足面积及单位条件再算'),
 ('D01','需复核','collection_date / publish_sign_start_end_dates','采集日期缺失、无法识别或明示日期不存在'),
 ('L01','错误','source_url_page','未填写来源'),
 ('L02','需复核','source_url_page','仅本地存档或未发现HTTP(S)网址，需核共享位置及出处；不检测网络可达性'),
 ('V01','需复核','verification_status','缺核验状态或原状态仍含待核／需复核等事项'),
 ('R01','需复核','missing_reason','关键字段缺失但没有缺失原因'),
]

def decimal(text):
    return Decimal(text.replace(',', ''))

def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            # 防止原文以公式字符开头时被表格软件执行。
            writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value
                             for key, value in row.items()})

def annual_prices(text):
    values = set()
    for line in text.splitlines():
        if '保证金' in line or re.search(r'\d\.\s+\d', line):
            continue
        for match in re.finditer(r'(?<![\d.,])(' + NUM + r')\s*(万元|元)\s*/\s*(首年|年)', line):
            value = decimal(match[1])
            values.add(value * (10000 if match[2] == '万元' else 1))
    return values

def price_values(text):
    """识别年总租、月总租和直接平方米月价；保证金行不作为租金。"""
    values = {'年': set(), '月': set(), '㎡/月': set()}
    canonical = text.replace('平方米', '㎡').replace('m²', '㎡').replace('㎡月', '㎡/月').replace('·', '/')
    for line in canonical.splitlines():
        if '保证金' in line or re.search(r'\d\.\s+\d', line):
            continue
        for match in re.finditer(r'(?<![\d.,])(' + NUM + r')\s*(万元|元)\s*/\s*(㎡/月|首年|年|月)(?![\w/])', line):
            values['年' if match[3]=='首年' else match[3]].add(decimal(match[1])*(10000 if match[2]=='万元' else 1))
    return values

def check_simple_normalized(unit, raw, area, flag):
    """仅从单一明示年/月总额和单一披露面积检查名义分摊，不生成计租结论。"""
    unit = unit.replace('平方米', '㎡').replace('m²', '㎡')
    shown = re.fullmatch('('+NUM+r')(?:\s*元/(?:披露)?㎡/月(?:[（(][^()（）]*[）)])?)?',unit)
    rent = re.fullmatch('('+NUM+r')\s*(万元|元)/(年|首年|月)',raw)
    areas = list(re.finditer('('+NUM+r')\s*(?:㎡|平方米|m²)',area))
    labels = r'公告(?:租赁|出租|建筑)面积|披露面积|建筑面积|房屋面积|计租面积'
    start = re.match(r'^(?:(?:'+labels+r')(?:约)?\s*[=：:]?\s*)?('+NUM+r')\s*(?:㎡|平方米|m²)',area)
    ambiguous = re.search(r'包含关系|冲突|实测|[~～]|至\s*\d|[—-]\s*\d',area)
    if not shown or not rent or len(areas)!=1 or not start or not re.search(labels,area) or ambiguous:
        flag('U02','需复核','非固定公式表达无法唯一对应单一总租和披露面积，保留待核，不猜分母或单位')
        return 0
    denominator=decimal(start[1])
    if denominator<=0:
        flag('U01','错误','披露面积分母非正')
        return 0
    observed=decimal(shown[1])
    numerator=decimal(rent[1])*(10000 if rent[2]=='万元' else 1)
    expected=numerator/(12 if rent[3] in ['年','首年'] else 1)/denominator
    tolerance=max(Decimal('0.000001'),Decimal(1).scaleb(observed.as_tuple().exponent)/2)
    if abs(observed-expected)>tolerance:
        flag('U01','错误','单价与单一明示总租和披露面积不符，按显示精度检查')
    return 1

def check_normalized(unit, raw, area, flag):
    """返回已执行算术/直录检查的条数；源值和计租范围仍由原件确认。"""
    source = price_values(raw)
    display = re.match(r'^(' + NUM + r')\s*元/(建筑|计租|披露)?㎡/月', unit)
    annual = list(re.finditer(r'公式\s*[=：]\s*(' + NUM + r')\s*元/年\s*[÷/]\s*12\s*[÷/]\s*(' + NUM + r')\s*㎡', unit))
    monthly = list(re.finditer(r'公式\s*[=：]\s*(' + NUM + r')\s*元/月\s*[÷/]\s*(' + NUM + r')\s*㎡', unit))
    direct = list(re.finditer(r'原文直录\s*[=：]\s*(' + NUM + r')\s*元/㎡/月', unit))
    if not display or len(annual)+len(monthly)+len(direct)!=1:
        if not re.search('公式|原文直录',unit):
            return check_simple_normalized(unit,raw,area,flag)
        flag('U02','需复核','仅校验年总租÷12÷面积、月总租÷面积或原文直录的平方米月价；其他表达待核')
        return 0
    observed = decimal(display[1])
    tolerance = max(Decimal('0.000001'), Decimal(1).scaleb(observed.as_tuple().exponent)/2)
    if direct:
        value = decimal(direct[0][1])
        if value not in source['㎡/月']:
            flag('U02','需复核','原文直录值未与原价字段中的平方米月价对应；间/月等单位不得转成平方米月价')
        if abs(observed-value)>tolerance:
            flag('U01','错误','显示单价与明示原文直录值不一致')
        return 1
    match, period = (annual[0], '年') if annual else (monthly[0], '月')
    numerator, denominator = decimal(match[1]), decimal(match[2])
    equivalent = source[period] | ({x*12 for x in source['月']} if period=='年' else {x/12 for x in source['年']})
    if numerator not in equivalent:
        flag('U02','需复核','公式金额未与原价字段的金额及年/月单位对应，或原价仅为保证金/其他单位')
    label = display[2]
    labels = {'建筑': '建筑或房屋面积|建筑面积|房屋面积', '计租': '计租面积',
              '披露': '披露面积', None: '建筑或房屋面积|建筑面积|房屋面积|计租面积|披露面积'}[label]
    areas = [decimal(m[1]) for m in re.finditer(r'(?:'+labels+r')\s*[=：:]\s*('+NUM+r')\s*(?:㎡|平方米)',area)]
    if denominator not in areas:
        flag('U02','需复核','公式面积未与指定建筑/计租/披露面积对应，需核分母口径')
    if denominator<=0:
        flag('U01','错误','明示公式的面积分母非正')
        return 0
    expected = numerator/(12 if period=='年' else 1)/denominator
    if abs(observed-expected)>tolerance:
        flag('U01','错误','单价与明示公式不一致，按显示精度检查舍入')
    return 1

def check(input_path, template_path, out):
    input_path, template_path, out = input_path.resolve(), template_path.resolve(), out.resolve()
    outputs = ['逐条质检结果.csv','问题明细.csv','人工复核清单.csv','质检规则.csv','质检摘要.md']
    if any(out / name in (input_path, template_path) for name in outputs):
        raise ValueError('输出位置与输入文件冲突')
    review_path = out / '人工复核清单.csv'
    if review_path.exists():
        with review_path.open(encoding='utf-8-sig', newline='') as handle:
            review_fields = ['原件值', '核对结论', '修正建议', '复核人', '复核日期']
            if any(any((row.get(key) or '').strip() for key in review_fields)
                   for row in csv.DictReader(handle)):
                raise ValueError('人工复核清单已有填写内容，为保留复核记录，请用 --out 指定新的结果目录')
    original_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    with template_path.open(encoding='utf-8-sig', newline='') as handle:
        expected = next(csv.reader(handle))
    with input_path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    findings, summary, manual = [], [], []

    def issue(number, row, code, severity, field, message):
        findings.append(dict(记录序号=number, observation_id=row.get('observation_id',''),
                             asset_id=row.get('asset_id',''), 规则=code, 级别=severity, 字段=field,
                             问题=message, 原值摘要=str(row.get(field,'') or '')[:600],
                             来源=row.get('source_url_page','')))

    for field in sorted(set(expected) - set(fields)):
        issue(0, {}, 'S01', '错误', field, '缺少模板字段')
    for field in sorted(set(fields) - set(expected)):
        issue(0, {}, 'S02', '提示', field, '模板外字段已保留在输入中')
    for field, count in Counter(fields).items():
        if count > 1:
            issue(0, {}, 'S01', '错误', field, '表头重复，需先修正副本后重跑')
    ids = Counter((row.get('observation_id') or '').strip() for row in rows)
    formula_checked = 0
    rank = {'错误':0, '需复核':1, '提示':2}
    for number, row in enumerate(rows, 1):
        start = len(findings)
        get = lambda key: (row.get(key) or '').strip()
        if None in row or any(value is None for value in row.values()):
            issue(number, row, 'S01', '错误', '', 'CSV行列数量与表头不符')
        for field in ['asset_id','observation_id']:
            if not get(field):
                issue(number,row,'I01','错误',field,'未填写ID')
        if get('observation_id') and ids[get('observation_id')] > 1:
            issue(number,row,'I02','错误','observation_id','同一观察ID出现多次，需核对来源及观察范围')
        kind = get('price_type')
        no_price = bool(re.search('无明确价格|无价|面议|未披露价格', kind))
        if not re.search('底价|起拍|挂牌|合同|成交|租赁价|调租价|估值|市场指标|无明确价格|无价|面议|未披露价格', kind):
            issue(number,row,'P01','需复核','price_type','需明确原价格性质')
        if kind and not no_price and not get('raw_price_unit'):
            issue(number,row,'P02','需复核','raw_price_unit','有价标签缺少原价与单位')
        if no_price and get('monthly_normalized'):
            issue(number,row,'P02','需复核','monthly_normalized','无明确价格或面议标签存在计算单价')
        raw = get('raw_price_unit')
        if raw and not no_price and not re.search(NUM + r'\s*(万元|元)\s*(?:/|每)\s*(?:首年|年|月|日|天|㎡|平方米|m²|间)',raw):
            issue(number,row,'P02','需复核','raw_price_unit','当前规则未识别完整金额与单位组合，需核原表头')
        annual = annual_prices(raw)
        all_prices = price_values(raw)
        if any(len(v)>1 or any(x<=0 for x in v) for v in all_prices.values()) or re.search(r'\d\.\s+\d',raw):
            issue(number,row,'P03','需复核','raw_price_unit','明示年价、非正金额或数值内空格需回原件核对')
        for field in ['address_scope_floor','area_building_chargeable_land']:
            if not get(field):
                issue(number,row,'A01','需复核',field,'字段为空，保留为待补记录')
        area = get('area_building_chargeable_land')
        if re.search(r'[=：:]\s*-\d', area):
            issue(number,row,'A01','需复核','area_building_chargeable_land','存在负面积，需核对是否识别错误')
        unit = get('monthly_normalized')
        if unit:
            formula_checked += check_normalized(unit, raw, area, lambda code,severity,message:
                issue(number,row,code,severity,'monthly_normalized',message))
        elif not no_price:
            issue(number,row,'U03','提示','monthly_normalized','未填名义月单价，保留年价或其他原始口径')
        try:
            datetime.fromisoformat(get('collection_date'))
        except ValueError:
            issue(number,row,'D01','需复核','collection_date','采集日期缺少或不符合ISO日期格式')
        dates = re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',get('publish_sign_start_end_dates'))
        if not dates:
            issue(number,row,'D01','需复核','publish_sign_start_end_dates','未识别到明示年月日，日期类型及原文待核')
        for date in dates:
            try:
                datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                issue(number,row,'D01','需复核','publish_sign_start_end_dates','明示日期不存在')
        source = get('source_url_page')
        if not source:
            issue(number,row,'L01','错误','source_url_page','来源为空')
        else:
            urls = re.findall(r'https?://[^\s<>"\u3000]+',source)
            valid = False
            for url in urls:
                try:
                    valid = valid or bool(urlsplit(url).hostname)
                except ValueError:
                    pass
            if not valid:
                issue(number,row,'L02','需复核','source_url_page','仅本地存档或未识别网址，需补可共享的原件定位及原始出处')
        verification = get('verification_status')
        if not verification or re.search(r'待核|需复核|未确认|未核|待[^\n；。]{0,40}复核|(?:尚未|未完成)[^\n；。]{0,20}复核',verification):
            issue(number,row,'V01','需复核','verification_status','原核验状态缺失或仍有待核事项；此规则不判断具体字段是否已核')
        core_missing = any(not get(k) for k in ['lessor_entity','address_scope_floor','area_building_chargeable_land','collection_date'])
        core_missing = core_missing or (not no_price and not raw)
        if core_missing and not get('missing_reason'):
            issue(number,row,'R01','需复核','missing_reason','关键字段缺失，需要写明原因')
        own = findings[start:]
        codes = list(dict.fromkeys(f['规则'] for f in own))
        severity = min((f['级别'] for f in own),key=rank.get) if own else '所检规则未发现问题'
        record = dict(记录序号=number,observation_id=get('observation_id'),asset_id=get('asset_id'),
                      价格性质=kind,检查结果=severity,错误数=sum(f['级别']=='错误' for f in own),
                      需复核数=sum(f['级别']=='需复核' for f in own),规则='、'.join(codes),
                      原核验状态=get('verification_status'),来源=source)
        summary.append(record)
        if any(f['级别'] in ['错误','需复核'] for f in own):
            specific = any(f['级别'] in ['错误','需复核'] and f['规则']!='V01' for f in own)
            manual.append(dict(记录序号=number,observation_id=get('observation_id'),asset_id=get('asset_id'),
                               优先级='优先' if specific else '常规',
                               待核事项='；'.join(dict.fromkeys(f['问题'] for f in own if f['级别']!='提示')),
                               来源=source,原件值='',核对结论='',修正建议='',复核人='',复核日期=''))
    assert original_hash==hashlib.sha256(input_path.read_bytes()).hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    summary_fields=['记录序号','observation_id','asset_id','价格性质','检查结果','错误数','需复核数','规则','原核验状态','来源']
    write_csv(out/outputs[0],summary_fields,summary)
    write_csv(out/outputs[1],['记录序号','observation_id','asset_id','规则','级别','字段','问题','原值摘要','来源'],findings)
    manual.sort(key=lambda r:(r['优先级']!='优先',r['记录序号']))
    write_csv(out/outputs[2],['记录序号','observation_id','asset_id','优先级','待核事项','来源','原件值','核对结论','修正建议','复核人','复核日期'],manual)
    write_csv(out/outputs[3],['规则','默认级别','字段','检查范围'],[dict(zip(['规则','默认级别','字段','检查范围'],r)) for r in RULES])
    counts=Counter(f['规则'] for f in findings)
    errors=sum(r['错误数']>0 for r in summary)
    file_errors=sum(f['记录序号']==0 and f['级别']=='错误' for f in findings)
    overall='存在文件结构错误' if file_errors else '存在记录错误' if errors else '所检规则无错误；待核事项另列'
    report=[f'# X03首批离线质检', '', f'规则版本 {VERSION}，运行时间 {datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")}。',
            '',f'输入文件 {input_path.name}，SHA256为 `{original_hash}`。原始文件哈希在检查前后相同。',
            '',f'共检查{len(rows)}行、{len(fields)}个字段，模板为{len(expected)}个字段。',
            f'文件结构错误{file_errors}项；总体状态：{overall}。',
            f'含错误的记录{errors}行，含需复核事项的记录{sum(r["需复核数"]>0 for r in summary)}行，人工队列{len(manual)}行。不同问题可能命中同一记录。',
            f'可解析的年总租/月总租换算或直接单价记录{formula_checked}行，已按显示精度执行算术/直录检查；源金额、单位或面积不匹配另列U02。',
            f'具体规则问题列为优先的记录{sum(r["优先级"]=="优先" for r in manual)}行，其余仅原表核验状态提示的记录{sum(r["优先级"]=="常规" for r in manual)}行。',
            '',f'非空资产ID的不同取值有{len(set(r.get("asset_id", "") for r in rows)-{""})}个。这是当前候选ID的计数，资产范围仍待核实。',
            '', '本次检查表结构、明示文本、核验状态和可解析公式，网址仅检查格式。原文、图片和网络可达性需人工另核。检查结果不代表租金预测准确率或数据真实性评价。',
            '', '人工清单先处理优先项，再选2—4篇代表公告回原件。V01反映原表仍有待核事项，即使金额曾被补核，其他字段仍可能待核，须逐项填写复核结论。',
            '', '| 规则 | 命中问题条数 |','| --- | --- |']
    report.extend(f'| {rule[0]} | {counts[rule[0]]} |' for rule in RULES)
    report.extend(['','未知字段及本规则无法识别的价格、面积、公式保留到复核队列。无价记录允许金额为空，零建筑面积允许保留，面积为零时不计算该面积口径的单价。'])
    (out/outputs[4]).write_text('\n'.join(report)+'\n','utf8')
    return dict(rows=len(rows),file_errors=file_errors,error_rows=errors,review_rows=sum(r['需复核数']>0 for r in summary),normalized_checked=formula_checked,status=overall,rules=dict(counts))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'共享资料/公众号采集结果.csv')
    parser.add_argument('--template',type=Path,default=ROOT/'共享资料/统一采集空表.csv')
    parser.add_argument('--out',type=Path,default=ROOT/'成员成果/王玮/X03')
    args=parser.parse_args()
    print(check(args.input,args.template,args.out))

if __name__=='__main__':
    main()
