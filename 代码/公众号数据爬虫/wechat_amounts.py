"""用原图表格线约束金额识别，再与同一资产包的正文字段核对。"""
import csv
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import numpy as np
from PIL import Image

FIELDS=["文章链接","图片序号","本地图片","资产包","字段","原始OCR片段","识别金额元","正文金额元","结果"]
def number(s):
    m=re.fullmatch(r"([0-9]+(?:\.\d+)?)元?",s.strip().replace(",",""))
    return Decimal(m[1]) if m else None

def blocks(rows):
    items=[]
    for r in rows:
        pts=json.loads(r["坐标（像素）"]);xs,ys=zip(*pts)
        items.append((r["文字"].strip(),min(xs),max(xs),min(ys),max(ys)))
    return items

def cell_amount(items,header,pixels):
    _,left,right,_,bottom=header
    x=round((left+right)/2)
    # Long vertical rules bound the column. Require real ruled cells before joining fragments.
    vertical=np.where((pixels<155).sum(axis=0)>pixels.shape[0]*.30)[0]
    lo=vertical[vertical<x];hi=vertical[vertical>x]
    if not len(lo) or not len(hi):return "",None
    lo,hi=int(lo[-1]),int(hi[0])
    line_ys=np.where((pixels[:,lo:hi+1]<155).mean(axis=1)>.81)[0]
    boundaries=[int(y) for y in line_ys if y>bottom]
    tokens=[b for b in items if b[3]>bottom and lo<(b[1]+b[2])/2<hi and re.fullmatch(r"[0-9,.]+",b[0])]
    if not boundaries:return "",None
    # Group by ruled cell; several numeric cells in the same column are ambiguous.
    groups=defaultdict(list)
    for t in tokens:
        above=[y for y in boundaries if y<t[3]]
        below=[y for y in boundaries if y>t[4]]
        if above and below:groups[(above[-1],below[0])].append(t)
    raw=" / ".join(" | ".join(v[0] for v in sorted(g,key=lambda v:v[3])) for g in groups.values())
    if len(groups)!=1:return raw,None
    ts=sorted(next(iter(groups.values())),key=lambda v:v[3])
    if len(ts)==1:return raw,number(ts[0][0])
    if len(ts)==2:
        a,b=ts
        if (re.fullmatch(r"[\d,]+\.",a[0]) and re.fullmatch(r"\d{1,2}",b[0]) and
                abs(a[1]-b[1])<=max(6,(a[4]-a[3])/2) and 0<=b[3]-a[4]<=1.5*(a[4]-a[3])):
            return raw,number(a[0]+b[0])
    return raw,None

def audit(out,projects):
    def read(path):
        with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
    records=read(projects);grouped=defaultdict(list)
    for r in read(out/"文字位置.csv"):grouped[(r["文章链接"],r["图片序号"])].append(r)
    result=[]
    for idx in read(out/"图片识别.csv"):
        url,i=idx["文章链接"],idx["图片序号"]; img=idx["本地图片"]
        items=blocks(grouped[(url,i)])
        pats=[("招租底价","挂牌底价元每年",r"竞价招租底|年租金底价|招租底价"),("竞价保证金","竞价保证金原文",r"竞价保")]
        headers=[[v for v in items if re.search(pattern,v[0]) and len(v[0])<14] for _,_,pattern in pats]
        if not any(headers):continue
        with Image.open(out/img) as im:pixels=np.array(im.convert("L"))
        nums={number(v[0]) for v in items if number(v[0]) is not None}
        candidates=[r for r in records if r["原文链接"]==url and number(r["建筑或房屋面积㎡"]) in nums]
        proj=candidates[0] if len(candidates)==1 else {}
        for (name,key,_),hh in zip(pats,headers):
            raw,value=cell_amount(items,hh[0],pixels) if len(hh)==1 else ("",None)
            expected=number(proj.get(key,""))
            state="一致" if value is not None and expected is not None and value==expected else "待核"
            result.append(dict(zip(FIELDS,[url,i,img,proj.get("资产包名称",""),name,raw,value,expected,state])))
    return result

