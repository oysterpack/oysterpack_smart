import unittest

from algosdk.error import AlgodHTTPError
from beaker import sandbox

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction_app.client.auction_manager_client import (
    AuctionManagerClient,
    create_auction_manager,
)
from oysterpack.apps.auction_app.contracts.auction import auction_storage_fees
from oysterpack.apps.auction_app.contracts.auction_manager import AuctionManager
from oysterpack.apps.auction_app.contracts.auction_status import AuctionStatus
from tests.algorand.test_support import AlgorandTestSupport


class AuctionManagerTestCase(AlgorandTestSupport, unittest.TestCase):
    def test_create(self):
        logger = super().get_logger("test_create")
        # SETUP
        app_client = self.sandbox_application_client(AuctionManager())
        app_client.build()

        # ACT
        app_client.create()
        auction_manager_client = AuctionManagerClient(app_client)
        logger.info(
            f"auction creation fees = {auction_manager_client.get_auction_creation_fees()} microalgos"
        )

    def test_create_auction(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = creator_app_client.prepare(signer=seller.signer)

        # ACT
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)

        # create another auction
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)

    def test_delete_finalized_auction(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = auction_manager_client.prepare(signer=seller.signer)

        # ACT
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)

        # create another auction
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller_address)

        with self.subTest(
            "trying to delete an Auction that is not finalized should fail"
        ):
            with self.assertRaises(AssertionError) as err:
                auction_manager_client.delete_finalized_auction(
                    seller_auction_client.app_id
                )
            self.assertEqual("auction is not finalized", str(err.exception))

        with self.subTest("delete finalized Auction"):
            gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
            starting_asset_balance = 1_000_000
            self._optin_asset_and_seed_balance(
                receiver=Address(seller.address),
                asset_id=gold_asset_id,
                amount=starting_asset_balance,
                asset_reserve_address=gold_asset_manager_address,
            )
            seller_auction_client.set_bid_asset(gold_asset_id, 10_000)

            seller_auction_client.cancel()
            seller_auction_client.finalize()
            auction_state = seller_auction_client.get_auction_state()
            self.assertEqual(auction_state.status, AuctionStatus.FINALIZED)

            account_manager_algo_balance_1 = self.algod_client.account_info(
                auction_manager_client.contract_address
            )["amount"]
            auction_algo_balance = seller_auction_client.get_application_account_info()[
                "amount"
            ]
            # ACT
            auction_manager_client.delete_finalized_auction(
                seller_auction_client.app_id
            )

            # ASSERT auction has been deleted
            with self.assertRaises(AlgodHTTPError) as err:
                seller_auction_client.get_application_state()
            self.assertEqual(err.exception.code, 404)
            self.assertEqual("application does not exist", str(err.exception))

            # ASSERT that the Auction ALGO account was closed out to the AuctionManager
            account_manager_algo_balance_2 = (
                auction_manager_client.get_application_account_info()["amount"]
            )
            expected_balance = account_manager_algo_balance_1 + auction_algo_balance
            self.assertGreater(
                account_manager_algo_balance_2, account_manager_algo_balance_1
            )
            self.assertEqual(expected_balance, account_manager_algo_balance_2)

            treasury_balance = auction_manager_client.get_treasury_balance()
            self.assertEqual(
                auction_algo_balance + auction_storage_fees(), treasury_balance
            )

            auction_manager_client.withdraw()
            app_account_info = auction_manager_client.get_application_account_info()
            self.assertEqual(
                app_account_info["amount"], app_account_info["min-balance"]
            )


if __name__ == "__main__":
    unittest.main()
