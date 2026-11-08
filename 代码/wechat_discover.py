"""读取微信合集/历史列表，按标题生成批量采集清单。"""
import argparse
import csv
import html
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from wechat_crawler import article_key,export_csv

BASE=Path(__file__).resolve().parent
DEFAULT="https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=MzAwNTY4Njc4Mg%3D%3D#wechat_redirect"
FIELDS=["标题","原文链接","筛选","命中词","列表来源"]
def classify(title):
    strong=[w for w in ("竞价招租","招租","招商","出租","招募承租","租赁公告","租赁房源","预热开启","资产预热公告","优质项目推荐") if w in title]
    if strong:return "建议采集","、".join(strong)
    if re.search(r"(?:市|区).{1,48}(?:号|广场).{0,35}项目[）)]?$",title):
        return "建议采集","地址型项目标题"
    if "火热" in title or not title:return "待选","火热" if title else "缺少标题"
    return "未命中",""
def cards(markup,source):
    soup=BeautifulSoup(markup,"html.parser")
    for el in soup.select("[href], [data-url], [data-link], [data-content-url], [data-href]"):
        for attr in ("data-link","data-url","data-content-url","data-href","href"):
            u=urljoin("https://mp.weixin.qq.com",html.unescape(el.get(attr,"")))
            try:key=article_key(u);break
            except ValueError:continue
        else:continue
        heading=el.select_one("[data-title], .album__item-title, .weui_media_title, .js_title, h4")
        title=el.get("data-title") or el.get("title") or (heading.get_text(" ",strip=True) if heading else el.get_text(" ",strip=True))
        status,word=classify(title)
        yield key,dict(zip(FIELDS,[title,u,status,word,source]))
def live(url,max_scroll):
    from playwright.sync_api import sync_playwright
    if urlsplit(url).hostname!="mp.weixin.qq.com":raise ValueError("请提供微信公众平台的列表链接")
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="msedge",headless=False)
        try:
            page=browser.new_page();page.goto(url,wait_until="domcontentloaded",timeout=30000)
            idle=0;seen=set()
            for _ in range(max_scroll+1):
                page.wait_for_timeout(1000)
                body=page.locator("body").inner_text()
                if ("请在微信客户端打开链接" in body or "环境异常" in body or "captcha" in page.url):
                    raise ValueError("该列表需要微信客户端或验证。请换可分享的合集链接，或传入包含文章卡片的列表 HTML。")
                entries=list(cards(page.content(),url));yield from entries
                new={k for k,_ in entries}-seen;seen.update(new)
                idle=0 if new else idle+1
                if idle>=3:break
                page.evaluate("""() => {window.scrollTo(0,document.body.scrollHeight);for(const e of document.querySelectorAll('*')) if(e.clientHeight>100 && e.scrollHeight>e.clientHeight+50 && /auto|scroll/.test(getComputedStyle(e).overflowY))e.scrollTop=e.scrollHeight;}""")
        finally:browser.close()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",help="微信合集网址或已保存的列表HTML路径")
    p.add_argument("--prompt",action="store_true")
    p.add_argument("--download",action="store_true",help="继续下载候选原文，沿用公众号名称校验")
    p.add_argument("--include-weak",action="store_true",help="同时下载仅含火热或缺少标题的候选")
    p.add_argument("--out",type=Path,default=BASE/"公众号采集结果")
    a=p.parse_args();src=a.source or (input("粘贴微信合集网址或列表HTML路径（回车尝试账号主页）：").strip().strip('"') if a.prompt else "") or DEFAULT
    auditdir=a.out/"标题筛选";auditdir.mkdir(parents=True,exist_ok=True)
    found={};problem=""
    try:
        items=live(src,40) if src.startswith(("http://","https://")) else cards(Path(src).read_text("utf-8-sig"),src)
        ranks={"未命中":0,"待选":1,"建议采集":2}
        for key,row in items:
            if key not in found or ranks[row["筛选"]]>ranks[found[key]["筛选"]]:found[key]=row
    except Exception as exc:problem=str(exc)
    rows=list(found.values());allowed={"建议采集","待选"} if a.include_weak else {"建议采集"}
    candidates=[r for r in rows if r["筛选"] in allowed]
    export_csv(auditdir/"标题筛选记录.csv",FIELDS,rows)
    manifest=auditdir/"候选链接.csv";export_csv(manifest,FIELDS,candidates)
    note=problem or ("未读到文章卡片，无法据此判断该号是否有公告" if not rows else "仅统计本次可见的文章卡片")
    (auditdir/"本次检索说明.txt").write_text(f"{src}\n{note}\n可见文章 {len(rows)}，入选 {len(candidates)}","utf-8-sig")
    print(note, f"可见文章 {len(rows)}，入选 {len(candidates)}。",flush=True)
    if a.download and candidates:
        rc=subprocess.call([sys.executable,str(BASE/"wechat_crawler.py"),"--input",str(manifest),"--out",str(a.out)])
        if rc:return rc
    return int(bool(problem) or not rows)
if __name__=="__main__":raise SystemExit(main())

