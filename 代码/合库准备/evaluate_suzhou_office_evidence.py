"""对固定公告缓存做定向补证；不扩张既有主组，不修改历史输入。

python 代码/合库准备/evaluate_suzhou_office_evidence.py <本批目录>
输入：补证索引.json、原件/；复用已有HTML/内嵌JSON解析器。
"""
import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from build_suzhou_office_followup import listing, result, date_iso


def write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(batch):
    index = json.loads((batch / "补证索引.json").read_text(encoding="utf8"))
    rows, evidence = [], []
    for item in index["四条成交"]:
        p, mode = listing(batch / item["挂牌文件"])
        pid = p["项目编号"]
        assert pid == item["项目编号"]
        c = result(batch / item["成交文件"], pid)
        assert c["成交日"].startswith("2026-") and c["成交日"] <= "2026-11-12"
        a, v = Decimal(p["出租面积(m²)"]), Decimal(c["年租金"])
        assert a >= 500 and v > 0
        dates = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", c["公告期限"])
        start, end = [date_iso(d) for d in dates]
        assert start == date_iso(p["挂牌起始日"])
        end_match = end == date_iso(p["挂牌终止日"])
        rows.append({
            "观察ID": "SZ-OFF-" + pid, "项目编号": pid, "楼宇或组合切分组": item["切分组"],
            "项目名称": p["项目名称"], "披露面积㎡": str(a),
            "面积类型": "未明确，不以通用现状条款确认建筑面积或实际计租面积",
            "公示成交元每年": str(v), "名义元每披露㎡月": f"{v / 12 / a:.6f}",
            "名义标签限制": item["名义标签限制"], "成交日": c["成交日"],
            "用途原文": p.get("使用用途及要求", ""), "费用原文": p.get("租金以外费用", ""),
            "物业费口径": item["物业费口径"], "税费口径": "未取得明确含税/不含税证据",
            "免租期原文": p.get("免租期", ""), "其他披露原文": p.get("其他披露事项", ""),
            "挂牌起止": p["挂牌起始日"] + "—" + p["挂牌终止日"],
            "成交公示公告期": c["公告期限"],
            "公告期限核对": "起止一致" if end_match else "起日一致、截止日不同；延期/变更直接证据未取得",
            "处理决定": "条件背景；不进入主流程", "不能纳入的原因": item["不能纳入的原因"],
            "挂牌来源": item["挂牌URL"], "成交来源": item["成交URL"],
            "核验范围": "同编号/标题范围/原价面积辅助核对；未代成员人工签核",
        })
        evidence.append({"项目编号": pid, "挂牌字段": p, "成交字段": c, "提取方式": mode})
    write(batch / "2026大面积办公相关成交_4条件观察.csv", rows)
    checks = []
    for item in index["原主组"]:
        p, _ = listing(batch / item["挂牌文件"])
        assert p["项目编号"] == item["项目编号"]
        phrase = p.get("与出租相关的其他条件", "")
        if item["项目编号"] == "SCJRZ20260793":
            assert "出租标的使用面积以现状为准" in phrase
            area_result = "新增使用面积措辞提示；498㎡与计租使用面积的直接等同关系仍未确认"
            excerpt = "出租标的使用面积以现状为准"
        else:
            assert "建筑面积、使用面积以现状为准" in phrase
            area_result = "仍未确认103㎡是建筑、使用还是合同计租面积；通用免责措辞不能选定分母类型"
            excerpt = "出租标的建筑面积、使用面积以现状为准"
        all_fields = " ".join(p.values())
        tax_hits = re.findall(r"含税|不含税|税率|税费|发票", all_fields)
        checks.append({
            "原观察ID": item["观察ID"], "项目编号": item["项目编号"],
            "披露面积㎡保持": p["出租面积(m²)"], "面积原文片段": excerpt,
            "本轮面积结论": area_result, "税费关键字命中": "；".join(tax_hits),
            "本轮税费结论": "原件未见税费明示；详情应用入口403，合同/拍卖告知书未取得；未知保留",
            "费用已知原文": p.get("租金以外费用", "") + "；" + p.get("其他披露事项", ""),
            "变更决定": "保留原价和原面积；只增补证据提示，不升级为正式统一口径样本",
            "来源": item["挂牌URL"], "证据位置": item["挂牌文件"],
        })
    write(batch / "主组两条面积与税费补证.csv", checks)
    (batch / "四条成交原文字段.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf8")
    summary = {"截至日": "2026-11-12", "本批条件成交观察": len(rows), "已配对项目编号数": len({r["项目编号"] for r in rows}),
               "满足本轮全部优先条件的新增数": 0, "主组两条补证数": len(checks),
               "主组税费已补清数": 0, "主组面积类型已最终确认数": 0,
               "城市生活广场新增证据提示": "使用面积以现状为准；不等同498㎡已确证合同使用面积",
               "公告截止日不一致需补变更的数量": sum("不同" in r["公告期限核对"] for r in rows),
               "训练或报价": "未执行", "主表或既有分层输入": "未覆盖"}
    (batch / "本批检查结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    build(Path(sys.argv[1]))
