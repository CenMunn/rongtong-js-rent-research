"""从本批官方HTML缓存重建办公补采表，不下载、不修改旧版或主数据。

运行：python 代码/合库准备/build_suzhou_office_followup.py <本批目录>
依赖：beautifulsoup4。输入：补采索引.json、原件/*.html。
静态div表格按标签/值配对；历史Vue页只用JSONDecoder读取内嵌data，禁用eval。
"""
import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup


def listing(path):
    html = path.read_text(encoding="utf-8-sig")
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for value in soup.select("div.value"):
        label = value.find_previous_sibling("div")
        if label:
            fields[label.get_text(" ", strip=True)] = value.get_text(" ", strip=True)
    match = re.search(r'\bdata:\s*(\{\s*"csPhone")', html)
    if match:
        data, _ = json.JSONDecoder().raw_decode(html[match.start(1):])
        a, p = data["asset"], data["project"]
        assert a["projectId"] == p["projectId"]
        mapping = {
            "项目编号": p.get("projectId"), "项目名称": p.get("projectName"),
            "出租面积(m²)": a.get("area"), "坐落位置": a.get("address"),
            "所在楼层": a.get("storey"), "租期": a.get("tenancy"),
            "租金挂牌底价": a.get("rentListBasicPrice"),
            "租金支付要求": p.get("rentPayRequirement"),
            "租金调整方式": p.get("rentAdjustMethod"),
            "其他披露事项": p.get("otherDisclosures"),
            "与出租相关的其他条件": p.get("otherConditions"),
            "使用用途及要求": p.get("useAndRequirement"),
            "挂牌起始日": data.get("startDate"), "挂牌终止日": data.get("endDate"),
        }
        fields.update({k: "" if v is None else str(v) for k, v in mapping.items()})
        unit = re.search(r"rentPriceInputType:\s*'([^']+)'", html)
        assert unit and unit.group(1) == "元/年", "挂牌原价单位未确认"
        mode = "Vue内嵌JSON：asset.area及project条款；非正文占位符"
    else:
        assert "元/年" in fields.get("租金挂牌底价", ""), "挂牌原价单位未确认"
        mode = "静态div：标签与相邻value单元配对"
    assert fields.get("项目编号") and fields.get("出租面积(m²)"), "缺少编号或面积"
    return fields, mode


def result(path, project_id):
    soup = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
    assert "成交年租金" in soup.get_text(), "结果页未披露年租金口径"
    matches = []
    for tr in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
        if cells and cells[0] == project_id:
            assert len(cells) == 6
            matches.append(cells)
    assert len(matches) == 1, f"成交行无法唯一定位：{project_id}"
    cells = matches[0]
    return {"公告期限": cells[2], "年租金": cells[3], "成交日": date_iso(cells[4])}


def date_iso(text):
    parts = re.findall(r"\d+", text)
    assert len(parts) == 3, text
    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(batch):
    index = json.loads((batch / "补采索引.json").read_text(encoding="utf8"))
    rows, extracted = [], []
    for item in index["观察"]:
        pid = item["项目编号"]
        p, mode = listing(batch / item["挂牌文件"])
        assert p["项目编号"] == pid
        c = result(batch / item["成交文件"], pid)
        assert c["成交日"] <= index["截至日"]
        # 同编号、公告期均相符才允许把挂牌面积关联到成交。
        period_parts = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", c["公告期限"])
        assert [date_iso(v) for v in period_parts] == [date_iso(p["挂牌起始日"]), date_iso(p["挂牌终止日"])]
        area = Decimal(p["出租面积(m²)"].replace(",", ""))
        rent = Decimal(c["年租金"].replace(",", ""))
        assert area > 0 and rent > 0
        row = {
            "观察ID": item["观察ID"], "项目编号": pid,
            "楼宇切分组": item["楼宇切分组"], "地址范围": item["地址范围"],
            "披露面积㎡": str(area), "面积口径": item["面积口径"],
            "成交年租金元": str(rent), "名义元每披露㎡月": f"{rent / 12 / area:.6f}",
            "价格性质": "官方公示成交年租金；非合同实收/有效租金",
            "价格期间说明": "挂牌明确首年年租；成交公示仅列年租金，期间及签署合同待核" if "首年年租金" in p.get("与出租相关的其他条件", "") else "公示年租金；实际计租起止待签署合同",
            "成交日": c["成交日"], "用途": p.get("使用用途及要求", ""),
            "物业费处理": item["物业费处理"], "物业费元每㎡月": item["物业费元每㎡月"],
            "公共能耗费元每㎡月": item["公共能耗费元每㎡月"],
            "费用原文": p.get("租金以外费用", "") or p.get("与出租相关的其他条件", ""),
            "税费口径": "未取得明确税费及签署合同证据，不设为0或擅自折净",
            "租期挂牌原文": p.get("租期", ""),
            "付款挂牌原文": p.get("租金支付要求", ""),
            "递增挂牌原文": p.get("租金调整方式", ""),
            "免租期挂牌原文": p.get("免租期", ""),
            "其他披露挂牌原文": p.get("其他披露事项", ""),
            "限制及纳入建议": item["限制及纳入建议"],
            "核验状态": "Codex同编号/公告期/字段辅助核对；未代成员人工签核",
            "提取方式": mode,
            "挂牌来源": item["挂牌URL"], "成交来源": item["成交URL"],
            "本轮动作": item["本轮动作"],
        }
        rows.append(row)
        extracted.append({"项目编号": pid, "挂牌字段": p, "成交字段": c, "提取方式": mode})
    assert len({r["观察ID"] for r in rows}) == len(rows)
    write_csv(batch / "苏州办公补采整理版_v2_7观察.csv", rows)
    (batch / "原文字段提取.json").write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf8")
    summary = {
        "截至日": index["截至日"], "本视图观察数": len(rows),
        "楼宇切分组数": len({r["楼宇切分组"] for r in rows}),
        "新增观察数": sum(r["本轮动作"] == "新增成交观察" for r in rows),
        "旧观察补证数": sum(r["本轮动作"] == "203室同编号挂牌补证" for r in rows),
        "新增且披露面积不小于500㎡": sum(r["本轮动作"] == "新增成交观察" and Decimal(r["披露面积㎡"]) >= 500 for r in rows),
        "面积最大值㎡": str(max(Decimal(r["披露面积㎡"]) for r in rows)),
        "同编号及公告期对应": True,
        "名义单价算术": "逐行由成交年租金÷12÷该编号挂牌面积重算",
        "训练或目标报价": "未执行；保留费用/用途/面积口径/年份分层",
    }
    (batch / "重建检查结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    build(Path(sys.argv[1]))
