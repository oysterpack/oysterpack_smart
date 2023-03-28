import unittest

from algosdk.error import AlgodHTTPError
from beaker.client import LogicException

from oysterpack.algorand.client.model import Address
from oysterpack.apps.auction.client.auction_manager_client import (
    AuctionManagerClient,
    create_auction_manager,
)
from oysterpack.apps.auction.contracts import auction_manager
from oysterpack.apps.auction.contracts.auction import auction_storage_fees
from oysterpack.apps.auction.contracts.auction_status import AuctionStatus
from tests.algorand.test_support import AlgorandTestCase


class AuctionManagerTestCase(AlgorandTestCase):
    def test_create(self):
        logger = super().get_logger("test_create")
        # SETUP
        app_client = self.sandbox_application_client(auction_manager.app)

        # ACT
        app_client.create()
        auction_manager_client = AuctionManagerClient(app_client)
        logger.info(
            f"auction creation fees = {auction_manager_client.get_auction_creation_fees()} microalgos"
        )

        self.assertEqual(
            app_client.call(auction_manager.app_name).return_value,
            auction_manager.APP_NAME,
        )

        with self.subTest("AuctionManager cannot be updated"):
            with self.assertRaises(LogicException):
                app_client.update()

        with self.subTest("AuctionManager cannot be deleted"):
            with self.assertRaises(LogicException):
                app_client.delete()

    def test_create_auction(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = creator_app_client.copy(signer=seller.signer)

        # ACT
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller)

        # create another auction
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller)

    def test_delete_finalized_auction(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = auction_manager_client.copy(signer=seller.signer)

        # ACT
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller)

        # create another auction
        seller_auction_client = seller_app_client.create_auction()
        auction_state = seller_auction_client.get_auction_state()
        self.assertEqual(seller.address, auction_state.seller)

        with self.subTest(
            "trying to delete an Auction that is not finalized should fail"
        ):
            with self.assertRaises(AssertionError) as err:
                auction_manager_client.delete_finalized_auction(
                    seller_auction_client.app_id
                )
            self.assertEqual("auction is not finalized", str(err.exception))

        with self.subTest("delete finalized Auction"):
            # setting the bid asset requires the seller to deposit ALGO in the auction contract to
            # cover asset opt-in storage fees. Account storage fees will not be refunded.
            # When the finalized auction is deleted, the Auction ALGO account is closed out to the AuctionManager.
            gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
            starting_asset_balance = 1_000_000
            self._optin_asset_and_seed_balance(
                receiver=Address(seller.address),
                asset_id=gold_asset_id,
                amount=starting_asset_balance,
                asset_reserve=gold_asset_manager_address,
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
            result = auction_manager_client.delete_finalized_auction(
                seller_auction_client.app_id
            )
            self.assert_app_txn_note(
                AuctionManagerClient.DELETE_FINALIZED_AUCTION_NOTE, result.tx_info
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
            # after witdrawing all available ALGO, the contract ALGO balance should match its min balance
            app_account_info = auction_manager_client.get_application_account_info()
            self.assertEqual(
                app_account_info["amount"], app_account_info["min-balance"]
            )

    def test_withdraw(self):
        # SETUP
        accounts = self.get_sandbox_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        auction_manager_client = create_auction_manager(
            algod_client=self.algod_client,
            signer=creator.signer,
        )
        seller_app_client = auction_manager_client.copy(signer=seller.signer)

        with self.subTest("AuctionManager has not yet deleted finalized any auctions"):
            self.assertIsNone(auction_manager_client.withdraw())

            seller_auction_client = seller_app_client.create_auction()
            self.assertIsNone(auction_manager_client.withdraw())

            seller_auction_client.cancel()
            self.assertIsNone(auction_manager_client.withdraw())
            seller_auction_client.finalize()
            self.assertIsNone(auction_manager_client.withdraw())

        with self.subTest(
            "when a finalized auction is deleted, then revenue is collected and becomes available for withdrawal"
        ):
            auction_manager_client.delete_finalized_auction(
                seller_auction_client.app_id
            )
            result = auction_manager_client.withdraw()
            self.assertIsNotNone(result)
            self.assert_app_txn_note(AuctionManagerClient.WITHDRAW_NOTE, result.tx_info)


if __name__ == "__main__":
    unittest.main()
