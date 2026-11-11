import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('merge', Path(__file__).resolve().parents[1] / 'build_merge_candidates.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PolicyBoundaryTests(unittest.TestCase):
    def test_price_natures_do_not_promote_floor_or_no_price(self):
        self.assertEqual(m.price_kind('招租底价（江苏公司自有报价资料）'), 'RESERVE_PRICE')
        self.assertEqual(m.price_kind('无明确价格的项目或OCR线索'), 'NO_PRICE')
        self.assertEqual(m.price_kind('成交公示年租金'), 'PUBLISHED_TRANSACTION')
        self.assertEqual(m.price_kind('法律文件披露关联方租赁价'), 'RELATED_CONTRACT')

    def test_namespaces_preserve_colliding_original_ids(self):
        self.assertNotEqual(m.row_uid('B01', 'O01'), m.row_uid('X03', 'O01'))

    def test_different_wechat_articles_stay_different(self):
        a = 'https://mp.weixin.qq.com/s?__biz=A&mid=1&idx=1&sn=x&scene=126#rd'
        b = 'https://mp.weixin.qq.com/s?__biz=A&mid=2&idx=1&sn=x'
        self.assertNotEqual(m.canonical_url(a), m.canonical_url(b))
        self.assertEqual(m.canonical_url(a), m.canonical_url(a.replace('scene=126', 'scene=2')))

    def test_deposit_is_not_a_rent(self):
        self.assertEqual(m.numeric_price('竞价保证金=50000元/年')[0], '')

    def test_conflicting_annual_values_not_selected(self):
        self.assertEqual(m.numeric_price('4406127元/年\n440.61万元/年')[0], '')

    def test_room_price_never_becomes_sqm_price(self):
        self.assertEqual(m.numeric_price('1750元/间/月')[0], '')

    def test_annual_and_monthly_totals_remain_distinct(self):
        self.assertEqual(m.numeric_price('50万元/年')[:2], ('500000', '元/年'))
        self.assertEqual(m.numeric_price('181120元/月')[:2], ('181120', '元/月'))


if __name__ == '__main__':
    unittest.main()
