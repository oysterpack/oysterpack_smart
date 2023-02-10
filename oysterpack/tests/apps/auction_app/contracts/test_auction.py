import unittest

from algosdk.encoding import encode_address
from beaker import sandbox
from beaker.client import LogicException
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

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

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

    def test_set_bid_asset(self):
        # SETUP
        logger = super().get_logger("test_set_bid_asset")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        app_id, app_addr, create_txid = creator_app_client.create(seller=seller.address)
        seller_app_client = creator_app_client.prepare(signer=seller.signer)
        logger.info(
            f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}, seller.address={seller.address}"
        )

        # auction must be pre-funded to pay for storage fees
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True

        # fund the auction to pay for storage
        seller_app_client.fund(int(0.2 * algo))

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000

        with self.subTest("only the seller can set the bid asset"):
            with self.assertRaises(LogicException):
                creator_app_client.call(
                    Auction.set_bid_asset,
                    bid_asset=bid_asset_id,
                    min_bid=min_bid,
                    suggested_params=sp,
                )

        with self.subTest("auction status is new and bid asset is not set"):
            sp = self.algod_client.suggested_params()
            sp.fee = sp.min_fee * 2
            sp.flat_fee = True
            seller_app_client.call(
                Auction.set_bid_asset,
                bid_asset=bid_asset_id,
                min_bid=min_bid,
                suggested_params=sp,
            )
            # ASSERT
            app_state = creator_app_client.get_application_state()
            logger.info(f"app_state: {app_state}")
            self.assertEqual(app_state["bid_asset_id"], bid_asset_id)
            self.assertEqual(app_state["min_bid"], min_bid)

            app_assets = seller_app_client.get_application_account_info()["assets"]
            self.assertEqual(len(app_assets), 1)
            print(app_assets)
            self.assertEqual(
                len(
                    [asset for asset in app_assets if asset["asset-id"] == bid_asset_id]
                ),
                1,
            )

        with self.subTest("setting the bid asset when it is already set should fail"):
            with self.assertRaises(LogicException):
                sp = self.algod_client.suggested_params()
                sp.fee = sp.min_fee * 2
                sp.flat_fee = True
                seller_app_client.call(
                    Auction.set_bid_asset,
                    bid_asset=bid_asset_id,
                    min_bid=min_bid,
                    suggested_params=sp,
                )

    def test_optout_asset(self):
        # SETUP
        logger = super().get_logger("test_set_bid_asset")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        app_id, app_addr, create_txid = creator_app_client.create(seller=seller.address)
        seller_app_client = creator_app_client.prepare(signer=seller.signer)
        logger.info(
            f"app_id={app_id}, app_addr={app_addr}, create_txid={create_txid}, seller.address={seller.address}"
        )

        # auction must be pre-funded to pay for storage fees
        sp = self.algod_client.suggested_params()
        sp.fee = sp.min_fee * 2
        sp.flat_fee = True

        # fund the auction to pay for storage
        seller_app_client.fund(int(0.2 * algo))

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000
        seller_app_client.call(
            Auction.set_bid_asset,
            bid_asset=bid_asset_id,
            min_bid=min_bid,
            suggested_params=sp,
        )

        # ACT
        seller_app_client.call(
            Auction.optout_asset, asset=bid_asset_id, suggested_params=sp
        )
        app_account_info = seller_app_client.get_application_account_info()
        self.assertEqual(len(app_account_info["assets"]), 0)


if __name__ == "__main__":
    unittest.main()
