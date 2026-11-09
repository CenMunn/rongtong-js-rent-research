"""合成数据仅供程序边界测试，不属于真实租金数据集。"""
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'check_data.py'
spec = importlib.util.spec_from_file_location('check_data', MODULE)
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)


class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with (qc.ROOT/'共享资料/统一采集空表.csv').open(encoding='utf-8-sig') as f:
            self.fields = next(csv.reader(f))

    def row(self, **changes):
        r = dict.fromkeys(self.fields, '')
        r.update(asset_id='TEST-ASSET', observation_id='TEST-01', lessor_entity='合成测试主体',
                 address_scope_floor='合成测试地址', area_building_chargeable_land='披露面积=5660㎡',
                 price_type='合同价', raw_price_unit='181120元/月',
                 monthly_normalized='32元/披露㎡/月；公式=181120元/月÷5660㎡',
                 collection_date='2026-11-09', publish_sign_start_end_dates='起租日期=2021-05-12',
                 source_url_page='https://example.org/test', verification_status='合成测试；字段已核')
        r.update(changes)
        return r

    def run_rows(self, rows, fields=None):
        path = self.root/'input.csv'
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields or self.fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
        result=qc.check(path,qc.ROOT/'共享资料/统一采集空表.csv',self.root/'out')
        with (self.root/'out/问题明细.csv').open(encoding='utf-8-sig') as f:
            issues=list(csv.DictReader(f))
        return result, issues

    def test_month_total(self):
        _, issues=self.run_rows([self.row()]);self.assertEqual(issues, [])

    def test_disclosed_rent_and_adjusted_rent_types(self):
        _,issues=self.run_rows([self.row(price_type='法律文件披露租赁价'),self.row(observation_id='TEST-02',price_type='上市公司披露调租价')])
        self.assertFalse(any(x['规则']=='P01' for x in issues))

    def test_annual_total(self):
        _, issues=self.run_rows([self.row(raw_price_unit='68000元/年',area_building_chargeable_land='披露面积=61.69㎡',monthly_normalized='91.8571元/披露㎡/月；公式=68000元/年÷12÷61.69㎡')]);self.assertEqual(issues, [])

    def test_direct_unit_without_area(self):
        _, issues=self.run_rows([self.row(raw_price_unit='18.5元/㎡月',area_building_chargeable_land='',monthly_normalized='18.5元/㎡/月；原文直录=18.5元/㎡/月',missing_reason='面积未披露')]);self.assertFalse(any(x['规则'] in ['U01','U02','R01'] for x in issues))

    def test_wrong_source_numerator(self):
        _, issues=self.run_rows([self.row(monthly_normalized='176.678445元/披露㎡/月；公式=12000000元/年÷12÷5660㎡')]);self.assertTrue(any(x['规则']=='U02' for x in issues))

    def test_wrong_area(self):
        _, issues=self.run_rows([self.row(monthly_normalized='181.12元/披露㎡/月；公式=181120元/月÷1000㎡')]);self.assertTrue(any(x['规则']=='U02' for x in issues))

    def test_wrong_arithmetic(self):
        _, issues=self.run_rows([self.row(monthly_normalized='33元/披露㎡/月；公式=181120元/月÷5660㎡')]);self.assertTrue(any(x['规则']=='U01' for x in issues))

    def test_missing_column_is_file_error(self):
        result,_=self.run_rows([self.row()], [x for x in self.fields if x!='industrial_specs']);self.assertGreater(result.get('file_errors',0),0)

    def test_multiple_periods_preserved(self):
        result,issues=self.run_rows([self.row(),self.row(observation_id='TEST-02')]);self.assertEqual(result['rows'],2);self.assertFalse(any(x['规则']=='I02' for x in issues))

    def test_duplicate_observations(self):
        _,issues=self.run_rows([self.row(),self.row()]);self.assertTrue(any(x['规则']=='I02' for x in issues))

    def test_no_price_and_zero_building(self):
        _,issues=self.run_rows([self.row(price_type='无明确价格',raw_price_unit='',monthly_normalized='',area_building_chargeable_land='建筑面积=0㎡；土地面积=100㎡')]);self.assertFalse(any(x['级别']=='错误' or x['规则']=='P02' for x in issues))

    def test_zero_denominator(self):
        _,issues=self.run_rows([self.row(area_building_chargeable_land='披露面积=0㎡',monthly_normalized='32元/披露㎡/月；公式=181120元/月÷0㎡')]);self.assertTrue(any(x['规则']=='U01' for x in issues))

    def test_deposit_cannot_be_rent(self):
        _,issues=self.run_rows([self.row(raw_price_unit='保证金181120元/月')]);self.assertTrue(any(x['规则'] in ['P02','U02'] for x in issues))

    def test_room_price_is_not_area_price(self):
        _,issues=self.run_rows([self.row(raw_price_unit='1750元/间/月',monthly_normalized='1750元/㎡/月；原文直录=1750元/㎡/月')]);self.assertTrue(any(x['规则']=='U02' for x in issues))

    def test_filled_reviews_protected(self):
        self.run_rows([self.row(verification_status='待核')])
        path=self.root/'out/人工复核清单.csv'
        with path.open(encoding='utf-8-sig') as f:r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
        rows[0]['核对结论']='合成复核意见，必须保留'
        with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
        before={p.name:p.read_bytes() for p in path.parent.iterdir()}
        with self.assertRaises(ValueError):qc.check(self.root/'input.csv',qc.ROOT/'共享资料/统一采集空表.csv',self.root/'out')
        self.assertEqual(before,{p.name:p.read_bytes() for p in path.parent.iterdir()})


if __name__=='__main__':unittest.main()
