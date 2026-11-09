import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wechat_cells import numeric_cell_text,uncovered_strips,repair_numeric_cell
import numpy as np

class NumericCells(unittest.TestCase):
    def sample(self):
        im=np.full((100,60,3),255,np.uint8);im[20:30,15:40]=0;im[40:43,24:31]=0;im[46:48,24:31]=0
        return im,[[[[14,19],[41,19],[41,31],[14,31]],'5976.0',.99]]
    def test_reflow_suffix(self):
        im,tokens=self.sample();extra,audit=repair_numeric_cell(im,(0,0,60,100),tokens,lambda x:([('5976.0 3',.9)],0))
        self.assertEqual(extra[0][1],'3');self.assertEqual(audit['候选值'],'5976.03')
    def test_reflow_low_confidence_not_accepted(self):
        im,tokens=self.sample();extra,audit=repair_numeric_cell(im,(0,0,60,100),tokens,lambda x:([('5976.0 3',.5)],0));self.assertEqual(extra,[])
    def test_reflow_cannot_rewrite_prefix(self):
        im,tokens=self.sample();extra,audit=repair_numeric_cell(im,(0,0,60,100),tokens,lambda x:([('5978.03',.99)],0));self.assertEqual(extra,[])
    def test_decimal_tail(self):self.assertEqual(numeric_cell_text('5976.0\n3'),'5976.03')
    def test_integer_tail(self):self.assertEqual(numeric_cell_text('4406\n127'),'4406127')
    def test_two_decimals(self):self.assertEqual(numeric_cell_text('73.56\n11.43'),'73.56\n11.43')
    def test_periods(self):self.assertEqual(numeric_cell_text('首年100\n次年200'),'首年100\n次年200')
    def test_range(self):self.assertEqual(numeric_cell_text('100-200\n3'),'100-200\n3')
    def test_uncovered_digit_in_nonempty_cell(self):
        im=np.full((100,60,3),255,np.uint8);im[20:30,15:40]=0;im[40:50,24:31]=0
        token=[[[14,19],[41,19],[41,31],[14,31]],'5976.0',.99]
        strips=uncovered_strips(im,(0,0,60,100),[token]);self.assertEqual(len(strips),1);self.assertGreater(strips[0][1][0][1],30)
    def test_no_cross_cell_digit(self):
        im=np.full((100,120,3),255,np.uint8);im[40:50,85:94]=0
        self.assertEqual(uncovered_strips(im,(0,0,60,100),[]),[])
    def test_small_tail_digit_with_internal_gap(self):
        im=np.full((100,60,3),255,np.uint8);im[40:43,24:31]=0;im[46:48,24:31]=0
        self.assertEqual(len(uncovered_strips(im,(0,0,60,100),[])),1)

if __name__=='__main__':unittest.main()
