"""整理南京片区合集归档，单列正文年价与需核对的表图。"""
import csv,json,re,sqlite3
from pathlib import Path
from decimal import Decimal
from bs4 import BeautifulSoup
from lxml import html
from wechat_projects import projects,FIELDS,money,MARK
from wechat_categories import classify_project,article_type,CLASS_FIELDS
from wechat_crawler import export_csv,article_key
ROOT=Path(__file__).resolve().parent/'outputs/南京片区合集试采'
DEST=ROOT/'交付文件'
def read(file):
 with file.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def package_values(s):
 return {m[1]:m[2].strip('：: ') for m in re.finditer(r'资产包\s*(\d+)\s*(.*?)(?=资产包\s*\d+|$)',s)}
def split_line(row):
    values=package_values(row.get('招租底价原文',''))
    if len(values)<2:return [row]
    areas=package_values(row.get('出租面积原文',''))
    records=[]
    for key,price in values.items():
        r=dict(row);r.update(资产包名称='资产包'+key,招租底价原文=price,出租面积原文=areas.get(key,''),挂牌底价元每年='')
        for field in ['名义挂牌元每建筑㎡每月','建筑或房屋面积㎡','土地面积㎡']:r[field]=''
        for field,label in [('建筑或房屋面积㎡','建筑面积'),('土地面积㎡','土地面积')]:
            m=re.findall(label+r'[：:]?([\d.]+)(?:㎡|平方米|m²)',r['出租面积原文'])
            if len(m)==1:r[field]=m[0]
        val=money(price)
        if val is not None:r['挂牌底价元每年']=str(val)
        if val and r['建筑或房屋面积㎡'] and Decimal(r['建筑或房屋面积㎡'])>0:r['名义挂牌元每建筑㎡每月']=str(round(val/12/Decimal(r['建筑或房屋面积㎡']),2))
        r['核验提示']='按正文资产包编号拆分；请核对对应场次及出租范围。'
        records.append(r)
    return records
def main(root=ROOT,dest=DEST,registry=None):
    dest.mkdir(parents=True,exist_ok=True)
    rows=[];imgrows=[];articles=[];registry=read(root/'标题筛选/全合集复筛.csv') if registry is None else registry;lookup={}
    members={article_key(r['原文链接']):r for r in registry if r['筛选'] in ('建议采集','补采')}
    data=[]
    if members and (root/'文章.sqlite3').exists():
        with sqlite3.connect(root/'文章.sqlite3') as db:
            data=db.execute('select data from articles').fetchall()
    for k,(js,) in enumerate(data):
        a=json.loads(js);meta=members.get(article_key(a['原文链接']))
        if meta is None:continue
        a['发布日期']=meta.get('发布日期') or a['发布日期']
        markup=(root/a['原文存档']).read_text('utf8')
        # Keep only the article subtree, skipping the outer page's tracking and styling scripts.
        tag=markup.index('id="js_content"');start=markup.rfind('<',0,tag)
        tree=html.fromstring(markup[start:]);block=tree if tree.get('id')=='js_content' else tree.get_element_by_id('js_content')
        body=BeautifulSoup(html.tostring(block,encoding='unicode'),'html.parser')
        qs=[v for q in projects(body,a) for v in split_line(q)]
        kind=article_type(a)
        for q in qs:
            if not q.get('项目位置'):
                sections=re.findall(r'(?:^|\n)项目\s*\d+\s*\n([^【]{1,110}?)\n项目基本情况\n(.*?)(?=\n项目\s*\d+\s*\n|$)',a['正文'],re.S)
                price=q.get('招租底价原文','')
                names=[''.join(h.split()) for h,t in sections if price and price in ''.join(t.split()) and re.match(r'(?:江苏省)?\S+市',h)]
                if len(names)==1:q['项目位置']=names[0]
            q.update(classify_project(a,q,kind));q['记录口径']='推送内的一次项目线索，同址可重复'
            if q.get('名义挂牌元每建筑㎡每月') and ('分租' in q.get('出租方式','') and not q.get('资产包名称') or q.get('出租面积原文','').count('建筑面积')>1):q['名义挂牌元每建筑㎡每月']=''
            rows.append(q)
        lookup[article_key(a['原文链接'])]=(len(qs),sum(bool(q.get('挂牌底价元每年')) for q in qs))
        articles.append(dict(a,文章类型=kind))
        # Locate table images in the basic information section that precedes a labeled address.
        for img in body.select('img'):
            url=img.get('data-src') or img.get('src','')
            try:
                plausible=float(img.get('data-w',800))>=380 and float(img.get('data-ratio',1))>=.28
            except ValueError:plausible=True
            img.replace_with('§'+url+'§' if plausible else '')
        text=body.get_text('\n',strip=True);ms=list(MARK.finditer(text))
        for idx,m in enumerate(ms):
            chunk=text[m.end():ms[idx+1].start() if idx+1<len(ms) else None]
            begin=chunk.find('【项目位置】')
            if begin<0 or begin>4000:continue
            ra=re.search(r'【项目位置】\s*([^【§]{1,180})',chunk);rp=re.search(r'【招租底价】\s*([^【\n]+)',chunk)
            if not ra or not rp or money(rp[1]) is not None:continue
            for src in re.findall(r'§(https?://[^§\s]+)§',chunk[:begin]):
                if 'mmbiz.' in src and 'wx_fmt=gif' not in src:
                    imgrows.append({'原文链接':a['原文链接'],'发布日期':a['发布日期'],'项目位置':''.join(ra[1].split()),'底价原文':rp[1].strip(),'图片链接':src})
    export_csv(dest/'逐篇采集清单.csv',['标题','原文链接','发布日期','筛选','命中词','状态','项目线索行','有年挂牌底价行'],(dict(r,状态='已采集' if article_key(r['原文链接']) in lookup else ('正文待重试' if article_key(r['原文链接']) in members else '未入选'),**dict(zip(['项目线索行','有年挂牌底价行'],lookup.get(article_key(r['原文链接']),('',''))))) for r in registry))
    export_csv(dest/'文章与正文.csv',['标题','原文链接','公众号','发布日期','文章类型','正文','正文图片链接'],articles)
    keys=FIELDS+CLASS_FIELDS+['记录口径']
    export_csv(dest/'项目线索明细.csv',keys,rows)
    priced=[r for r in rows if r.get('挂牌底价元每年')]
    export_csv(dest/'正文挂牌年租金.csv',['项目城市','项目位置','资产包名称','用途分类','发布日期','出租面积原文','建筑或房屋面积㎡','招租底价原文','挂牌底价元每年','名义挂牌元每建筑㎡每月','税费原文','标题','原文链接','核验提示'],priced)
    export_csv(dest/'转引表格的图片线索.csv',['项目位置','发布日期','底价原文','图片链接','原文链接'],imgrows)
    print('文章',len(articles),'项目线索',len(rows),'有年价',len(priced),'可换算',sum(bool(r.get('名义挂牌元每建筑㎡每月')) for r in priced),'图片',len(imgrows))
if __name__=='__main__':main()

