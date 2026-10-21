import unittest

from app.evaluation import answer_contains_expected_facts, citations_are_valid, recall_at_k


class EvaluationMetricTests(unittest.TestCase):
    def test_recall_at_k(self):
        result = recall_at_k([[1, 2], [4]], [{2}, {3, 4}])
        self.assertEqual(result.evaluated, 2)
        self.assertEqual(result.recall_at_k, 0.75)

    def test_citation_validity(self):
        self.assertTrue(citations_are_valid([1, 3], 3))
        self.assertFalse(citations_are_valid([4], 3))

    def test_expected_facts(self):
        self.assertTrue(answer_contains_expected_facts("Pressure is 2.2 to 2.8 bar.", ["2.2", "2.8 bar"]))


if __name__ == "__main__":
    unittest.main()
