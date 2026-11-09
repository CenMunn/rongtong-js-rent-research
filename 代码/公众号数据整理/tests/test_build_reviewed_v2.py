"""2026-11-10补回：原文件误存CSV索引，现验证真实v2的范围及日志。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('reviewed_v2', Path(__file__).resolve().parents[1] / 'build_reviewed_v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReviewedV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out = Path(cls.temp.name) / 'v2'
        cls.y01 = m.ROOT / '成员成果/王玮/Y01'
        cls.paths = [m.ROOT / '共享资料/公众号采集结果.csv',
                     cls.y01 / '公众号整理版_v1/公众号采集结果_整理版_v1.csv',
                     cls.y01 / '公众号整理版_v2/公众号采集结果_整理版_v2.csv']
        cls.before = [m.sha(p) for p in cls.paths]
        cls.result = m.build(cls.out)
        cls.fields, cls.rows = m.read(cls.out / '公众号采集结果_整理版_v2.csv')
        _, cls.parent = m.read(cls.paths[1])

    def test_reproduction_matches_published_values(self):
        fields, published = m.read(self.paths[2])
        self.assertEqual((self.fields, self.rows), (fields, published))
        self.assertEqual((len(self.rows), len(self.fields)), (1157, 28))

    def test_only_signed_ten_observations_changed(self):
        changed = [i for i, (a, b) in enumerate(zip(self.parent, self.rows), 1) if a != b]
        self.assertEqual(changed, [87, 131, 136, 137, 148, 149, 181, 191, 206, 208])
        for a, b in zip(self.parent, self.rows):
            self.assertEqual((a['asset_id'], a['observation_id']), (b['asset_id'], b['observation_id']))

    def test_log_matches_every_changed_field(self):
        _, log = m.read(self.out / '本批修改日志.csv')
        actual = {(a['observation_id'], k): (a[k], b[k])
                  for a, b in zip(self.parent, self.rows) for k in self.fields if a[k] != b[k]}
        self.assertEqual(actual, {(r['observation_id'], r['字段']): (r['原值'], r['整理值']) for r in log})
        self.assertEqual(len(log), 58)

    def test_cumulative_log_replays_from_raw(self):
        _, raw = m.read(self.paths[0])
        data = {r['observation_id']: dict(r) for r in raw}
        _, log = m.read(self.out / '逐字段修改日志.csv')
        self.assertEqual(len(log), 81)
        for r in log:
            self.assertEqual(data[r['observation_id']][r['字段']], r['原值'])
            data[r['observation_id']][r['字段']] = r['整理值']
        self.assertEqual(list(data.values()), self.rows)

    def test_two_disputes_and_history_retained(self):
        self.assertIn('5976.03㎡', self.rows[135]['area_building_chargeable_land'])
        for i in [126, 135]:
            self.assertEqual(self.rows[i]['monthly_normalized'], '')
            self.assertIn('4406127', self.rows[i]['raw_price_unit'])
            self.assertIn('440.61万', self.rows[i]['raw_price_unit'])
        self.assertIn('土地或场地面积=待核', self.rows[509]['area_building_chargeable_land'])
        _, issues = m.read(self.out / '未定差异清单.csv')
        self.assertEqual([r['问题ID'] for r in issues], ['D01', 'D02'])

    def test_signoff_scope_does_not_expand(self):
        _, signoffs = m.read(self.out / '本批成员签核登记.csv')
        self.assertEqual(len(signoffs), 10)
        self.assertTrue(all(r['签核人'] == '王玮' and r['范围'] for r in signoffs))
        self.assertEqual(self.rows[391], self.parent[391])
        self.assertEqual(self.rows[1088], self.parent[1088])

    def test_source_hashes_unchanged_and_overwrite_rejected(self):
        self.assertEqual(self.before, [m.sha(p) for p in self.paths])
        before = {p.name: m.sha(p) for p in self.out.iterdir()}
        with self.assertRaises(FileExistsError):
            m.build(self.out)
        self.assertEqual(before, {p.name: m.sha(p) for p in self.out.iterdir()})


if __name__ == '__main__':
    unittest.main()
