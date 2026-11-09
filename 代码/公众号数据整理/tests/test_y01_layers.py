import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parents[1] / 'build_y01_layers.py'
spec = importlib.util.spec_from_file_location('y01_layers', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class LayerTests(unittest.TestCase):
    def test_explicit_province_and_broken_lines(self):
        self.assertEqual(m.classify('江 苏 省\n南京市玄武区')[0], '江苏')
        self.assertEqual(m.classify('安徽省合肥市巢湖市军分区路1号')[0], '省外')

    def test_city_and_county_city(self):
        self.assertEqual(m.classify('苏州市常熟市三峰管理区')[0], '江苏')
        self.assertEqual(m.classify('句容市玉清东路一幢01-05号')[0], '江苏')

    def test_region_only_is_not_address(self):
        self.assertEqual(m.classify('来源片区=苏北')[0], '归属待确认')
        self.assertEqual(m.classify('来源片区=安徽')[0], '归属待确认')

    def test_road_and_site_names_are_not_provinces(self):
        for address in ['北京西路39号', '吴江农场叶泽湖地块西区', '（临街主楼3-6层）']:
            self.assertEqual(m.classify(address)[0], '归属待确认')

    def test_conflicting_provinces_stay_pending(self):
        self.assertEqual(m.classify('江苏省南京市及安徽省合肥市')[0], '归属待确认')

    def test_full_partition_preserves_values_and_status_scope(self):
        with tempfile.TemporaryDirectory() as d:
            summary = m.build(Path(d) / 'new')
            self.assertEqual(summary['省域分层'], {'江苏': 937, '省外': 136, '归属待确认': 84})
            self.assertEqual(summary['复核状态'], {
                '成员已签核（限定字段）': 10, '助手抽核，待成员确认': 16,
                '机器候选，待成员复核': 10, '本轮未登记逐条复核': 1121})
            src = m.read(m.SOURCE)
            merged = []
            for filename in m.PART_FILES.values():
                merged.extend(m.read(Path(d) / 'new' / filename))
            self.assertEqual({r['observation_id']: r for r in src},
                             {r['observation_id']: r for r in merged})
            index = {r['观察ID']: r for r in m.read(Path(d) / 'new' / '逐条省域与核验状态索引.csv')}
            self.assertEqual(index['WX-20261108-001089']['省域层'], '归属待确认')
            self.assertIn('成员已签核', index['WX-20261108-000136']['本轮复核状态'])
            self.assertIn('正式采用值未定', index['WX-20261108-000136']['仍待核事项'])
            self.assertIn('未登记', index['WX-20261108-000003']['本轮复核状态'])
            self.assertEqual(len(m.read(Path(d) / 'new' / '两项未定差异.csv')), 2)
            with self.assertRaises(FileExistsError):
                m.build(Path(d) / 'new')


if __name__ == '__main__':
    unittest.main()
