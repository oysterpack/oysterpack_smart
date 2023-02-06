import logging
import unittest

from algosdk.encoding import encode_address
from beaker import sandbox

from oysterpack.apps.auction_app.contracts.auction import Auction, AuctionStatus
from tests.algorand.test_support import AlgorandTestSupport


class AuctionTestCase(AlgorandTestSupport, unittest.TestCase):
    logger = logging.getLogger("AuctionTestCase")

    def test_create(self):
        # SETUP
        logger = super().get_logger("test_create")
        creator = sandbox.get_accounts().pop()
        seller = sandbox.get_accounts().pop()
        app_client = AlgorandTestSupport.sandbox_application_client(
            Auction(), sender=creator.address, signer=creator.signer
        )

        # ACT
        app_id, app_addr, create_txid = app_client.create(seller=seller.address)
        logger.info(
            f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}, seller.address={seller.address}"
        )

        # ASSERT
        app_state = app_client.get_application_state()
        logger.info(f"app_state: {app_state}")
        # seller address is stored as bytes in the contract
        # beaker's ApplicationClient will return the bytes as a hex encoded string
        seller_address = encode_address(bytes.fromhex(app_state["seller"]))
        self.assertEqual(seller.address, seller_address)
        self.assertEqual(app_state["status"], AuctionStatus.New.value)


if __name__ == "__main__":
    unittest.main()
