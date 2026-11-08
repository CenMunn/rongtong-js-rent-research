"""融通江苏招租推送的项目级提取。仅解析 HTML 里实际存在的文字；图片留待核验。"""
import re
from decimal import Decimal
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

FIELDS = ["原文链接", "公众号", "发布日期", "标题", "项目序号", "项目标题", "项目位置", "项目简介",
          "拟招租业态", "出租面积原文", "建筑或房屋面积㎡", "土地面积㎡", "场地面积亩",
          "招租底价原文", "挂牌底价元每年", "税费原文", "名义挂牌元每建筑㎡每月","出租方原文","资产包名称",
          "竞价保证金原文", "出租方式", "交付状态", "租赁年限", "免租期", "递增方式",
          "支付方式", "报名截止", "保证金截止", "外部链接", "图片线索", "表格文字", "核验提示"]
ALIASES = {
    "出租方":"出租方原文","出租单位":"出租方原文","资产包名称":"资产包名称",
    "项目位置":"项目位置", "项目简介":"项目简介", "拟招租业态":"拟招租业态", "招租业态":"拟招租业态",
    "出租面积":"出租面积原文","招商面积":"出租面积原文","项目地点":"项目位置","招商业态":"拟招租业态","租赁业态":"拟招租业态","租赁面积":"出租面积原文","招租面积":"出租面积原文", "竞价招租底价":"招租底价原文", "招租底价":"招租底价原文",
    "竞价保证金":"竞价保证金原文", "租赁年限":"租赁年限","出租年限":"租赁年限","免租期":"免租期",
    "出租方式":"出租方式","交付状态":"交付状态","支付方式":"支付方式","递增方式":"递增方式",
    "租金递增":"递增方式","报名截止日期":"报名截止","保证金缴纳截止日期":"保证金截止"}
NUM=r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
MARK=re.compile(r"(?m)^[ \t]*(?:(?:[（(]一[)）]|0?1)[ \t]*)?项\s*目\s*基\s*本\s*(?:情\s*况|信\s*息)[ \t]*$")
LABEL=re.compile(r"【([^【】]{1,22})】")
def money(s):
    if re.search(r"\d\s*[-~至—]\s*\d|起步|起至|元\s*[/／]\s*(?:月|日|天|平|㎡|m²)|每平方米|总租金",s):return None
    vals=re.findall(r"("+NUM+r")\s*(万?)元",s)
    if len(vals)!=1 or not re.search(r"首年|年租金|元\s*[/／]\s*年|元\s*每年",s):return None
    return Decimal(vals[0][0].replace(",",""))*(10000 if vals[0][1] else 1)

def table_data(t):
    # Expand merged headers so the columns containing floor, deposit and area stay distinct.
    grid={}; lines=[]
    for y,tr in enumerate(t.select("tr")):
        x=0; values=[]
        for cell in tr.find_all(["th","td"],recursive=False):
            while (y,x) in grid:x+=1
            value="".join(cell.stripped_strings);values.append(value)
            def span(k):
                s=cell.get(k,"1");return min(100,max(1,int(s))) if s.isdecimal() else 1
            w=span("colspan")
            for yy in range(y,y+span("rowspan")):
                for xx in range(x,x+w):grid[yy,xx]=value
            x+=w
        if values:lines.append(" | ".join(values))
    inds=[y for y in range(len(t.select("tr"))) if re.fullmatch(r"\d+",grid.get((y,0),""))]
    if len(inds)!=1:return {},lines
    y=inds[0];vals={}
    for (yy,x),v in grid.items():
        if yy!=y:continue
        header="".join(grid.get((i,x),"") for i in range(y))
        for pattern,key in [(r"资产包名称","资产包名称"),(r"房地产位置|^位置$","项目位置"),(r"房屋面积|建筑面积","建筑或房屋面积㎡"),
                            (r"土地面积","土地面积㎡"),(r"场地面积.*亩","场地面积亩"),
                            (r"招租底价|年租金底价","招租底价原文"),(r"竞价保证金","竞价保证金原文")]:
            if re.search(pattern,header) and v and key not in vals:
                if "面积" in key and key!="场地面积亩" and "亩" in header:continue
                if key=="招租底价原文" and re.fullmatch(NUM,v) and re.search(r"元[/／]年",header):
                    v+=("万元/年" if "万元" in header else "元/年")
                vals[key]=v
    return vals,lines

def split_packages(chunk, title):
    """一些公告以字段为小标题，在每个字段下分别列出各资产包。"""
    info=re.split(r"可通过扫描下方|[（(]二[)）]\s*项目图片",chunk,maxsplit=1)[0]
    markers=re.findall(r"(?m)^资产包\s*(\d+)[：:]?",info)
    if len(set(markers))<2 or not re.search(r"(?m)^资产包\s*\d+[：:]\s*首年租金",info):
        return None
    shared=[]; values={k:[] for k in dict.fromkeys(markers)}; section=""
    for line in info.splitlines():
        line=line.strip()
        label=line.strip("【】")
        if label in ALIASES:
            section=label
            continue
        if line.startswith("【") or not line or line.startswith("§"):
            section=""
            continue
        m=re.fullmatch(r"资产包\s*(\d+)\s*[：:]?(.*)",line)
        if m:
            num,value=m.groups()
            if not value.strip():continue
            label="出租面积" if section=="项目简介" and "面积" in value else section
            if label in ALIASES:values[num].append(f"【{label}】{value.strip()}")
        elif section and section not in ("竞价招租底价","竞价保证金","出租面积"):
            shared.append(f"【{section}】{line}")
    location=re.match(r"^([^（(丨|]+?号[^（(丨|]*)[（(]",title)
    address="【项目位置】"+location[1].strip() if location else ""
    return [(f"资产包{k}",address+"".join(shared)+f"【资产包名称】资产包{k}"+''.join(v)) for k,v in values.items()]

def projects(body, meta):
    doc=BeautifulSoup(str(body),"html.parser")
    tables=[];imgs=[];urls=[]
    for table in list(doc.select("table")):
        if table.parent is None:continue
        tables.append(table_data(table));table.replace_with(f"\n§T{len(tables)-1}§\n")
    for img in doc.select("img"):
        src=img.get("data-src") or img.get("src") or ""
        imgs.append(src);img.replace_with(f"\n§I{len(imgs)-1}§\n")
    for a in doc.select("a[href]"):
        url=urljoin(meta["原文链接"],a["href"])
        if urlsplit(url).scheme in ("http","https"):
            urls.append(url);a.append(f"\n§L{len(urls)-1}§\n")
    text=doc.get_text("\n",strip=True)
    markers=list(MARK.finditer(text))
    numbered=False
    if not markers and re.search(r"首年租金|竞价招租底价",text):
        markers=list(re.finditer(r"(?m)^项目\s*\d+\s*$",text));numbered=bool(markers)
    starts=[(m.start(),m.end()) for m in markers]
    if not starts:
        starts=[(m.start(),m.start()) for m in re.finditer("【项目位置】",text)]
    if not starts and ("【招租底价】" in text or "【竞价招租底价】" in text or re.search("招租|招募",meta["标题"])):
        starts=[(0,0)]
    result=[]; sections=[]
    for i,(pos,start) in enumerate(starts):
        prev=[l for l in text[:pos].splitlines() if l.strip() and "§" not in l]
        head=prev[-1] if markers and prev and len(prev[-1])<=80 else (meta["标题"] if len(starts)==1 else "")
        if markers:
            block=re.search(r"(?:^|\n)项目\s*\d+\s*\n([^§【】]{1,100})$",re.sub(r"§[^§]+§","",text[:pos]).rstrip())
            if block:head="".join(block[1].split())
        chunk=text[start:starts[i+1][0] if i+1<len(starts) else None]
        if numbered:
            first=re.sub(r"§[^§]*§","",chunk).strip().splitlines()
            if first:head=first[0].strip()
        bundles=split_packages(chunk,meta["标题"])
        if bundles:
            sections.extend((name,details) for name,details in bundles)
        else:
            sections.append((head,chunk))
    for i,(head,chunk) in enumerate(sections):
        part=re.split(r"可通过扫描下方|——\s*特别提醒|\n公告详情",chunk,maxsplit=1)[0]
        names="|".join(map(re.escape,sorted(set(ALIASES)|{"其他信息","商业优势","业务咨询"},key=len,reverse=True)))
        part=re.sub(r"(?m)^("+names+r")[ \t]*(?:(?:\n\s*)?[：:]\s*|\s*$)",r"【\1】",part)
        row={k:meta[k] for k in ["原文链接","公众号","发布日期","标题"]};row.update(项目序号=i+1,项目标题=head)
        notes=[]; labels=list(LABEL.finditer(part))
        for j,m in enumerate(labels):
            key=ALIASES.get(re.sub(r"\s+","",m[1]))
            if not key:continue
            v=part[m.end():labels[j+1].start() if j+1<len(labels) else None]
            v=re.split(r"§|可通过扫描下方|特别提示|\n[（(][二三四]|\n商业优势|\n点击了解项目",v)[0].strip("：: \n")
            v=re.sub(r"\s+","",v)
            if key in row and row[key]!=v:notes.append("标签重复，需核对项目边界");continue
            row[key]=v
        if not row.get("项目位置") and re.fullmatch(r"(?:(?:江苏|安徽)省)?[\u4e00-\u9fff]{2,6}市[^【】丨|]{1,80}(?:号|号.*|项目|大厦|广场|盐场|路|街|巷)",head):
            row["项目位置"]=head
        if not row.get("出租面积原文"):
            areas=re.findall(r"(?:项目|房屋|出租|本次出租)?建筑面积[约为：:\s]*"+NUM+r"\s*(?:平方米|㎡|m²|平米)",row.get("项目简介",""))
            if len(areas)==1:row["出租面积原文"]=areas[0]
        rawtables=[];tablefields={}
        for idx in re.findall(r"§T(\d+)§",part):
            fields,lines=tables[int(idx)];rawtables.extend(lines)
            for k,v in fields.items():
                if k in tablefields:notes.append("多个表格含同名字段，需人工复核")
                else:tablefields[k]=v
        row["表格文字"]="\n".join(rawtables)
        for key,pattern in [("建筑或房屋面积㎡","建筑面积|房屋面积"),("土地面积㎡","土地面积"),("场地面积亩","场地面积")]:
            unit="亩" if key=="场地面积亩" else r"(?:平方米|㎡|m²|m2|平米)"
            m=re.search("(?:"+pattern+r")[\s：:约为]*("+NUM+r")\s*"+unit,row.get("出租面积原文",""),re.I)
            t=re.fullmatch("("+NUM+r")\s*(?:"+unit+")?",tablefields.get(key,""),re.I)
            if m and t and Decimal(m[1].replace(",",""))!=Decimal(t[1].replace(",","")):notes.append("正文与表格面积冲突")
            if m or t:row[key]=(m or t)[1].replace(",","")
        for key in ["项目位置","竞价保证金原文","招租底价原文","资产包名称"]:
            if key not in row and key in tablefields:row[key]=tablefields[key]
        p=row.get("招租底价原文","");val=money(p);tv=money(tablefields.get("招租底价原文",""))
        if tv is not None and val!=tv:notes.append("正文与表格底价口径待核")
        if val is not None:
            row["挂牌底价元每年"]=format(val,"f");area=Decimal(row.get("建筑或房屋面积㎡","0"))
            if area>0 and not notes:row["名义挂牌元每建筑㎡每月"]=format(val/12/area,".2f")
        else:notes.append("未确认年度底价")
        tax=re.search(r"(不含税|含税)(?:[，,、]?税点\s*[\d.]+%)?",p)
        row["税费原文"]=tax[0] if tax else ""
        if not row.get("项目位置"):notes.append("地址待核")
        if not row.get("建筑或房屋面积㎡") and not row.get("场地面积亩"):notes.append("面积待核（可能在图片中）")
        if not labels and not tablefields:notes.append("缺少可读标签/表格，仅为待审线索")
        row["图片线索"]="\n".join(dict.fromkeys(imgs[int(x)] for x in re.findall(r"§I(\d+)§",chunk) if imgs[int(x)]))
        hrefs=[urls[int(x)] for x in re.findall(r"§L(\d+)§",chunk)]
        hrefs.extend(re.findall(r"https?://[^\s§<>，。]+",chunk))
        row["外部链接"]="\n".join(dict.fromkeys(hrefs))
        row["核验提示"]="；".join(dict.fromkeys(notes+["须核对出租主体及招租文件，金额为挂牌口径"]))
        result.append(row)
    return result

