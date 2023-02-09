import unittest

from algosdk.encoding import encode_address
from beaker import sandbox
from beaker.consts import algo

from oysterpack.apps.auction_app.contracts.auction import (
    Auction,
    AuctionStatus,
)
from tests.algorand.test_support import AlgorandTestSupport


class AuctionTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_create(self):
        # SETUP
        logger = super().get_logger("test_create")
        creator = sandbox.get_accounts().pop()
        seller = sandbox.get_accounts().pop()

        app_client = self.sandbox_application_client(Auction(), signer=creator.signer)

        # ACT
        app_id, app_addr, create_txid = app_client.create(seller=seller.address)
        app_account_info = app_client.get_application_account_info()
        logger.info(app_account_info)
        logger.info(
            f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}, seller.address={seller.address}"
        )

        # ASSERT
        app_state = app_client.get_application_state()
        logger.info(f"app_state: {app_state}")
        # seller address is stored as bytes in the contract
        # beaker's ApplicationClient will return the bytes as a hex encoded string
        seller_address = encode_address(bytes.fromhex(app_state["seller_address"]))
        self.assertEqual(seller.address, seller_address)
        self.assertEqual(app_state["status"], AuctionStatus.New.value)

    def test_initialize(self):
        # SETUP
        logger = super().get_logger("test_initialize")
        creator = sandbox.get_accounts().pop()
        seller = sandbox.get_accounts().pop()

        app_client = self.sandbox_application_client(Auction(), signer=creator.signer)
        app_id, app_addr, create_txid = app_client.create(seller=seller.address)
        logger.info(
            f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}, seller.address={seller.address}"
        )

        # auction must be pre-funded to pay for storage fees
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True
        app_client.fund(int(0.2 * algo))
        app_client.call(Auction.initialize, suggested_params=sp)

        app_state = app_client.get_application_state()
        logger.info(f"app_state: {app_state}")
        self.assertNotEqual(app_state["bid_escrow_app_id"], 0)

        # initializing the auction again should be ok while status=AuctionStatus.New
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True
        app_client.call(Auction.initialize, suggested_params=sp)
        self.assertEqual(
            app_state["bid_escrow_app_id"],
            app_client.get_application_state()["bid_escrow_app_id"],
        )


if __name__ == "__main__":
    unittest.main()
