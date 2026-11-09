"""Y01限定版本的省域视图及核验状态索引；标准库，不改底表，不新增签核。"""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
Y01 = ROOT / '成员成果/王玮/Y01'
SOURCE = Y01 / '公众号整理版_v2/公众号采集结果_整理版_v2.csv'
RAW = ROOT / '共享资料/公众号采集结果.csv'
HASH = '562b4fb084dcc6191ff93b7863eec57e919f954c593aef6461929e2a3fc285bd'
RAW_HASH = '15af352277259e67fbd12f7418cb341a9b218ae672e038d6a726bfeab109e8d7'
DEFAULT_OUT = Y01 / '省域分层与状态汇总_2026-11-10'
PART_FILES = {'江苏': '江苏省内_28字段.csv', '省外': '省外保留_28字段.csv',
              '归属待确认': '归属待确认_28字段.csv'}
STATES = ['成员已签核（限定字段）', '助手抽核，待成员确认',
          '机器候选，待成员复核', '本轮未登记逐条复核']
# 仅匹配完整的“某市”字样；不将街道名、来源片区或企业名称当作地址证据。
JS_CITIES = ('南京 苏州 无锡 徐州 常州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁 '
             '常熟 江阴 昆山 太仓 张家港 宜兴 溧阳 启东 如皋 海安 邳州 新沂 '
             '东台 仪征 高邮 丹阳 扬中 句容 兴化 靖江 泰兴').split()
AH_CITIES = ('合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山 滁州 阜阳 宿州 '
             '六安 亳州 池州 宣城 巢湖 桐城 天长 明光 宁国 界首 潜山 广德 无为').split()
OTHER_PROVINCES = ('浙江省 上海市 北京市 天津市 重庆市 河北省 山西省 辽宁省 吉林省 '
                   '黑龙江省 福建省 江西省 山东省 河南省 湖北省 湖南省 广东省 海南省 '
                   '四川省 贵州省 云南省 陕西省 甘肃省 青海省 台湾省 内蒙古自治区 '
                   '广西壮族自治区 西藏自治区 宁夏回族自治区 新疆维吾尔自治区 '
                   '香港特别行政区 澳门特别行政区').split()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows, headers):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def rel(path):
    return path.relative_to(ROOT).as_posix()


def address_text(text):
    return text.split('来源片区=')[0].strip()


def classify(text):
    address = re.sub(r'\s+', '', address_text(text))
    if not address:
        return '归属待确认', '有效地址缺失；来源片区只作检索线索'
    matches = set()
    evidence = []
    for province in ['江苏省', '安徽省'] + OTHER_PROVINCES:
        if province in address:
            matches.add('江苏' if province == '江苏省' else province)
            evidence.append(province)
    for cities, province in [(JS_CITIES, '江苏'), (AH_CITIES, '安徽省')]:
        found = [city + '市' for city in cities if city + '市' in address]
        if found:
            matches.add(province)
            evidence.extend(found)
    if len(matches) > 1:
        return '归属待确认', '地址包含多个省域线索：' + '、'.join(evidence)
    if matches:
        return ('江苏' if '江苏' in matches else '省外'), '现有地址文本命中：' + '、'.join(evidence)
    return '归属待确认', '缺少明确省份或完整地级/县级市名；不按片区或路名推定'


def build(out):
    if out.exists():
        raise FileExistsError('禁止覆盖已发布目录，请指定新的 --out')
    if digest(SOURCE) != HASH or digest(RAW) != RAW_HASH:
        raise ValueError('输入版本变化，需重新审定省域及状态口径')
    inputs = [SOURCE, RAW, Y01 / 'Y01_证据索引.csv', Y01 / 'Y01_字段复核记录.csv',
              Y01 / '第二批10条复核/成员签核登记.csv',
              Y01 / '第三批10条复核/第三批复核记录.csv',
              Y01 / '第四批10条待核候选/第四批10条待核候选.csv',
              Y01 / '公众号整理版_v2/未定差异清单.csv']
    before = {rel(p): digest(p) for p in inputs}
    rows = read(SOURCE)
    headers = list(rows[0])
    assert len(rows) == 1157 and len(headers) == 28
    ids = [r['observation_id'] for r in rows]
    assert len(set(ids)) == len(ids)
    signed = {r['观察ID']: r for r in read(inputs[4])}
    first = {r['observation_id']: r for r in read(inputs[2])}
    third = {r['观察ID']: r for r in read(inputs[5])}
    fourth = {r['观察ID']: r for r in read(inputs[6])}
    for entries in [signed, first, third, fourth]:
        assert set(entries) <= set(ids)
    for r in signed.values():
        assert r['签核状态'] == '成员已人工签核'
    parts = {k: [] for k in PART_FILES}
    index = []
    for number, row in enumerate(rows, 1):
        oid = row['observation_id']
        layer, basis = classify(row['address_scope_floor'])
        parts[layer].append(row)
        region = re.search(r'来源片区=([^\n]+)', row['address_scope_floor'])
        state = STATES[3]
        scope = '本轮无逐条登记；原字段中的历史核验描述原样保留，不自动升级为成员签核'
        origin = rel(SOURCE)
        pending = '金额、原单位、计租分母、主体、范围及条款按实际证据逐项核验'
        if oid in signed:
            state, origin = STATES[0], rel(inputs[4])
            scope = signed[oid]['范围']
            pending = '仅本批所列字段已签核；其他字段仍按原记录待核'
        elif oid in first or oid in third:
            state = STATES[1]
            origin = rel(inputs[2] if oid in first else inputs[5])
            scope = '仅抽核记录所列字段的助手原图/正文对照；尚无本批成员签核'
            pending = '成员确认抽核结论及修订建议后，才能应用未签核变化'
        elif oid in fourth:
            state, origin = STATES[2], rel(inputs[6])
            scope = 'OCR同格补读或同篇项目匹配候选；不代表人工核验'
            pending = fourth[oid]['风险与待核事项']
        if oid in {'WX-20261108-000127', 'WX-20261108-000136'}:
            pending += '；D01图文金额差27元/年，正式采用值未定'
        if oid == 'WX-20261108-000510':
            pending += '；D02图文土地面积差1000㎡，正式采用值未定'
        index.append({'原表行': number, '观察ID': oid, '资产ID': row['asset_id'],
                      '省域层': layer, '省域判断依据': basis, '现有地址摘录': address_text(row['address_scope_floor']),
                      '来源片区': region.group(1) if region else '',
                      '本轮复核状态': state, '状态登记依据': origin, '已核或候选范围': scope,
                      '仍待核事项': pending, '原核验状态（未改写）': row['verification_status']})
    summary = {'规则版本': 'Y01-LAYER-1.0', '生成时间': datetime.now().astimezone().isoformat(timespec='seconds'),
               '输入观察数': len(rows), '字段数': len(headers),
               '省域分层': {k: len(v) for k, v in parts.items()},
               '复核状态': {s: sum(r['本轮复核状态'] == s for r in index) for s in STATES},
               '价格性质（照录v2）': dict(Counter(r['price_type'] for r in rows)),
               '归属待确认中地址缺失数': sum(not r['现有地址摘录'] for r in index if r['省域层'] == '归属待确认'),
               '原表有公众号文章URL的观察数': sum(bool(re.search(r'https://mp\.weixin\.qq\.com/(?:s(?:\?|/))', r['source_url_page'])) for r in rows),
               '校验': {'分层总数等于输入': sum(len(v) for v in parts.values()) == len(rows),
                       '观察ID无重复': len(set(ids)) == len(ids), 'v2及原始底表未修改': True,
                       '省域规则判断不是人工确认': True, '新候选未写入v2或v3': True}}
    out.mkdir(parents=True)
    for layer, filename in PART_FILES.items():
        write(out / filename, parts[layer], headers)
        assert read(out / filename) == parts[layer]
    write(out / '逐条省域与核验状态索引.csv', index, list(index[0]))
    write(out / '归属待确认原因清单.csv', [r for r in index if r['省域层'] == '归属待确认'], list(index[0]))
    cross = [{'省域层': layer, '核验状态': state,
              '观察数': sum(r['省域层'] == layer and r['本轮复核状态'] == state for r in index)}
             for layer in parts for state in STATES]
    write(out / '省域与状态交叉汇总.csv', cross, ['省域层', '核验状态', '观察数'])
    shutil.copyfile(inputs[7], out / '两项未定差异.csv')
    (out / '汇总与校验.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    counts = summary['省域分层']
    state_lines = '\n'.join(f'| {s} | {summary["复核状态"][s]} |' for s in STATES)
    (out / '分层与状态说明.md').write_text(f'''# Y01省域分层与状态汇总

基准为整理版v2的1157条观察、28字段。生成时间：{summary['生成时间']}。本次只生成视图和状态索引，原始底表、v1、v2及历史观察均保留；未生成v3。

| 省域层 | 观察数 | 使用方式 |
| --- | ---: | --- |
| 江苏 | {counts['江苏']} | 按现有地址字段规则识别的省内候选，不等于逐条身份已核实 |
| 省外 | {counts['省外']} | 独立保留，不并入江苏主体研究样本 |
| 归属待确认 | {counts['归属待确认']} | 地址不足或歧义，待后续回原件确认 |

三份28字段CSV逐值保持v2内容与各层原有顺序，合计1157条，不删并历史观察。省域标签和判断依据放在单独索引，不增加统一采集模板字段。

规则先截取地址正文，去掉“来源片区=”及其后元信息；忽略地址内空白，匹配明确省份或完整地级/县级市名。完整市名只使用程序列明的江苏、安徽清单；其他省份按明确省级名称识别。多个省域线索冲突时留待确认。“北京西路”不视为北京，“吴江农场”不凭场名推定为苏州，片区标签不替代项目地址。按现有地址判定有OCR错误风险，不代表本次又核对了全部原件。公司管理范围也不等于物业所在省份，省域分层不替代出租法人和资产归属核验。

待确认中{summary['归属待确认中地址缺失数']}条缺少有效地址；其余只有场名、路名或楼层范围等不足线索。逐项原因见归属待确认原因清单；不从相邻项目借用地址。

| 本轮状态（互斥统计） | 观察数 |
| --- | ---: |
{state_lines}

成员签核仅按第二批10条签核登记认定，且只覆盖登记字段，第136条价格差异仍未选择正式值。助手抽核包含首批6条和第三批10条；第四批10条是机器候选。本轮无登记者不等于历史从未处理，其历史标签仍保留在索引，不能据此推算全量已人工验收。状态与省域规则是两个独立维度。

第三、四批候选未写入v2。两项未定差异继续保留：D01中山东路147号图文金额差27元/年（127、136两次观察），D02常熟大地块图文土地面积差1000㎡（510）；同轮正式文件或答疑缺失前不选择单一值。

本次分层未复核全部租金与面积，未核实实际用途、计租分母或全量公司身份，也不检查网站当前能否打开。可追溯的公众号文章URL只代表表内有链接，不代表实时可达。底价、无价及面议样本不能混同成交标签，不直接报告租金预测准确率。

复现：从仓库根目录运行 `python "代码/公众号数据整理/build_y01_layers.py" --out "新空目录"`。输入必须匹配已发布v2与原始底表哈希，目录存在即拒绝覆盖。输入、输出哈希见清单。

下一步：由王玮收口Y01第一阶段初版，按提交清单交付；候选复核、正式文件补证和后续版本另行推进，不阻塞已完成的本阶段方法与抽检结果。
''', encoding='utf-8')
    assert before == {rel(p): digest(p) for p in inputs}, '输入被修改'
    manifest = {'输入': before, '输出': {p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()},
                '生成程序': rel(Path(__file__)), '程序SHA256': digest(Path(__file__))}
    (out / '输入输出哈希清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(build(args.out), ensure_ascii=False, indent=2))
