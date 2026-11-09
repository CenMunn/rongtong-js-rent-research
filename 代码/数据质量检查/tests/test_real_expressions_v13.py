"""真实表达形式的合成回归用例，不计入真实数据；继承原15项边界测试。"""
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=module('checks_base',HERE.with_name('test_check_data.py'))
base.qc=module('qc13',HERE.parents[1]/'check_data_v1_3.py')

class RealExpressions(base.Checks):
    def simple(self,**kw):
        values=dict(raw_price_unit='361,800.00 元/年',area_building_chargeable_land='210.90㎡，公告租赁面积约',monthly_normalized='142.96')
        values.update(kw)
        return self.row(**values)

    def test_bare_monthly(self):
        r,issues=self.run_rows([self.simple()]);self.assertEqual(r['normalized_checked'],1);self.assertFalse(any(x['规则'] in ['U01','U02'] for x in issues))

    def test_b01_unit_suffix(self):
        r,issues=self.run_rows([self.simple(area_building_chargeable_land='公告租赁面积约210.90平方米；实际计租、建筑及土地面积未分别确认',monthly_normalized='142.9587元/平方米/月（公告范围名义分摊）')]);self.assertEqual(r['normalized_checked'],1);self.assertFalse(any(x['规则']=='U02' for x in issues))

    def test_wan_year(self):
        r,issues=self.run_rows([self.simple(raw_price_unit='49.056 万元/年',area_building_chargeable_land='280㎡，公告租赁面积',monthly_normalized='146.00')]);self.assertEqual(r['normalized_checked'],1);self.assertFalse(any(x['规则'] in ['U01','U02'] for x in issues))

    def test_simple_wrong_amount(self):
        _,i=self.run_rows([self.simple(monthly_normalized='143.96')]);self.assertTrue(any(x['规则']=='U01' for x in i))

    def test_multiple_areas_not_guessed(self):
        r,i=self.run_rows([self.simple(area_building_chargeable_land='建筑面积210.90㎡；土地面积500㎡')]);self.assertEqual(r['normalized_checked'],0);self.assertTrue(any(x['规则']=='U02' for x in i))

    def test_land_only_not_used(self):
        r,i=self.run_rows([self.simple(area_building_chargeable_land='土地面积210.90㎡')]);self.assertEqual(r['normalized_checked'],0)

    def test_range_denominator_not_guessed(self):
        r,i=self.run_rows([self.simple(area_building_chargeable_land='披露面积=210.90㎡至300㎡')]);self.assertEqual(r['normalized_checked'],0)

    def test_conflicting_prices_not_guessed(self):
        r,i=self.run_rows([self.simple(raw_price_unit='361800元/年；400000元/年')]);self.assertEqual(r['normalized_checked'],0)

    def test_blank_stays_blank(self):
        r,i=self.run_rows([self.simple(monthly_normalized='',area_building_chargeable_land='公告租赁面积约6300㎡，地下500㎡包含关系待核')]);self.assertEqual(r['normalized_checked'],0);self.assertTrue(any(x['规则']=='U03' for x in i))

    def test_pending_named_reviewer(self):
        _,i=self.run_rows([self.row(verification_status='原始来源已取得；待游依宸独立复核')]);self.assertTrue(any(x['规则']=='V01' for x in i))

    def test_pending_classmate(self):
        _,i=self.run_rows([self.row(verification_status='挂牌及成交原文已核，待同学复核')]);self.assertTrue(any(x['规则']=='V01' for x in i))

    def test_not_yet_signed_off(self):
        _,i=self.run_rows([self.row(verification_status='尚未完成成员复核')]);self.assertTrue(any(x['规则']=='V01' for x in i))
