"""在本机按融通江苏公众号合集批量采集。用法见 片区合集采集说明.txt。"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

from wechat_crawler import CHINA, article_key, export_csv
from wechat_discover import classify
from nanjing_album_export import main as extract, read

BASE=Path(__file__).resolve().parent
ACCOUNT="融通地产江苏公司"
REVIEW_FIELDS=["原文链接","图片链接","项目城市","项目位置","资产包或房间","建筑面积㎡","表头单位","原图底价","复核状态"]
MASTER_FIELDS=["项目城市","项目位置","资产包或房间","建筑面积㎡","发布日期","金额原文或原图数值","表头单位","挂牌底价元每年","名义挂牌元每建筑㎡每月","税费原文","来源","原文链接","图片链接","复核提示"]

def album_parameters(url):
    parts=urlsplit(url.strip().replace("\\&","&"))
    query=parse_qs(parts.query)
    if parts.hostname!="mp.weixin.qq.com" or parts.path!="/mp/appmsgalbum":
        raise ValueError("请输入微信合集链接")
    biz=query.get("__biz",[""])[0]; aid=query.get("album_id",[""])[0]
    if not biz or not aid.isdecimal():raise ValueError("合集链接缺少 __biz 或 album_id")
    return biz,aid

def discover(url):
    biz,aid=album_parameters(url)
    params=dict(__biz=biz,album_id=aid,action="getalbum",f="json",count=20,is_reverse=0)
    entries={}; info={}; cursor=None
    with requests.Session() as session:
        while True:
            response=session.get("https://mp.weixin.qq.com/mp/appmsgalbum",params=params,timeout=(6,20))
            response.raise_for_status()
            obj=response.json()
            if obj.get("base_resp",{}).get("ret") not in (0,"0"):raise ValueError("合集目录访问未成功，请检查是否需要在微信内验证")
            data=obj["getalbum_resp"];page_meta=data.get("base_info") or {}
            if not info:
                info=page_meta
                if info.get("nickname")!=ACCOUNT:raise ValueError("合集署名与目标公众号不一致")
            elif page_meta.get("nickname") not in (None,"",ACCOUNT):raise ValueError("翻页后合集署名不一致")
            articles=data.get("article_list",[])
            for a in articles:
                link=a["url"].replace("http://mp.weixin.qq.com","https://mp.weixin.qq.com",1)
                status,match=classify(a["title"])
                entries[article_key(link)]={"标题":a["title"],"原文链接":link,"筛选":status,"命中词":match,"发布日期":datetime.fromtimestamp(int(a["create_time"]),CHINA).date().isoformat(),"列表来源":url}
            if str(data.get("continue_flag"))!="1":break
            if not articles:raise ValueError("微信声明还有下一页，但未返回文章")
            next_cursor=(articles[-1]["msgid"],articles[-1]["itemidx"])
            if cursor==next_cursor:raise ValueError("合集分页未前进，请稍后重跑")
            cursor=next_cursor;params.update(begin_msgid=cursor[0],begin_itemidx=cursor[1]);time.sleep(.25)
    if len(entries)!=int(info["article_count"]):
        raise ValueError(f"合集标注{info['article_count']}篇，实际取得{len(entries)}篇；请稍后重跑，本次不覆盖旧目录")
    return list(entries.values()),info["title"]

def table_ocr(dest,root):
    from wechat_images import RapidOCR,download,np
    rows=read(dest/"转引表格的图片线索.csv")
    cache=root/"图片缓存";cache.mkdir(exist_ok=True)
    fields=["原文链接","图片链接","项目位置","发布日期","图片文件","OCR文本","识别状态"]
    engine=None;report=[]
    with requests.Session() as session:
        for r in rows:
            src=r["图片链接"]
            cached=cache/(hashlib.sha256(src.encode()).hexdigest()+".json")
            if cached.exists():
                rec=json.loads(cached.read_text("utf8"))
            else:
                try:
                    path,im=download(session,src,r["原文链接"],cache)
                    if engine is None:engine=RapidOCR()
                    tokens,_=engine(np.asarray(im)[:,:,::-1].copy());tokens=tokens or []
                    rec={"图片文件":str(path.relative_to(root)),"OCR文本":"\n".join(t for _,t,_ in tokens),"识别状态":"待核表头、标的和金额" if tokens else "未检出文字","文字坐标":tokens}
                    tmp=cached.with_suffix(".tmp");tmp.write_text(json.dumps(rec,ensure_ascii=False),"utf8");tmp.replace(cached)
                except (OSError,ValueError,RuntimeError,requests.RequestException) as exc:rec={"识别状态":f"识别失败：{exc}"}
            report.append(dict(r,**rec))
    export_csv(dest/"表图OCR复核清单.csv",fields,report)
    return rows

def decimal(s):
    try:
        n=Decimal(str(s).replace(",","").strip())
        return n if n.is_finite() and n>0 else None
    except InvalidOperation:return None

def merge_prices(dest,root,pictures):
    master=[]
    for r in read(dest/"正文挂牌年租金.csv"):
        master.append(dict(r,**{"资产包或房间":r["资产包名称"],"建筑面积㎡":r["建筑或房屋面积㎡"],"来源":"正文自动提取","金额原文或原图数值":r["招租底价原文"],"图片链接":""}))
    checked=root/"人工核图.csv"
    reviewed=read(checked) if checked.exists() else []
    seen_pictures={(r.get("原文链接"),r.get("图片链接")) for r in reviewed}
    for pic in pictures:
        key=(pic["原文链接"],pic["图片链接"])
        if key not in seen_pictures:
            reviewed.append(dict(pic,复核状态="待核"))
            seen_pictures.add(key)
    export_csv(checked,REVIEW_FIELDS,reviewed)
    refs={(article_key(r["原文链接"]),r["图片链接"]):r for r in pictures}
    issues=[]
    for r in reviewed:
        if r.get("复核状态")!="已核":continue
        try:
            ref=refs[(article_key(r["原文链接"]),r["图片链接"])]
            area=decimal(r["建筑面积㎡"]);raw=decimal(r["原图底价"])
            if raw is None or not r["项目位置"].strip():raise ValueError("缺少有效金额或地址")
            year=raw*{"元/年":1,"万元/年":10000}[r["表头单位"]]
            master.append(dict(r,发布日期=ref["发布日期"],挂牌底价元每年=str(year),金额原文或原图数值=r["原图底价"],来源="图片人工核实",**{"名义挂牌元每建筑㎡每月":f"{year/12/area:.2f}" if area else ""}))
        except (KeyError,ValueError) as e:issues.append(dict(r,问题=f"未通过来源或单位检查：{e}"))
    export_csv(dest/"核图输入异常.csv",REVIEW_FIELDS+["问题"],issues)
    for r in master:
        issues=[]
        if not r["项目位置"]:issues.append("缺地址")
        if not r["名义挂牌元每建筑㎡每月"]:issues.append("单价未确认")
        if not r.get("税费原文"):issues.append("税费未提取")
        r["复核提示"]="；".join(issues)
    export_csv(dest/"挂牌底价总表.csv",MASTER_FIELDS,master)
    return master

def run(url,out):
    _,aid=album_parameters(url);root=out/aid;dest=root/"交付文件";dest.mkdir(parents=True,exist_ok=True)
    registry,name=discover(url);fields=["标题","原文链接","筛选","命中词","发布日期","列表来源"]
    candidates=[r for r in registry if r["筛选"]=="建议采集"]
    export_csv(root/"合集目录.csv",fields,registry);export_csv(root/"候选链接.csv",fields,candidates)
    print(f"{name}：目录{len(registry)}篇，强匹配{len(candidates)}篇。",flush=True)
    if candidates:
        cmd=[sys.executable,str(BASE/"wechat_crawler.py"),"--input",str(root/"候选链接.csv"),"--out",str(root),"--browser-wait","35"]
        rc=subprocess.run(cmd).returncode
        if rc and (root/"本次失败.csv").is_file() and read(root/"本次失败.csv"):
            # 同一清单重试，已入库文章沿用缓存。
            rc=subprocess.run(cmd).returncode
        if rc and not (root/"文章.sqlite3").exists():raise ValueError("正文采集未能启动")
    if not candidates:
        print("本次无强匹配标题；请查看合集目录.csv 的待选文章。")
    extract(root,dest,registry)
    pics=table_ocr(dest,root);master=merge_prices(dest,root,pics)
    states=Counter(r["状态"] for r in read(dest/"逐篇采集清单.csv"));scope=Counter(r["项目城市"] for r in master)
    stats=dict(合集=name,合集ID=aid,目录篇数=len(registry),强匹配篇数=len(candidates),文章状态=dict(states),转引表图线索=len(pics),价格来源=dict(Counter(r["来源"] for r in master)),价格记录按城市=dict(scope),可计算建筑月单价=sum(bool(r["名义挂牌元每建筑㎡每月"]) for r in master))
    (dest/"质量摘要.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),"utf8")
    print(stats,flush=True)
    if (root/"文章.sqlite3").is_file():
        subprocess.run([sys.executable,str(BASE/"wechat_fulltables.py"),"album",str(root),name],check=True)
    return int(bool(states["正文待重试"]))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("url",nargs="?");p.add_argument("--out",type=Path,default=BASE/"outputs/公众号片区采集")
    args=p.parse_args()
    try:sys.exit(run(args.url or input("粘贴融通江苏片区合集链接：").strip(),args.out.resolve()))
    except (ValueError,OSError,KeyError,requests.RequestException) as exc:sys.exit(f"本次未完整完成：{exc}")

