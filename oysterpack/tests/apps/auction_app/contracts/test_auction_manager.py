import unittest

from oysterpack.apps.auction_app.contracts.auction_manager import AuctionManager
from tests.algorand.test_support import AlgorandTestSupport


class AuctionFactoryTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_create(self):
        # SETUP
        logger = super().get_logger("test_create")
        app_client = self.sandbox_application_client(AuctionManager())
        app_client.build()

        # inner transaction fees need to be paid
        sp = app_client.client.suggested_params()
        sp.fee = sp.min_fee * 3
        sp.flat_fee = True

        # ACT
        app_id, app_addr, create_txid = app_client.create()

        app_account_info = app_client.get_application_account_info()
        logger.info(app_account_info)
        logger.info(f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}")


if __name__ == "__main__":
    unittest.main()
