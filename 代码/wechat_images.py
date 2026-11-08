"""从文章.csv下载正文图片，保存中文OCR结果。运行时无需重新打开微信文章。"""
import argparse
import csv
import hashlib
import os
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from tempfile import NamedTemporaryFile

import numpy as np
import requests
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from wechat_amounts import FIELDS as AMOUNT_FIELDS, audit

INDEX = ["文章链接","标题","图片序号","图片URL","本地图片","宽","高","状态","OCR文字（待核）","问题"]
LINES = ["文章链接","图片序号","本地图片","文字序号","文字","模型分数","坐标（像素）"]

def save_csv(path,fields,rows):
    with NamedTemporaryFile(dir=path.parent,mode="w",newline="",encoding="utf-8-sig",delete=False) as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    os.replace(f.name,path)

def download(session,url,article,folder):
    key=hashlib.sha256(url.encode()).hexdigest()
    matches=list(folder.glob(key+".*"))
    if matches:
        with Image.open(matches[0]) as im:return matches[0],im.convert("RGB")
    parts=urlsplit(url)
    if parts.hostname not in ("mmbiz.qpic.cn","mmbiz.qlogo.cn") or parts.scheme not in ("http","https"):
        raise ValueError("图片域名待核")
    with session.get(parts._replace(scheme="https").geturl(),headers={"Referer":article},stream=True,timeout=(5,20)) as r:
        r.raise_for_status()
        buf=BytesIO()
        for block in r.iter_content(65536):
            buf.write(block)
            if buf.tell()>20*1024*1024:raise ValueError("图片超过20 MB")
    buf.seek(0)
    with Image.open(buf) as im:
        if im.width*im.height>30000000:raise ValueError("图片像素数超限")
        path=folder/(key+"."+im.format.lower())
        rgb=im.convert("RGB")
    with NamedTemporaryFile(dir=folder,delete=False) as f:f.write(buf.getvalue())
    os.replace(f.name,path)
    return path,rgb

def main():
    p=argparse.ArgumentParser(description=__doc__)
    base=Path(__file__).resolve().parent
    default=base/"公众号采集结果/文章.csv"
    if not default.is_file() and (base.parent/"爬取数据/文章.csv").is_file():
        default=base.parent/"爬取数据/文章.csv"
    p.add_argument("--articles",type=Path,default=default)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if not args.articles.is_file():
        p.error("请先下载公众号文章，或通过 --articles 指定爬虫导出的文章.csv")
    out=args.out or args.articles.parent/"图片识别"; folder=out/"图片";folder.mkdir(parents=True,exist_ok=True)
    engine=RapidOCR()
    rows=[];lines=[]
    with args.articles.open(encoding="utf-8-sig",newline="") as f,requests.Session() as session:
        for article in csv.DictReader(f):
            url=article["原文链接"]
            for i,src in enumerate(dict.fromkeys(article["正文图片链接"].splitlines()),1):
                if not src:continue
                row={"文章链接":url,"标题":article["标题"],"图片序号":i,"图片URL":src}
                try:
                    path,im=download(session,src,url,folder)
                    row.update(本地图片=str(path.relative_to(out)),宽=im.width,高=im.height)
                    result,_=engine(np.asarray(im)[:,:,::-1].copy())
                    tokens=result or []
                    row.update(状态="已识别，待核" if tokens else "未识别到文字")
                    row["OCR文字（待核）"]="\n".join(t for _,t,_ in tokens)
                    for j,(pts,t,score) in enumerate(tokens,1):
                        lines.append(dict(zip(LINES,[url,i,row["本地图片"],j,t,score,str(pts)])))
                except Exception as exc:
                    row.update(状态="失败",问题=str(exc))
                rows.append(row)
                print(i,row["状态"],row.get("问题",""),flush=True)
    save_csv(out/"图片识别.csv",INDEX,rows);save_csv(out/"文字位置.csv",LINES,lines)
    projects=args.articles.parent/"项目线索.csv"
    if projects.exists():
        save_csv(out/"图片金额核对.csv",AMOUNT_FIELDS,audit(out,projects))
    print(f"图片 {len(rows)} 张，失败 {sum(r['状态']=='失败' for r in rows)} 张：{out}")
    return int(any(r["状态"]=="失败" for r in rows))
if __name__=="__main__":
    raise SystemExit(main())

