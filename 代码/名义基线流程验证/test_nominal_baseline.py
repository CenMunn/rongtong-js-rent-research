import copy
import unittest
from decimal import Decimal as D
from run_nominal_baseline import evaluate, predict_fold

class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id=str(i), building_group=g, _y=D(y), transaction_date=d)
            for i,g,y,d in [(1,'A','10','2026-07-01'),(2,'B','20','2026-08-01'),(3,'C','40','2026-11-01')]]
    def test_manual_arithmetic(self):
        folds, metrics = evaluate(self.rows)
        self.assertEqual([D(x['predicted_training_median']) for x in folds], [D(30),D(25),D(15)])
        self.assertEqual(D(metrics['MAE']), D(50)/3)
    def test_held_label_cannot_change_prediction(self):
        expected = predict_fold(self.rows, 'A')[2]
        altered = copy.deepcopy(self.rows)
        altered[0]['_y'] = D('99999')
        self.assertEqual(predict_fold(altered, 'A')[2], expected)
    def test_same_building_multiple_observations_stay_together(self):
        self.rows.append(dict(id='4', building_group='A', _y=D(100), transaction_date='2026-09-01'))
        train, test, pred = predict_fold(self.rows, 'A')
        self.assertEqual({x['id'] for x in test}, {'1','4'})
        self.assertEqual({x['building_group'] for x in train}, {'B','C'})
        self.assertEqual(pred, D(30))
    def test_date_limitation_is_visible(self):
        folds, metrics = evaluate(self.rows)
        self.assertEqual(metrics['folds_with_later_training_dates'], 2)
        self.assertFalse(folds[-1]['contains_later_training_record'])

if __name__ == '__main__': unittest.main()
