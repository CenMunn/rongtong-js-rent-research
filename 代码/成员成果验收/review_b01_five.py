"""复现B01重点5条的限定辅助复核；固定读图观察，不执行自动人工签核或合库。"""
import argparse
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
FIRST = ROOT/'成员成果/王玮/成员成果验收/2026-11-10_首批'
BASE = FIRST/'原始提交展开/B01_20261108'
DEFAULT_OUT = ROOT/'成员成果/王玮/成员成果验收/2026-11-10_B01重点5条'
FACTS = {
    'N0117FCZZ250441': dict(name='苏州经贸北区1号', area='36.45', floor='68671.80', rent='68671.80', monthly='157.0000', shop=1, result='SZ_shop1_result_ejy_retry.response.json'),
    'N0117FCZZ250442': dict(name='苏州经贸北区2号', area='18.45', floor='34759.80', rent='34759.80', monthly='157.0000', shop=2, result='SZ_shop2_result_ejy.response.json'),
    'N0117FCZZ250449': dict(name='苏州经贸北区9号', area='205.73', floor='387595.32', rent='810202.00', monthly='328.1818', shop=9, result='SZ_shop9_result_ejy.response.json'),
    'N0117FCZZ240212': dict(name='湖南路185号2024包', area='1547.66', floor='2594300.00', rent='3689300.00', monthly='198.6494', listing='NJ_hunan2024_listing.html', result='NJ_hunan2024_result_retry.html'),
    'N0117FCZZ231107': dict(name='湖南路185号2023包', area='6300.00', floor='3856223.00', rent='5471223.00', monthly='', listing='NJ_hunan2023_listing.html', result='NJ_hunan2023_result.html'),
}

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        r=csv.DictReader(f)
        return r.fieldnames, list(r)

def write(path, rows, fields=None):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]))
        w.writeheader();w.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rel(path):
    return path.relative_to(ROOT).as_posix()

def soup(path):
    if path.suffix=='.json':
        d=json.loads(path.read_text(encoding='utf-8-sig'))
        return BeautifulSoup(d['newsDetail']['content'],'html.parser')
    return BeautifulSoup(path.read_bytes(),'html.parser')

def plain(path):
    s=soup(path)
    for x in s(['script','style','noscript']):x.decompose()
    return re.sub(r'\s+',' ',' '.join(s.stripped_strings))

def compact(value):
    return re.sub(r'\s+','',value)

def result_fields(path):
    result={}
    for tr in soup(path).find_all('tr'):
        cells=tr.find_all(['td','th'],recursive=False)
        if len(cells)==2:
            result[compact(cells[0].get_text())]=cells[1].get_text(' ',strip=True)
    return result

def build(out):
    if out.exists():raise FileExistsError('禁止覆盖已发布目录，请指定新 --out')
    protected=[ROOT/'共享资料/南京苏州交易明细.csv',ROOT/'共享资料/公众号采集结果.csv',
               ROOT/'成员成果/王玮/Y01/公众号整理版_v2/公众号采集结果_整理版_v2.csv',
               ROOT/'成员成果/陈怡帆/B01_20261108_成果与原件.zip',
               BASE/'B01_统一采集表.csv',BASE/'B01_缺面积复点与配对结果.csv']
    before={rel(p):sha(p) for p in protected}
    fields, original=read(BASE/'B01_统一采集表.csv')
    _, detail=read(BASE/'B01_缺面积复点与配对结果.csv')
    byid={r['round_contract_id']:r for r in original}
    detailed={r['成交编号']:r for r in detail}
    _,evidence=read(BASE/'证据索引.csv')
    evidence_byname={Path(r['原件路径']).name:r for r in evidence if r['状态']=='200'}
    files={'SZ_ejy_batch8403.html','SZ_batch_items.html','SZ_school_schedule.pdf'}
    for fact in FACTS.values():
        files.add(fact['result'])
        if 'listing' in fact:files.add(fact['listing'])
    for name in files:
        assert sha(BASE/'证据'/name)==evidence_byname[name]['文件SHA256'],name
    assert sha(BASE/'证据/SZ_school_schedule.pdf')=='d641ce04b2fd6e7e9c2713649cb95876fda6eaa696d77bddbfcb3257ffaead7f'
    out.mkdir(parents=True)
    with pymupdf.open(BASE/'证据/SZ_school_schedule.pdf') as pdf:
        assert len(pdf)==1
        pdf[0].get_pixmap(matrix=pymupdf.Matrix(3,3).prerotate(270)).save(out/'苏州扫描清单_第1页横向.png')
    quotes=[];index=[];scan=[];audit=[];derived=[];logs=[]
    def quote(oid,name,field,fragment):
        t=compact(plain(BASE/'证据'/name));fragment=compact(fragment)
        start=t.find(fragment)
        assert start>=0,(name,fragment)
        quotes.append({'观察ID':oid,'字段':field,'证据':rel(BASE/'证据'/name),
                       '原文摘录':t[max(0,start-20):start+len(fragment)+70],
                       '规范化文本偏移':start,'原件SHA256':sha(BASE/'证据'/name)})
    for name in sorted(files):
        e=evidence_byname[name]
        index.append({'证据文件':rel(BASE/'证据'/name),'入口URL':e['入口URL'],'POST参数':e['POST参数'],
                      '获取时间':e['采集时间'],'原件SHA256':e['文件SHA256'],
                      '本次核对':'已保存存档的内容与哈希核对；未实时回网'})
    batch=plain(BASE/'证据/SZ_ejy_batch8403.html')
    item_rows=[]
    for tr in soup(BASE/'证据/SZ_batch_items.html').find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)]
        if len(cells)>3:item_rows.append(cells)
    for round_id,fact in FACTS.items():
        row=byid[round_id];d=detailed[round_id];oid=row['observation_id']
        result=result_fields(BASE/'证据'/fact['result'])
        assert result['标的编号']==round_id
        for label,expected in [('年租金底价（元）',fact['floor']),('成交年租金（元）',fact['rent'])]:
            assert Decimal(result[label].replace(',',''))==Decimal(expected),(round_id,label)
            quote(oid,fact['result'],label,label+result[label])
        quote(oid,fact['result'],'同轮标的编号','标的编号'+round_id)
        assert result['出租方名称']==row['lessor_entity']
        assert result['成交日期']==d['原文成交日期']
        assert Decimal(d['本次公告披露面积平方米'])==Decimal(fact['area'])
        assert Decimal(d['成交年租金元'])==Decimal(fact['rent'])
        numerator=Decimal(fact['rent']);area=Decimal(fact['area'])
        notes='实际签署合同、计租分母及实收未核；仅为披露范围下的名义价格观察'
        if 'shop' in fact:
            number=fact['shop']
            item=next(c for c in item_rows if c[1]==round_id)
            assert f'北区{number}号商铺' in item[0]
            assert compact(item[0])==compact(result['出租标的名称'])
            quote(oid,'SZ_batch_items.html','铺号与系统编号映射',' '.join(item[:4]))
            quote(oid,'SZ_ejy_batch8403.html','批量公告关联清单','具体详见《待出租房产基本情况清单》')
            # PDF数值来自2026-11-10 Codex对原图第1/2/9行的固定读图观察；不是运行时OCR自动确认。
            scan.append({'观察ID':oid,'铺号':number,'物理页':1,'表内行':number,
                         '原图披露租赁面积㎡':fact['area'],'原图评估及底价元每年':fact['floor'],
                         '租期原文':'5年','原图编号栏':'以系统提示为准',
                         '编号补充证据':'SZ_batch_items.html中同铺号对应'+round_id,
                         '原PDF':rel(BASE/'证据/SZ_school_schedule.pdf'),
                         '本批横向渲染图':'苏州扫描清单_第1页横向.png',
                         '核对方式':'2026-11-10 Codex原图读图辅助核对，非团队成员签核'})
            chain=f'批量公告及其附件链接→标的列表北区{number}号={round_id}→原PDF第1页第{number}行→同编号成交JSON content表格'
            status='可接收公开成交观察（披露面积名义分摊）'
            if number==2:
                notes+='；单项列表截止2025-03-31，批量正文为03-24，分别保留，是否正式延期未查'
            if number==9:
                notes+='；成交810202元高于底价387595.32元，二者不能互替'
        else:
            listing=fact['listing'];t=plain(BASE/'证据'/listing)
            quote(oid,listing,'同轮挂牌编号','项目编号'+round_id)
            quote(oid,listing,'披露面积','租赁面积约(㎡)'+fact['area'])
            assert result['出租方名称'] in t
            chain='同项目编号、出租方和出租范围的挂牌HTML→成交HTML；不跨用同门牌另一包面积'
            if round_id=='N0117FCZZ240212':
                quote(oid,listing,'分段交付与免租','2024年6月1日前，除去原租户未能交付的575平方米（招商银行1楼+2楼），剩余部分出租面积约为972.66平方米')
                quote(oid,listing,'免租适用范围','该区域2024年6月1日前给予装修免租期；2024年6月1日后交付的部分无免租期')
                assert Decimal('575')+Decimal('972.66')==area
                status='条件接收：仅全范围名义单价，分段起租及有效租金待核'
                notes+='；1547.66=972.66+575，不能把全包年租全部除以先交付972.66㎡，也不能假定整个租期全范围免租'
            else:
                quote(oid,listing,'地下空间范围','负一楼约500平方米不算在产证面积内')
                quote(oid,listing,'税费原文','租赁租赁价格为不含增值税价，税金由承租方承担')
                status='仅接收成交金额及披露范围；计租分母待核，单价留空'
                notes+='；约6300㎡与地下约500㎡包含关系未解决，不自行采用6300或6800或5800㎡作分母'
        if fact['monthly']:
            calc=(numerator/12/area).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
            assert calc==Decimal(fact['monthly'])
            assert Decimal(re.search(r'\d+(?:\.\d+)?',row['monthly_normalized'])[0])==calc
            result_month=str(calc)
        else:
            assert row['monthly_normalized']=='' and d['换算公式']==''
            result_month=''
        audit.append({'观察ID':oid,'项目编号':round_id,'名称':fact['name'],'原件披露面积㎡':fact['area'],
                      '原件挂牌底价元每年':fact['floor'],'原件成交年租金元':fact['rent'],
                      '名义元每披露㎡月':result_month,'原价单位核对':'原文成交年租金（元），非保证金或评估价',
                      '同轮证据链':chain,'接收结论':status,'仍待核及使用限制':notes,
                      '原值修订':'原金额、原面积与已填名义数值均相符，无数值纠错；2023包保持空单价',
                      '核验方式':'Codex存档及PDF原图辅助核对，未代成员人工签核'})
        clone=dict(row)
        def edit(field,value,reason):
            if clone[field]!=value:
                logs.append({'观察ID':oid,'字段':field,'原值':clone[field],'本批副本值':value,'原因':reason,
                             '核验方式':'仅助手限定复核，非成员新增签核'})
                clone[field]=value
        if result_month:
            edit('monthly_normalized',f'{result_month}元/披露㎡/月（名义；{numerator}元/年÷12÷{area}㎡）'+('；仅全包范围，不代表分段实收' if round_id=='N0117FCZZ240212' else ''),'补分母及公式标签，不改数值')
        if round_id=='N0117FCZZ240212':
            edit('rent_free_escalation',row['rent_free_escalation']+'；挂牌原文：972.66㎡区域2024-06-01前给予装修免租；2024-06-01后交付部分无免租；575㎡原租户区域交付待核；成交签约条款未得','摘录已披露分段条件，不等同已签合同')
        edit('verification_status',row['verification_status']+'\n2026-11-10重点5条Codex辅助核对：原件编号、金额、披露面积及名义换算范围已核；'+status+'；未代成员签核','保留原提交状态，限定本次复核内容')
        edit('comparison_decision',row['comparison_decision']+'；'+status+'；'+notes,'限定观察使用范围，不纳为最终可比或实收真值')
        edit('missing_reason',row['missing_reason']+'\n本批已完成所列原件的助手辅助核对，前文“独立复核”为历史状态；'+notes+'；其余未列字段继续待核','不清空尚未核实的实际计租及合同缺口')
        derived.append(clone)
    write(out/'重点5条复核记录.csv',audit)
    write(out/'重点5条_28字段复核副本.csv',derived,fields)
    write(out/'扫描清单3条读图记录.csv',scan)
    write(out/'逐字段证据摘录.csv',quotes)
    write(out/'证据索引.csv',index)
    write(out/'副本修改日志.csv',logs)
    public_templates=[]
    for name in ['SZ_ejy_batch8403.html','NJ_hunan2023_listing.html','NJ_hunan2024_listing.html']:
        for link in soup(BASE/'证据'/name).find_all('a',href=True):
            title=link.get_text(strip=True)
            if '合同' in title and '.pdf' in link['href']:
                public_templates.append({'对应原件':rel(BASE/'证据'/name),'附件名称':title,'原文附件URL':link['href'],
                                         '状态':'从原存档提取链接，本批未下载、未验证当前可达',
                                         '用途':'供B03公开条款参考，不代替签署合同或实际计租证明'})
    write(out/'B03可参考公开合同模板线索.csv',public_templates)
    assert before=={rel(p):sha(p) for p in protected}
    summary={'时间':datetime.now().astimezone().isoformat(timespec='seconds'),'本批观察数':5,
             '扫描原图核对目标行数':3,'同编号成交及面积证据链观察数':5,'数值纠错条数':0,
             '复算相符名义单价数':4,'保持空单价数':1,'简单披露面积成交观察':3,
             '分段条件名义单价观察':1,'仅金额及范围接收观察':1,
             'B01累计限定辅助核对观察数':6,'累计说明':'首批中山北路1条，加本批5条；其余9条未逐原件复核，非全15条通过',
             '新增成员人工签核数':0,'原始输入哈希':before,'原始输入均保持':True,
             '原件索引哈希验证数':len(files),'副本字段变化数':len(logs),
             '边界':'离线存档与PDF原图辅助核对；未实时回网，不等于实际合同、实际收款或最终可比验收'}
    (out/'复核运行记录.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=DEFAULT_OUT)
    print(json.dumps(build(p.parse_args().out),ensure_ascii=False,indent=2))
