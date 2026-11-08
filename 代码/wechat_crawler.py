"""公开微信文章采集。运行 python wechat_crawler.py --help 查看参数。"""

import argparse
import hashlib
import csv
import html
import json
import re
import sqlite3
import sys
import time
from collections import deque
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from wechat_projects import FIELDS, projects
from wechat_download import ArticleDownloader
from wechat_categories import CLASS_FIELDS, article_type, classify_project


BASE = Path(__file__).resolve().parent
HOST = "https://mp.weixin.qq.com"
CHINA = timezone(timedelta(hours=8))
KEYWORDS = "酒店 宾馆 写字楼 办公 商铺 门面 商业街 厂房 仓库 仓储 产业园 园区 公寓 招租 租金 南京 苏州".split()


def article_key(url):
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or parts.netloc.lower() != "mp.weixin.qq.com":
        raise ValueError("请输入微信公众平台文章链接")
    if re.fullmatch(r"/s/[A-Za-z0-9_-]+/?", parts.path):
        return HOST + parts.path.rstrip("/")
    query = parse_qs(parts.query)
    if parts.path == "/s" and all(query.get(k) for k in ("__biz", "mid", "idx")):
        return HOST + "/s?" + urlencode([(k, query[k][0]) for k in ("__biz", "mid", "idx")])
    raise ValueError("链接缺少文章标识，请从文章右上角复制原文链接")


def publication_date(soup):
    tag = soup.select_one("#publish_time")
    scripts = "\n".join(s.get_text() for s in soup.find_all("script"))
    values = [tag.get_text(strip=True)] if tag else []
    values += re.findall(r"""\b(?:var\s+)?(?:publish_time|createTime)\s*[:=]\s*['"]([^'"]+)""", scripts)
    for value in values:
        match = re.search(r"(20\d\d)[年./-](\d{1,2})[月./-](\d{1,2})", value)
        if match:
            try:
                return datetime(*map(int, match.groups())).date().isoformat()
            except ValueError:
                continue
    match = re.search(r"""\b(?:ct|create_time)\s*[:=]\s*['"]?(\d{10})\b""", scripts)
    return datetime.fromtimestamp(int(match[1]), CHINA).date().isoformat() if match else ""


def manifest_entries(path):
    """TXT 每行可带说明或 Markdown 链接；CSV 读取明确的链接列。"""
    if path.suffix.lower()==".csv":
        with path.open(encoding="utf-8-sig",newline="") as f:
            rows=csv.DictReader(f)
            column=next((name for name in ("原文链接","文章链接","链接","URL","url") if name in (rows.fieldnames or [])),None)
            if column is None:
                raise ValueError("CSV 需要一列名为“原文链接”“文章链接”“链接”或 URL")
            for row in rows:
                if (row[column] or "").strip():yield html.unescape(row[column].strip()),""
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line=line.strip()
        if not line or line.startswith("#"):continue
        text,sep,local=line.partition("\t")
        urls=re.findall(r'https?://mp\.weixin\.qq\.com/s(?:/|\?)[A-Za-z0-9_%/?&=;.#~-]+',text)
        for url in urls or [text]:
            yield html.unescape(url),local.strip() if sep else ""


def parse_article(data, url, account):
    soup = BeautifulSoup(data, "html.parser", from_encoding="utf-8")
    body = soup.select_one("#js_content")
    if body is None:
        raise ValueError("未找到正文，可能是验证页、已删除文章或页面格式不同")
    name = soup.select_one("#js_name, #js_profile_qrcode .profile_nickname")
    nickname = name.get_text(strip=True) if name else ""
    if nickname != account:
        raise ValueError(f"账号未匹配（页面识别为“{nickname or '未知'}”），请核对原文")
    title = soup.select_one("#activity-name")
    meta = soup.select_one('meta[property="og:title"]')
    heading = title.get_text(strip=True) if title else (meta.get("content", "") if meta else "")
    if not heading:
        raise ValueError("缺少文章标题")
    for tag in body.select("style, script"):
        tag.decompose()
    content = body.get_text("\n", strip=True)
    images = [i.get("data-src") or i.get("src") for i in body.select("img")]
    images = [i for i in images if i and i.startswith(("http://", "https://"))]
    if not content and not images:
        raise ValueError("正文为空，请核对原文")
    links = []
    for anchor in body.select("a[href]"):
        link = urljoin(url, html.unescape(anchor["href"]))
        try:
            article_key(link)
        except ValueError:
            continue
        links.append(link)
    row = {
        "原文链接": url, "公众号": nickname, "标题": heading,
        "发布日期": publication_date(soup), "正文": content,
        "关键词线索": "、".join(k for k in KEYWORDS if k in heading + content),
        "正文图片链接": "\n".join(images), "正文内文章链接": list(dict.fromkeys(links)),
        "采集时间": datetime.now(CHINA).isoformat(timespec="seconds")
    }
    row["项目线索"] = projects(body, row)
    return row


def export_csv(path, fields, rows):
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False,
                            encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v)
                             for k, v in row.items() if k in fields})
    Path(file.name).replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE / "微信文章链接.txt", help="每行一个原文链接，可用 Tab 附本地 HTML 路径")
    parser.add_argument("--url", action="append", help="直接传入一篇原文链接，可以重复使用")
    parser.add_argument("--paste", action="store_true", help="提示粘贴文章链接")
    parser.add_argument("--reparse", action="store_true", help="从已下载的 HTML 重新提取数据")
    parser.add_argument("--browser-wait", type=int, default=180, help="浏览器等待正文的秒数，默认180")
    parser.add_argument("--http-only", action="store_true", help="仅尝试直接下载")
    parser.add_argument("--index-html", type=Path, help="从已保存的文章目录 HTML 中批量提取原文超链接")
    parser.add_argument("--account", default="融通地产江苏公司", help="只接收署名完全匹配的公众号文章")
    parser.add_argument("--out", type=Path, default=BASE / "公众号采集结果")
    parser.add_argument("--follow", action="store_true", help="继续查找正文中链接到的微信文章")
    parser.add_argument("--limit", type=int, help="限制本次未采集链接数；默认处理完整清单，追踪文章链接时默认30")
    args = parser.parse_args()
    if (args.limit is not None and args.limit < 1) or args.browser_wait < 1:
        parser.error("--limit 与 --browser-wait 必须是正整数")
    if args.paste:
        args.url = (args.url or []) + [input("粘贴微信文章链接，再按回车：").strip()]
    queue = deque((u,"") for u in (args.url or []))
    if not args.url:
        try:
            queue.extend(manifest_entries(args.input))
        except ValueError as exc:
            parser.error(str(exc))
    if args.index_html:
        index = BeautifulSoup(args.index_html.read_bytes(), "html.parser", from_encoding="utf-8")
        for anchor in index.select("a[href]"):
            link = urljoin(HOST, html.unescape(anchor["href"]))
            try:
                article_key(link)
            except ValueError:
                continue
            queue.append((link, ""))
    if not queue:
        parser.error(f"请先在 {args.input} 填入文章链接")
    args.out.mkdir(parents=True, exist_ok=True)
    failures = []
    seen = set()
    attempted = skipped = duplicates = 0
    limit=args.limit if args.limit is not None else (30 if args.follow else None)
    log=[]
    with sqlite3.connect(args.out / "文章.sqlite3") as db, requests.Session() as session, ExitStack() as stack:
        downloader = ArticleDownloader(session, stack, args.browser_wait, not args.http_only)
        db.execute("CREATE TABLE IF NOT EXISTS articles (account TEXT, id TEXT, data TEXT, PRIMARY KEY(account,id))")
        while queue and (limit is None or attempted < limit):
            url, local = queue.popleft()
            try:
                key = article_key(url)
                if key in seen:
                    duplicates += 1
                    log.append({"链接":url,"状态":"批内重复"})
                    continue
                seen.add(key)
                saved = db.execute("SELECT data FROM articles WHERE account=? AND id=?", (args.account, key)).fetchone()
                if saved and not args.reparse and "项目线索" in json.loads(saved[0]):
                    skipped += 1
                    row = json.loads(saved[0])
                else:
                    attempted += 1
                    previous = json.loads(saved[0]) if saved else {}
                    if args.reparse and previous.get("原文存档"):
                        data = (args.out / previous["原文存档"]).read_bytes()
                        method = previous.get("获取方式", "原文存档")
                    elif local:
                        data = (args.input.parent / local).read_bytes()
                        method = "本地文件"
                    else:
                        if attempted > 1:
                            time.sleep(2)
                        data, method = downloader.get(url)
                    row = parse_article(data, url, args.account)
                    row["获取方式"] = method
                    archive = args.out / "原文存档"
                    archive.mkdir(exist_ok=True)
                    archive_path = archive / (hashlib.sha256(data).hexdigest()+".html")
                    archive_path.write_bytes(data)
                    row["原文存档"] = str(archive_path.relative_to(args.out))
                    db.execute("INSERT OR REPLACE INTO articles VALUES (?,?,?)", (args.account, key, json.dumps(row, ensure_ascii=False)))
                    db.commit()
                    print(f"已采集 {row['标题']}")
                log.append({"链接":url,"状态":"使用已有记录" if saved and not args.reparse and "项目线索" in json.loads(saved[0]) else "已处理","文章类型":article_type(row),"标题":row["标题"],"项目线索数":len(row.get("项目线索",[]))})
                if args.follow:
                    queue.extend((link, "") for link in row["正文内文章链接"])
            except (ValueError, OSError, requests.RequestException) as err:
                failures.append({"链接": url, "原因": str(err)})
                log.append({"链接":url,"状态":"失败","原因":str(err)})
                print(f"未采集 {url}  {err}", file=sys.stderr)
        def records():
            for record, in db.execute("SELECT data FROM articles WHERE account=? ORDER BY rowid", (args.account,)):
                row=json.loads(record)
                row["文章类型"]=article_type(row)
                yield row
        fields = ["公众号", "发布日期", "标题","文章类型", "关键词线索", "原文链接", "正文", "正文图片链接", "采集时间","原文存档","获取方式"]
        export_csv(args.out / "文章.csv", fields, records())
        export_csv(args.out / "项目线索.csv", FIELDS+CLASS_FIELDS,
                   (dict(item,**classify_project(r,item,r["文章类型"])) for r in records() for item in r.get("项目线索", [])))
        log.extend({"链接":url,"状态":"达到上限，未处理"} for url,_ in queue)
        export_csv(args.out / "本次批量清单.csv", ["链接","状态","文章类型","标题","项目线索数","原因"], log)
        export_csv(args.out / "本次失败.csv", ["链接", "原因"], failures)
    print(f"本次尝试 {attempted}，已存跳过 {skipped}，批内重复 {duplicates}，失败 {len(failures)}。输出目录 {args.out}")
    if queue:
        print("达到本次上限。已入库文章会自动跳过；持续失败的链接请修复或移出清单后继续。")
    return int(bool(failures))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as error:
        sys.exit(f"读写失败（请检查文件路径，并关闭 Excel 中打开的结果表）：{error}")
