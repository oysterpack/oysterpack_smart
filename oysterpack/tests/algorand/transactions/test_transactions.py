import unittest

from algosdk.constants import MIN_TXN_FEE

from oysterpack.algorand.transactions import GetSuggestedParamsFactory, suggested_params_with_min_flat_flee
from tests.algorand.test_support import AlgorandTestSupport


class TransactionsTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_suggested_params_with_min_flat_flee(self):
        params = suggested_params_with_min_flat_flee(self.algod_client)
        self.assertTrue(params.flat_fee)
        self.assertEqual(params.fee, MIN_TXN_FEE)
        self.assertEqual(params.min_fee, MIN_TXN_FEE)


class GetSuggestedParamsFactoryTest(AlgorandTestSupport, unittest.TestCase):

    def test_create_with_min_flat_fee(self):
        get_suggested_params = GetSuggestedParamsFactory.create_with_min_flat_fee(self.algod_client)
        params = get_suggested_params()
        self.assertTrue(params.flat_fee)
        self.assertEqual(params.fee, MIN_TXN_FEE)
        self.assertEqual(params.min_fee, MIN_TXN_FEE)


if __name__ == '__main__':
    unittest.main()
