"""把第二批成员已签核修订应用到v2；父版本及原始数据保持不变。"""
import argparse,csv,hashlib,json,shutil
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:r=csv.DictReader(f);return r.fieldnames,list(r)
def write(p,fields,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(out):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise FileExistsError('已有版本不得覆盖，请指定新的空目录')
    parent=ROOT/'成员成果/王玮/Y01/公众号整理版_v1'
    batch=ROOT/'成员成果/王玮/Y01/第二批10条复核'
    raw=ROOT/'共享资料/公众号采集结果.csv';source=parent/'公众号采集结果_整理版_v1.csv'
    manifest=json.loads((parent/'版本清单.json').read_text('utf-8'))
    if sha(source)!=manifest['整理版SHA256'] or sha(raw)!=manifest['原始数据SHA256']:raise ValueError('父版本或原始底表哈希不符')
    parent_hash=sha(source);raw_hash=sha(raw)
    fields,old=read(source);rows=[dict(x) for x in old];byid={r['observation_id']:r for r in rows}
    _,signed=read(batch/'成员签核登记.csv');_,review=read(batch/'第二批复核记录.csv');_,images=read(batch/'证据索引.csv')
    nums=[87,131,136,137,148,149,181,191,206,208]
    expected={f'WX-20261108-{n:06d}' for n in nums};reviews={r['观察ID']:r for r in review};image_byid={r['观察ID']:r for r in images}
    if len(signed)!=10 or {r['观察ID'] for r in signed}!=expected or any(r['签核人']!='王玮' or r['签核状态']!='成员已人工签核' for r in signed):raise ValueError('本批签核范围不符')
    if len(rows)!=1157 or len(fields)!=28 or len(reviews)!=10 or set(reviews)!=expected:raise ValueError('输入记录不符')
    for oid in expected:
        review=reviews[oid];image=image_byid[oid]
        # Git/CSV可能转换单元格内换行；仅在比较依据时等价化，不改写原值。
        norm=lambda s:s.replace('\r\n','\n').replace('\r','\n')
        if norm(byid[oid]['raw_price_unit'])!=norm(review['原价字段']) or norm(byid[oid]['area_building_chargeable_land'])!=norm(review['原面积字段']):raise ValueError('原值已改变，须重新核对签核依据')
        if sha(batch/image['原图'])!=image['原图SHA256']:raise ValueError('原图哈希不符')
    log_fields,previous=read(parent/'逐字段修改日志.csv');changes=[]
    now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    def edit(oid,field,value,kind,reason):
        before=byid[oid][field]
        if before==value:return
        image=image_byid[oid];review=reviews[oid]
        changes.append(dict(observation_id=oid,原表数据行=str(int(oid[-6:])),字段=field,原值=before,整理值=value,变更类别=kind,修改原因=reason,
           核实记录定位='第二批复核记录.csv：'+oid+'；成员签核登记.csv：'+oid,
           证据=review['原文URL']+'\n仓库原图=成员成果/王玮/Y01/第二批10条复核/'+image['原图']+'；图序='+image['图序']+'；图内行='+image['图内行'],
           原图SHA256=image['原图SHA256'],处理方式='按成员王玮已人工签核的本批复核内容整理；未列字段保留待核',修改时间=now))
        byid[oid][field]=value
    amounts={87:'11.43万元/年',131:'73.56万元/年',137:'4172758元/年',148:'73.56万元/年',149:'73.56万元/年',181:'110.31万元/年',191:'110.31万元/年',206:'213690.65元/年',208:'145847.51元/年'}
    for n in nums:
        oid=f'WX-20261108-{n:06d}';r=byid[oid];review=reviews[oid]
        if n in amounts:
            edit(oid,'raw_price_unit',r['raw_price_unit']+'\n整理版v2成员已人工签核的图表底价='+amounts[n]+'；原OCR及既有换算按历史保留，已正确年价不重算为新报价',
                 '本批签核修订','补充明确的原图数值及货币/年度单位，保留旧OCR；签核范围见本批记录')
        if n==136:
            area=r['area_building_chargeable_land'].replace('建筑或房屋面积=5976.0㎡','建筑或房屋面积=5976.03㎡',1)
            edit(oid,'area_building_chargeable_land',area+'\n土地或场地面积=0㎡（成员已核原图）\n整理版v2=同格末位3换行，已确认5976.03㎡；上方原OCR片段保留',
                 '本批签核修订','图及正文面积一致，补回OCR遗漏的末位3；图表土地明确0')
            edit(oid,'raw_price_unit',r['raw_price_unit']+'\n原图表格底价=4406127元/年\n正文金额=440.61万（不含税），按年度表头口径对照为4406100元/年\n差额=27元；两种表达已核对，正式采用值待核，名义月单价继续为空',
                 '未定差异标注','本条与第127条均存在同类金额表达差异，分别保留两次观察，未合并或选择采用值')
        elif n in [87,148,149,181,206,208] and '土地或场地面积=0㎡' not in r['area_building_chargeable_land']:
            edit(oid,'area_building_chargeable_land',r['area_building_chargeable_land']+'\n土地或场地面积=0㎡（成员已核本行原图）',
                 '本批签核修订','仅按本条已签核原图明确的0补充，不把其他行的空白或斜线推成0')
        if n==87:
            edit(oid,'address_scope_floor',r['address_scope_floor']+'\n出租范围=与北京东路44号-2捆绑项目中的太平门街81号负一层分项',
                 '本批签核修订','分项范围单列，不与整包合计累加')
        text='成员王玮已人工签核本批复核内容；原图判断='+review['原图核对结果']+'；其他未列字段沿用原待核状态，前文为历史记录。'
        edit(oid,'verification_status',r['verification_status']+'\n整理版v2当前核验='+text,'签核与溯源说明','记录签核人和范围，未把本批签核扩展到全表全部字段')
        restriction='只落实本批原图数值、单位、面积或范围修订；主体、计租口径及完整经济条款仍按缺口处理，不作成交真值。'
        if n==87:restriction+='捆绑分项不与合计重复累加。'
        if n==136:restriction+='图文金额差异尚未选正式采用值，不计算单价。'
        edit(oid,'comparison_decision',r['comparison_decision']+'\n整理版v2限制='+restriction,'签核与溯源说明','保留历史、多期及比较范围限制')
        missing=r['missing_reason']
        if n==136:missing=missing.replace('土地面积未取得或OCR未确认','本批成员已核原图土地面积0㎡；计租面积类型仍待核',1)
        edit(oid,'missing_reason',missing+'\n整理版v2补充=已处理本批签核建议；原OCR片段继续保留；其他缺失原因不清空。'+('金额正式采用值待同轮文件确认。' if n==136 else ''),
             '签核与溯源说明','清楚区分已处理字段与其余原始缺口')
        edit(oid,'source_url_page',r['source_url_page']+'\n整理版v2依据=成员成果/王玮/Y01/第二批10条复核/第二批复核记录.csv及成员签核登记.csv；本条='+oid,
             '签核与溯源说明','保留原来源，并增加成员签核定位')
    assert len(rows)==1157 and all(a['asset_id']==b['asset_id'] and a['observation_id']==b['observation_id'] for a,b in zip(old,rows))
    assert {r['observation_id'] for r in changes}==expected
    actual={(a['observation_id'],k):(a[k],b[k]) for a,b in zip(old,rows) for k in fields if a[k]!=b[k]}
    assert actual=={(r['observation_id'],r['字段']):(r['原值'],r['整理值']) for r in changes}
    _,originals=read(raw);replay={r['observation_id']:dict(r) for r in originals}
    for change in previous+changes:
        r=replay[change['observation_id']];assert r[change['字段']]==change['原值'];r[change['字段']]=change['整理值']
    assert list(replay.values())==rows
    out.mkdir(parents=True,exist_ok=True)
    data=out/'公众号采集结果_整理版_v2.csv'
    write(data,fields,rows);write(out/'本批修改日志.csv',log_fields,changes);write(out/'逐字段修改日志.csv',log_fields,previous+changes)
    shutil.copyfile(batch/'成员签核登记.csv',out/'本批成员签核登记.csv')
    shutil.copyfile(batch/'第二批复核记录.csv',out/'本批复核依据快照.csv')
    issues=[dict(问题ID='D01',差异类型='中山东路147号图文金额表达差异',涉及观察ID='WX-20261108-000127；WX-20261108-000136（两次观察分别保留）',原图值='4406127元/年',正文值='440.61万，按年度口径对照为4406100元/年',差额='27元/年',当前处理='两值并存，未选择正式采用值，两条名义月单价均为空',后续证据='各对应轮次正式招租文件或官方答疑'),
       dict(问题ID='D02',差异类型='常熟大地块图文土地面积差异',涉及观察ID='WX-20261108-000510',原图值='68170.28㎡',正文值='69170.28㎡',差额='1000㎡',当前处理='继承v1，主标签为待核，两值并存；无租金不计算单价',后续证据='同轮正式招租文件/资产清单或官方答疑')]
    write(out/'未定差异清单.csv',list(issues[0]),issues)
    count_original=sum(a!=b for a,b in zip(originals,rows))
    result=dict(版本='公众号整理版_v2',生成时间=now,父版本='公众号整理版_v1',父版本SHA256=parent_hash,原始底表SHA256=raw_hash,
       整理版SHA256=sha(data),本批修改日志SHA256=sha(out/'本批修改日志.csv'),累计日志SHA256=sha(out/'逐字段修改日志.csv'),程序SHA256=sha(Path(__file__)),
       签核依据SHA256=sha(batch/'成员签核登记.csv'),复核依据SHA256=sha(batch/'第二批复核记录.csv'),行数=1157,字段数=28,
       本批签核观察数=10,本批变化字段数=len(changes),累计变更字段记录=len(previous+changes),累计变化观察数=count_original,
       本批签核人='王玮；仅限第二批10条所列复核内容',未定差异类别数=2,资产及观察ID='全部沿用，不去重、不删行',回放验证='可按累计日志从原始底表完整重建v2')
    (out/'版本清单.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    (out/'版本说明.md').write_text(f'''# 公众号整理版v2

生成时间：{now}。接续不可覆盖的v1，落实第二批10条成员王玮已人工签核的修订。原始1157行底表及v1均保持不变，仍为1157行、28字段和原ID/行序，历史观察不删并。

本批10条涉及{len(changes)}个字段变化，主要为金额清晰读数/单位、原图明确土地0、捆绑分项范围、第136条房屋面积5976.03㎡及相应核验说明。原有正确年价和月单价不重算为新报价，本批不强填新的月单价。

原OCR片段和历史核验状态继续保留，当前采用信息及签核范围另加标签。原图未明确的字段不借用其他项目补值；其他主体、计租及经济条款等缺口继续待核。成员签核不等同于1157行或每个字段全部已核。

累计相对原始底表有{count_original}条观察变化，累计日志{len(previous+changes)}个字段记录。[本批日志](本批修改日志.csv)记录v1→v2，[累计日志](逐字段修改日志.csv)记录原始底表→v1→v2，可逐步回放恢复完整数据。每条保留原值、整理值、证据、签核范围及时间。

[两项未定差异](未定差异清单.csv)继续保留：中山东路图文金额差27元（第127/136条分别保留）、常熟图文土地面积差1000㎡（第510条）。未选正式采用值。第136条面积漏位已修复，不再列为面积图文冲突。

[版本清单](版本清单.json)、[本批成员签核快照](本批成员签核登记.csv)、[复核依据快照](本批复核依据快照.csv)提供输入输出哈希及当前版本依据。版本哈希对应本次运行的文件字节，文件换行转换后需另行核验。

旧OCR中空格或旧值保留可能继续触发规则提示，请区分历史OCR与当前签核说明。v2并非全量真实性验收或定价训练集。重新生成必须使用新空目录，现有版本不可覆盖。
''','utf-8')
    assert sha(source)==parent_hash and sha(raw)==raw_hash
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'成员成果/王玮/Y01/公众号整理版_v2');a=p.parse_args()
    print(json.dumps(build(a.out),ensure_ascii=False,indent=2))
