"""用既有真实底表验证副本与溯源关系，结果仅写入临时目录。"""
import csv
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('reviewed',Path(__file__).resolve().parents[1]/'build_reviewed.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f);return r.fieldnames,list(r)

class ReviewedCopy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name)/'version'
        self.source=module.ROOT/'共享资料/公众号采集结果.csv'
        self.evidence=module.ROOT/'成员成果/王玮/Y01/Y01_七项建议核实记录.csv'
        self.index=module.ROOT/'成员成果/王玮/Y01/Y01_证据索引.csv'
        self.before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        module.build(self.source,self.evidence,self.index,self.out)
        self.original_fields,self.original=read(self.source)
        self.fields,self.rows=read(self.out/'公众号采集结果_整理版_v1.csv')

    def test_structure_and_ids_preserved(self):
        self.assertEqual(self.original_fields,self.fields);self.assertEqual(len(self.rows),1157)
        for a,b in zip(self.original,self.rows):
            self.assertEqual(a['observation_id'],b['observation_id']);self.assertEqual(a['asset_id'],b['asset_id'])

    def test_supported_corrections(self):
        self.assertIn('北京东路44号-2',self.rows[85]['address_scope_floor'])
        self.assertIn('图表复核分项底价=272.95万元/年',self.rows[85]['raw_price_unit'])
        self.assertIn('建筑或房屋面积=5976.03㎡',self.rows[126]['area_building_chargeable_land'])
        self.assertIn('建筑或房屋面积=11181.97㎡',self.rows[390]['area_building_chargeable_land'])
        self.assertIn('土地或场地面积=13279.31㎡',self.rows[390]['area_building_chargeable_land'])
        self.assertIn('8.446633元/建筑㎡/月',self.rows[390]['monthly_normalized'])

    def test_amount_discrepancy_is_not_silently_chosen(self):
        r=self.rows[126];self.assertIn('4406127元/年',r['raw_price_unit']);self.assertIn('440.61万',r['raw_price_unit'])
        self.assertIn('27元',r['raw_price_unit']);self.assertEqual(r['monthly_normalized'],'')
        self.assertIn('正式采用值待核',r['verification_status'])

    def test_land_conflict_has_no_adopted_value(self):
        r=self.rows[509];self.assertIn('土地或场地面积=待核',r['area_building_chargeable_land'])
        self.assertIn('原图土地面积=68170.28㎡',r['area_building_chargeable_land'])
        self.assertIn('正文土地面积=69170.28㎡',r['area_building_chargeable_land'])
        self.assertEqual(r['raw_price_unit'],'');self.assertEqual(r['monthly_normalized'],'')

    def test_only_four_observations_changed(self):
        changed=[i+1 for i,(a,b) in enumerate(zip(self.original,self.rows)) if a!=b]
        self.assertEqual(changed,[86,127,391,510])

    def test_every_changed_cell_has_before_after_evidence(self):
        _,log=read(self.out/'逐字段修改日志.csv')
        actual={(r['observation_id'],r['字段']):(r['原值'],r['整理值']) for r in log}
        expected={(a['observation_id'],k):(a[k],b[k]) for a,b in zip(self.original,self.rows) for k in self.fields if a[k]!=b[k]}
        self.assertEqual(actual,expected)
        self.assertTrue(all(r['核实记录定位'] and r['证据'] for r in log))
        self.assertEqual(sum(r['变更类别']=='原图支持的修订' for r in log),5)
        self.assertEqual(sum(r['变更类别']=='差异标注' for r in log),2)

    def test_source_unchanged_and_version_not_overwritten(self):
        self.assertEqual(self.before,hashlib.sha256(self.source.read_bytes()).hexdigest())
        before={p.name:p.read_bytes() for p in self.out.iterdir() if p.is_file()}
        with self.assertRaises(FileExistsError):module.build(self.source,self.evidence,self.index,self.out)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.out.iterdir() if p.is_file()})

if __name__=='__main__':unittest.main()
