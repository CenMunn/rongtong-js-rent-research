"""保留公众号原始底表，生成有逐字段修改日志的整理副本。"""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = '1'
BASE_HASH = '15af352277259e67fbd12f7418cb341a9b218ae672e038d6a726bfeab109e8d7'

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def write(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build(source, evidence, evidence_index, out):
    source, evidence, evidence_index, out = (Path(p).resolve() for p in (source, evidence, evidence_index, out))
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('输出目录已有内容，版本不得覆盖；请指定新的空目录')
    if sha(source) != BASE_HASH:
        raise ValueError('原始底表与已核实版本不一致，请先核对版本；本程序仅应用这7项既有核实结果')
    fields, originals = read(source)
    expected = read(ROOT/'共享资料/统一采集空表.csv')[0]
    if fields != expected or len(originals) != 1157:
        raise ValueError('原表字段或记录数与本批核实基线不符')
    rows = [dict(r) for r in originals]
    by_id = {r['observation_id']: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError('观察ID不唯一，不执行修改')
    _, findings = read(evidence)
    _, image_records = read(evidence_index)
    images = {r['observation_id']: r for r in image_records}
    keys = {(r['observation_id'], r['字段']) for r in findings}
    allowed = {
        ('WX-20261108-000086','address_scope_floor'), ('WX-20261108-000086','raw_price_unit'),
        ('WX-20261108-000127','area_building_chargeable_land'), ('WX-20261108-000127','raw_price_unit'),
        ('WX-20261108-000391','area_building_chargeable_land'), ('WX-20261108-000391','monthly_normalized'),
        ('WX-20261108-000510','area_building_chargeable_land')}
    if keys != allowed or len(findings) != 7:
        raise ValueError('核实记录必须精确对应本次7个字段事项')
    for record in findings:
        if by_id[record['observation_id']][record['字段']] != record['原表值']:
            raise ValueError('待修订原值与核实记录不一致')
    for oid in {x[0] for x in allowed}:
        ref = images[oid]
        image_path = evidence_index.parent/ref['共享原图']
        if sha(image_path) != ref['原图SHA256']:
            raise ValueError('证据原图哈希不一致')
    log = []
    moment = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

    def edit(oid, field, value, category, reason):
        r = by_id[oid]
        old = r[field]
        if old == value:
            raise ValueError('预期修改未改变字段：'+oid+'/'+field)
        refs = [x for x in findings if x['observation_id']==oid and x['字段']==field]
        if not refs:
            refs = [x for x in findings if x['observation_id']==oid]
        ref = images[oid]
        log.append(dict(observation_id=oid, 原表数据行=oid[-6:].lstrip('0'), 字段=field,
            原值=old, 整理值=value, 变更类别=category, 修改原因=reason,
            核实记录定位=evidence.name+'：'+'；'.join(x['observation_id']+'/'+x['字段'] for x in refs),
            证据=ref['原文URL']+'\n仓库原图=成员成果/王玮/Y01/'+ref['共享原图']+'\n正文图序='+ref['图序'],
            原图SHA256=ref['原图SHA256'], 处理方式='Codex按已核实原图/存档整理；非王玮或组员人工签核', 修改时间=moment))
        r[field] = value

    a,b,c,d = ('WX-20261108-'+n for n in ['000086','000127','000391','000510'])
    edit(a,'address_scope_floor',by_id[a]['address_scope_floor'].replace('北京东路44号','北京东路44号-2',1)+
         '\n出租范围=与太平门街81号负一层捆绑招租中的北京东路44号-2分项',
         '原图支持的修订','补门牌后缀并标明本行分项范围，资产ID保持原值')
    edit(a,'raw_price_unit',by_id[a]['raw_price_unit']+
         '\n图表复核分项底价=272.95万元/年（不含税），即2729500元/年；旧OCR片段保留，当前分项值以本条复核说明为准',
         '原图支持的修订','识别272. 95为272.95；原有换算年价正确，不用整包价覆盖分项价')
    edit(b,'area_building_chargeable_land',by_id[b]['area_building_chargeable_land'].replace('建筑或房屋面积=5976.0㎡','建筑或房屋面积=5976.03㎡',1)+
         '\n土地或场地面积=0㎡（原图明确土地面积为0）\n本次原图复核=建筑5976.03㎡；上方原文及OCR面积片段按原始识别保留',
         '原图支持的修订','补齐跨行末位3，并记录原图明确的土地面积0')
    edit(c,'area_building_chargeable_land',by_id[c]['area_building_chargeable_land'].replace('建筑或房屋面积=11181.9㎡','建筑或房屋面积=11181.97㎡',1).replace('土地或场地面积=13279.3㎡','土地或场地面积=13279.31㎡',1)+
         '\n本次原图复核=建筑11181.97㎡、土地13279.31㎡；原文及OCR面积片段保留旧识别',
         '原图支持的修订','补齐建筑、土地两列跨行末位7与1')
    monthly = Decimal('1133400')/12/Decimal('11181.97')
    edit(c,'monthly_normalized',f'{monthly:.6f}元/建筑㎡/月（名义底价，以建筑面积暂算）\n公式=1133400.00元/年÷12÷11181.97㎡',
         '原图支持的修订','随建筑面积修订重新计算；旧显示单价及公式完整保存在修改日志')

    edit(b,'raw_price_unit',by_id[b]['raw_price_unit']+
         '\n原图表格底价=4406127元/年（不含税）\n正文对照=440.61万按同项目年度表头口径对照为4406100元/年；与图表相差27元\n差异状态=疑似精度差异，正式采用值待核；两种表达并存，暂不计算单价',
         '差异标注','保留图表、正文和27元差额，不自行确定正式采用金额')
    edit(d,'area_building_chargeable_land',by_id[d]['area_building_chargeable_land'].replace('土地或场地面积=68170.28㎡','土地或场地面积=待核（图文冲突，暂不确定采用值）',1)+
         '\n原图土地面积=68170.28㎡\n正文土地面积=69170.28㎡\n差异=1000㎡；保留两种来源值，待同轮正式招租文件或官方答疑确认',
         '差异标注','撤回旧OCR误识别判断；图表值读取正确，图文内部冲突须保留')

    current = {
        a: '已按原图补门牌后缀、捆绑分项标签和分项金额；计租面积及主体等仍待核',
        b: '已按原图核建筑5976.03㎡及土地0㎡；图表与正文金额并列，正式采用值待核',
        c: '已按原图核建筑11181.97㎡/土地13279.31㎡并重算名义建筑月单价；计租口径仍待核',
        d: '原图68170.28㎡/正文69170.28㎡存在冲突，未选择土地面积采用值；租金继续为空'}
    decisions = {
        a: '本行仅为捆绑包分项；整包284.38万元/年及6562.77㎡另属合计，分析时不得与分项累加。资产ID暂沿用，交主表负责人核对。',
        b: '金额来源差异待正式文件确认；保留名义月单价为空，不认定成交价。',
        c: '当前8.446633元/建筑㎡/月为名义首年底价，计租及经济条款口径未完整核实。',
        d: '保留无价条件线索；土地相关计算暂缓，不能以正文值直接替换图表值。'}
    for oid in [a,b,c,d]:
        r=by_id[oid]
        edit(oid,'verification_status',r['verification_status']+'\n整理版v1当前复核='+current[oid]+
             '；Codex原图/存档辅助核实，非本人或组员人工签核。上文旧状态按历史记录保留。',
             '核验与溯源说明','区分当前逐字段核对结论和历史状态，未核事项继续保留')
        edit(oid,'comparison_decision',r['comparison_decision']+'\n整理版v1限制='+decisions[oid],
             '核验与溯源说明','明确分项、差异及当前使用限制')
        missing=r['missing_reason']
        if oid==b:
            missing=missing.replace('土地面积未取得或OCR未确认','本次原图已明确土地面积0㎡；计租面积及主体关系仍待核',1)
        edit(oid,'missing_reason',missing+'\n整理版v1补充='+current[oid]+'；其余历史缺失说明继续保留。',
             '核验与溯源说明','补充当前已核范围与未解决事项，不清空其他原始限制')
        ref=images[oid]
        edit(oid,'source_url_page',r['source_url_page']+
             '\n整理依据（仓库相对路径）=成员成果/王玮/Y01/Y01_七项建议核实记录.csv；原图=成员成果/王玮/Y01/'+ref['共享原图']+
             '；正文图序='+ref['图序'], '核验与溯源说明','保留既有来源并增加可共享的核实记录和原图定位')

    assert len(rows)==len(originals) and all(a['observation_id']==b['observation_id'] and a['asset_id']==b['asset_id'] for a,b in zip(originals,rows))
    actual={(a['observation_id'],k) for a,b in zip(originals,rows) for k in fields if a[k]!=b[k]}
    assert actual=={(r['observation_id'],r['字段']) for r in log}
    assert sum(r['变更类别']=='原图支持的修订' for r in log)==5
    assert sum(r['变更类别']=='差异标注' for r in log)==2
    changed_ids=sorted({r['observation_id'] for r in log})
    out.mkdir(parents=True,exist_ok=True)
    data_path=out/'公众号采集结果_整理版_v1.csv'
    audit_path=out/'逐字段修改日志.csv'
    write(data_path,fields,rows)
    write(audit_path,list(log[0]),log)
    assert sha(source)==BASE_HASH
    manifest=dict(版本='公众号整理版_v1',程序版本=VERSION,生成时间=moment,原始数据文件=str(source),原始数据SHA256=sha(source),
        整理版SHA256=sha(data_path),修改日志SHA256=sha(audit_path),核实记录SHA256=sha(evidence),证据索引SHA256=sha(evidence_index),
        程序SHA256=sha(Path(__file__)),总行数=len(rows),字段数=len(fields),修订观察数=len(changed_ids),
        未改动观察数=len(rows)-len(changed_ids),修订字段数=len(log),原图支持修订项=5,差异标注项=2,
        修订观察ID=changed_ids,资产ID及观察ID='全部保持原值及顺序，不去重不删行',核实范围='仅本次7项及必要状态/溯源说明',
        人工签核='本批WX观察未由本人或组员独立人工签核；原文抽核O01/O04/O06确认不移作本批签核',
        未定事项=['中山东路图表/正文金额差额27元，正式采用值待核','常熟大地块图表/正文土地面积差1000㎡，暂未选择采用值'])
    (out/'版本清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    (out/'版本说明.md').write_text(f'''# 公众号整理版 v1

基于已保存底表和七项建议核实记录生成，不新增抓取，不覆盖原始底表。生成时间：{moment}。

1157行、28字段及原顺序全部保留；4条观察涉及{len(log)}个字段变化，其中5项原图支持的修订、2项差异标注，其余为核验状态、使用限制和证据定位。另1153条观察逐字段保持不变。资产ID及观察ID均沿用原值，历史多期记录不删除，暂编资产ID后续仍需统一。

## 已落实修订

- 第86行：门牌补“-2”，标明捆绑包分项；追加明确分项272.95万元/年，原OCR片段保留，整包价仅在使用限制说明。
- 第127行：建筑5976.03㎡及原图土地0㎡；同时保留原OCR片段。
- 第391行：建筑11181.97㎡、土地13279.31㎡；1133400÷12÷11181.97换算为8.446633元/建筑㎡/月。

## 仍未确定的数值

- 第127行原图4406127元/年、正文440.61万元两种表达并列，按年度口径差27元；正式采用值待核，名义月单价继续为空。
- 第510行原图土地68170.28㎡、正文69170.28㎡，差1000㎡；“土地或场地面积”主标签改为待核，双来源数值均保留。不能直接取正文覆盖图表。该条无价，金额及月单价继续为空。

## 使用与追溯

当前规范化面积和复核说明与原OCR片段同时存在，分析时按标签识别，不能提取第一个或最后一个数字就认定为采用值。图文冲突项不选单一土地面积；捆绑分项和合计不得同时累加。

原始输入、核实记录、程序及输出哈希见[版本清单](版本清单.json)。每一处变更的完整原值、整理值、原因、证据和核实记录定位见[逐字段修改日志](逐字段修改日志.csv)。修改日志是审计记录，不属于额外采集样本。

本次为Codex按原图/存档辅助核实后的整理副本，不宣称全量真实性、计租口径或当前市场价已确认。原O01/O04/O06人工确认属于另一组观察，不移作这些WX记录的签核。

本版只落实用户批准的①②；不扩大抽查，不推断缺失值，不估算有效租金。原始底表完整保留。重复生成请指定新的空目录，旧版本不得覆盖。
''','utf-8')
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'共享资料/公众号采集结果.csv')
    p.add_argument('--evidence',type=Path,default=ROOT/'成员成果/王玮/Y01/Y01_七项建议核实记录.csv')
    p.add_argument('--evidence-index',type=Path,default=ROOT/'成员成果/王玮/Y01/Y01_证据索引.csv')
    p.add_argument('--out',type=Path,default=ROOT/'成员成果/王玮/Y01/公众号整理版_v1')
    args=p.parse_args()
    print(json.dumps(build(args.source,args.evidence,args.evidence_index,args.out),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
