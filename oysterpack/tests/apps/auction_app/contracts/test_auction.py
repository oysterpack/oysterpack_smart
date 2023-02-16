import unittest
from datetime import datetime, UTC, timedelta
from typing import cast

from algosdk.transaction import wait_for_confirmation
from beaker import sandbox
from beaker.client import LogicException

from oysterpack.algorand.client.accounts import get_asset_holding
from oysterpack.algorand.client.model import Address, AssetHolding
from oysterpack.algorand.client.transactions import asset
from oysterpack.apps.auction_app.client.auction_client import (
    AuctionClient,
    AuthError,
    AuctionBidder,
)
from oysterpack.apps.auction_app.contracts.auction import (
    Auction,
    AuctionStatus,
    auction_storage_fees,
)
from tests.algorand.test_support import AlgorandTestCase


class AuctionTestCase(AlgorandTestCase):
    def test_create(self):
        # SETUP
        logger = super().get_logger("test_create")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )

        # ACT
        creator_app_client.create(seller=seller.address)
        auction_client = AuctionClient(creator_app_client)

        # ASSERT
        app_state = creator_app_client.get_application_state()
        logger.info(f"app_state: {app_state}")
        self.assertEqual(seller.address, auction_client.get_seller_address())
        self.assertEqual(app_state[Auction.status.str_key()], AuctionStatus.NEW.value)

        self.assertEqual(
            creator_app_client.call(Auction.app_name).return_value, Auction.APP_NAME
        )

        with self.subTest("Auction cannot be updated"):
            with self.assertRaises(LogicException):
                creator_app_client.update()

    def test_set_bid_asset(self):
        # SETUP
        logger = super().get_logger("test_set_bid_asset")

        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000

        self.assertIsNone(seller_app_client.get_bid_asset_holding())

        with self.subTest("only the seller can set the bid asset"):
            with self.assertRaises(AuthError):
                creator_app_client.set_bid_asset(bid_asset_id, min_bid)

        with self.subTest("the bid can be set when the auction status is new"):
            result = seller_app_client.set_bid_asset(
                bid_asset_id,
                min_bid,
            )
            # ASSERT
            app_state = creator_app_client.get_auction_state()
            logger.info(f"app_state: {app_state}")
            self.assertEqual(app_state.bid_asset_id, bid_asset_id)
            self.assertEqual(app_state.min_bid, min_bid)
            # checks the Auction bid asset holding
            bid_asset_holding = seller_app_client.get_bid_asset_holding()
            self.assertIsNotNone(bid_asset_holding)
            self.assertEqual(
                cast(AssetHolding, bid_asset_holding).asset_id, bid_asset_id
            )
            self.assert_app_txn_note(AuctionClient.SET_BID_ASSET_NOTE, result.tx_info)

        with self.subTest("setting the bid asset again to the same values is a noop "):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)

        with self.subTest("update the min bid"):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid * 2)
            app_state = seller_app_client.get_auction_state()
            self.assertEqual(bid_asset_id, app_state.bid_asset_id)
            self.assertEqual(min_bid * 2, app_state.min_bid)

        with self.subTest("change the bid asset settings"):
            bid_asset_id, _asset_manager_address = self.create_test_asset("goUSD")
            min_bid = 2_000_000
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)

            app_state = seller_app_client.get_auction_state()
            self.assertEqual(bid_asset_id, app_state.bid_asset_id)
            self.assertEqual(min_bid, app_state.min_bid)

            self.assertEqual(
                seller_app_client.get_bid_asset_holding().asset_id, bid_asset_id
            )

    def test_optout_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        bid_asset_id, _asset_manager_address = self.create_test_asset("USD$")
        min_bid = 1_000_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)

        # ACT
        result = seller_app_client.optout_asset(bid_asset_id)
        self.assertIsNotNone(result)
        self.assert_app_txn_note(AuctionClient.OPTOUT_ASSET_NOTE, result.tx_info)
        app_account_info = seller_app_client.get_application_account_info()
        self.assertEqual(len(app_account_info["assets"]), 0)

        with self.subTest("opting out again is a noop"):
            self.assertIsNone(seller_app_client.optout_asset(bid_asset_id))

        with self.subTest(
            "after opting out the bid asset, the bid asset can be set again"
        ):
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)
            app_account_info = seller_app_client.get_application_account_info()
            self.assertEqual(len(app_account_info["assets"]), 1)
            self.assertEqual(app_account_info["assets"][0]["asset-id"], bid_asset_id)

        with self.subTest("only the seller can optout an asset"):
            with self.assertRaises(AuthError):
                creator_app_client.optout_asset(bid_asset_id)

    def test_optin_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        gold_asset_id, _asset_manager_address = self.create_test_asset("GOLD$")

        # auction should start with zero assets
        auction_assets = seller_app_client.get_auction_assets()
        self.assertEqual(len(auction_assets), 0)

        # ACT
        with self.subTest("only the seller can optin an asset"):
            with self.assertRaises(AuthError):
                creator_app_client.optin_asset(gold_asset_id)

        result = seller_app_client.optin_asset(gold_asset_id)
        # ASSERT asset was opted in
        self.assertIsNotNone(result)
        self.assert_app_txn_note(AuctionClient.OPTIN_ASSET_NOTE, result.tx_info)
        self.assertEqual(len(seller_app_client.get_auction_assets()), 1)
        # would fail if the contract did not hold the asset
        self.algod_client.account_asset_info(
            seller_app_client.contract_address, gold_asset_id
        )

        with self.subTest("opting is an asset that is already opted in is a noop"):
            self.assertIsNone(seller_app_client.optin_asset(gold_asset_id))

        with self.subTest("optin a second asset"):
            go_mint_asset_id, _asset_manager_address = self.create_test_asset("goMINT")
            seller_app_client.optin_asset(go_mint_asset_id)
            # Assert
            auction_assets = seller_app_client.get_auction_assets()
            self.assertEqual(len(auction_assets), 2)
            self.algod_client.account_asset_info(
                seller_app_client.contract_address, gold_asset_id
            )
            self.algod_client.account_asset_info(
                seller_app_client.contract_address, go_mint_asset_id
            )

    def test_deposit_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        gold_asset_id, asset_manager_address = self.create_test_asset("GOLD$")

        # opt in GOLD$ for the seller account
        txn = asset.opt_in(
            account=Address(seller.address),
            asset_id=gold_asset_id,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # transfer assets to the seller account
        txn = asset.transfer(
            sender=asset_manager_address,
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=1_000_000,
            suggested_params=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # ACT
        deposit_amount = 10_000
        asset_holding = seller_app_client.deposit_asset(gold_asset_id, deposit_amount)
        self.assertEqual(asset_holding.asset_id, gold_asset_id)
        self.assertEqual(asset_holding.amount, deposit_amount)

        with self.subTest("only the seller can deposit assets"):
            with self.assertRaises(AuthError):
                creator_app_client.deposit_asset(gold_asset_id, deposit_amount)

    def test_withdraw_asset(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        gold_asset_id, asset_manager_address = self.create_test_asset("GOLD$")

        # opt in GOLD$ for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=asset_manager_address,
        )
        with self.assertRaises(AssertionError) as err:
            seller_app_client.withdraw_asset(gold_asset_id, 1000)
        self.assertEqual("Auction does not hold the asset", str(err.exception))

        seller_app_client.deposit_asset(gold_asset_id, starting_asset_balance)

        with self.subTest("only seller can withdraw assets"):
            with self.assertRaises(AuthError):
                creator_app_client.withdraw_asset(gold_asset_id, 1000)

        with self.subTest("seller withdraws asset"):
            withdraw_amount = 100_000
            asset_holding = seller_app_client.withdraw_asset(
                gold_asset_id, withdraw_amount
            )
            self.assertEqual(asset_holding.asset_id, gold_asset_id)
            self.assertEqual(
                asset_holding.amount, starting_asset_balance - withdraw_amount
            )

        with self.subTest("seller tries to withdraw <= 0"):
            with self.assertRaises(AssertionError):
                seller_app_client.withdraw_asset(gold_asset_id, 0)
            with self.assertRaises(AssertionError):
                seller_app_client.withdraw_asset(gold_asset_id, -1)

        with self.subTest("seller tries to over withdraw"):
            with self.assertRaises(AssertionError) as err:
                seller_app_client.withdraw_asset(gold_asset_id, starting_asset_balance)
            self.assertEqual(
                "Auction has insufficient funds - asset balance is 900000",
                str(err.exception),
            )

    def test_commit(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
        bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

        # opt in GOLD$ for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=gold_asset_manager_address,
        )

        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        start_time = datetime.now(UTC) + timedelta(days=1)
        end_time = start_time + timedelta(days=3)

        with self.subTest("only seller can commit the auction"):
            with self.assertRaises(AuthError):
                creator_app_client.commit(start_time, end_time)

        with self.subTest("end_time < start_time"):
            with self.assertRaises(AssertionError):
                seller_app_client.commit(end_time, start_time)

        with self.subTest("end_time == start_time"):
            with self.assertRaises(AssertionError):
                seller_app_client.commit(end_time, end_time)

        with self.subTest("bid asset must be set"):
            with self.assertRaises(AssertionError):
                seller_app_client.commit(start_time, end_time)

        seller_app_client.set_bid_asset(bid_asset_id, 10_000)

        with self.subTest("auction must have assets"):
            with self.assertRaises(AssertionError):
                seller_app_client.commit(start_time, end_time)

        seller_app_client.optin_asset(gold_asset_id)

        with self.subTest("auction asset balancs must be > 0"):
            with self.assertRaises(AssertionError):
                seller_app_client.commit(start_time, end_time)

        seller_app_client.deposit_asset(gold_asset_id, 10_000)

        with self.subTest("auction is prepared to commit"):
            result = seller_app_client.commit(start_time, end_time)
            self.assert_app_txn_note(AuctionClient.COMMIT_NOTE, result.tx_info)
            auction_state = seller_app_client.get_auction_state()
            self.assertEqual(AuctionStatus.COMMITTED, auction_state.status)
            self.assertEqual(
                int(start_time.timestamp()), int(auction_state.start_time.timestamp())
            )
            self.assertEqual(
                int(end_time.timestamp()), int(auction_state.end_time.timestamp())
            )

        with self.subTest("auction cannot be cancelled once it is committed"):
            with self.assertRaises(AssertionError):
                seller_app_client.cancel()

    def test_bid(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()
        bidder = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        auction_bidder = AuctionBidder(creator_app_client.prepare(signer=bidder.signer))

        gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
        bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

        # opt in GOLD$ for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=gold_asset_manager_address,
        )
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )
        self._optin_asset_and_seed_balance(
            receiver=Address(bidder.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        min_bid = 10_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)
        seller_app_client.optin_asset(gold_asset_id)
        seller_app_client.deposit_asset(gold_asset_id, 10_000)

        with self.subTest("submit bid before it has been committed"):
            with self.assertRaises(AssertionError) as err:
                auction_bidder.bid(min_bid)
            self.assertEqual("auction is not open for bidding", str(err.exception))

        start_time = seller_app_client.latest_timestamp()
        end_time = start_time + timedelta(days=3)
        seller_app_client.commit(start_time, end_time)

        with self.subTest("first bid is minimum bid"):
            result = auction_bidder.bid(min_bid)
            auction_state = seller_app_client.get_auction_state()
            self.assertEqual(auction_state.highest_bid, min_bid)
            self.assertEqual(auction_state.highest_bidder_address, bidder.address)
            self.assert_app_txn_note(AuctionBidder.BID_NOTE, result.tx_info)

        with self.subTest("submit higher bid"):
            prior_highest_bid = seller_app_client.get_auction_state().highest_bid
            bid = prior_highest_bid + 1
            bidder_bid_asset_holding_1 = get_asset_holding(
                Address(bidder.address), bid_asset_id, self.algod_client
            )
            auction_bidder.bid(bid)
            auction_state = seller_app_client.get_auction_state()
            self.assertEqual(auction_state.highest_bid, bid)
            self.assertEqual(auction_state.highest_bidder_address, bidder.address)
            # bidder should have been refunded
            bidder_bid_asset_holding_2 = get_asset_holding(
                Address(bidder.address), bid_asset_id, self.algod_client
            )
            self.assertEqual(
                bidder_bid_asset_holding_1.amount - 1, bidder_bid_asset_holding_2.amount
            )

        with self.subTest("previous bidder account has opted-out of the bid asset"):
            # close out the bid asset on the bidder account back to the bid asset manager account
            from oysterpack.algorand.client.transactions.asset import close_out

            txn = close_out(
                account=Address(bidder.address),
                asset_id=bid_asset_id,
                close_to=bid_asset_manager_address,
                suggested_params=self.algod_client.suggested_params(),
            )
            signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
            txid = self.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.algod_client, txid)
            self.assertIsNone(
                get_asset_holding(
                    Address(bidder.address), bid_asset_id, self.algod_client
                )
            )

            # submit a new high bid using the bid asset manager account
            assert bid_asset_manager_address != bidder.address
            auction_bidder_2 = AuctionBidder(
                creator_app_client.prepare(
                    signer=self.sandbox_default_wallet_transaction_signer(),
                    sender=bid_asset_manager_address,
                )
            )
            # ACT - submit higher bid
            previous_highest_bid = seller_app_client.get_auction_state().highest_bid
            auction_bidder_2.bid(previous_highest_bid + 1)
            # ASSERT
            # auction retained previous highest bid amount
            auction_bid_asset_holding = get_asset_holding(
                seller_app_client.contract_address, bid_asset_id, self.algod_client
            )
            expected_auction_bid_asset_holding = (
                auction_bidder_2.get_auction_state().highest_bid + previous_highest_bid
            )
            self.assertEqual(
                expected_auction_bid_asset_holding, auction_bid_asset_holding.amount
            )

        with self.subTest("bids are rejected if the auction has ended"):
            # TODO
            pass

    def test_accept_bid(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()
        bidder = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        auction_bidder = AuctionBidder(creator_app_client.prepare(signer=bidder.signer))

        gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
        bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

        # opt in GOLD$ for the seller account
        starting_asset_balance = 1_000_000
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=gold_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=gold_asset_manager_address,
        )
        self._optin_asset_and_seed_balance(
            receiver=Address(seller.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )
        self._optin_asset_and_seed_balance(
            receiver=Address(bidder.address),
            asset_id=bid_asset_id,
            amount=starting_asset_balance,
            asset_reserve_address=bid_asset_manager_address,
        )

        min_bid = 10_000
        seller_app_client.set_bid_asset(bid_asset_id, min_bid)
        seller_app_client.optin_asset(gold_asset_id)
        seller_app_client.deposit_asset(gold_asset_id, 10_000)

        with self.assertRaises(AssertionError) as err:
            seller_app_client.accept_bid()
        self.assertEqual(str(err.exception), "bidding sesssion is not open")

        start_time = seller_app_client.latest_timestamp()
        end_time = start_time + timedelta(days=3)
        seller_app_client.commit(start_time, end_time)

        with self.assertRaises(AssertionError) as err:
            seller_app_client.accept_bid()
        self.assertEqual(str(err.exception), "auction has no bid")

        auction_bidder.bid(min_bid)
        auction_state = seller_app_client.get_auction_state()
        self.assertEqual(auction_state.highest_bid, min_bid)
        self.assertEqual(auction_state.highest_bidder_address, bidder.address)

        result = seller_app_client.accept_bid()
        self.assert_app_txn_note(AuctionClient.ACCEPT_BID_NOTE, result.tx_info)
        auction_state = seller_app_client.get_auction_state()
        self.assertEqual(AuctionStatus.BID_ACCEPTED, auction_state.status)

    def test_cancel(self):
        # SETUP
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        seller_app_client = AuctionClient(
            creator_app_client.prepare(signer=seller.signer)
        )
        creator_app_client = AuctionClient(creator_app_client)

        with self.subTest("only seller is authorized to cancel the auction"):
            with self.assertRaises(AuthError):
                creator_app_client.cancel()

        with self.subTest(
            "cancelling the auction when it has no asset holdings sets its status to Finalized"
        ):
            result = seller_app_client.cancel()
            self.assert_app_txn_note(AuctionClient.CANCEL_NOTE, result.tx_info)
            auction_state = seller_app_client.get_auction_state()
            self.assertEqual(AuctionStatus.FINALIZED, auction_state.status)

        with self.subTest(
            "if the Auction has asset-holdings, then the status will be set to Cancelled"
        ):
            creator_app_client = self.sandbox_application_client(
                Auction(), signer=creator.signer
            )
            creator_app_client.create(seller=seller.address)
            seller_app_client = AuctionClient(
                creator_app_client.prepare(signer=seller.signer)
            )

            gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
            starting_asset_balance = 1_000_000
            self._optin_asset_and_seed_balance(
                receiver=Address(seller.address),
                asset_id=gold_asset_id,
                amount=starting_asset_balance,
                asset_reserve_address=gold_asset_manager_address,
            )
            seller_app_client.set_bid_asset(gold_asset_id, 10_000)

            # ACT
            result = seller_app_client.cancel()
            # ASSERT
            auction_state = seller_app_client.get_auction_state()
            self.assertEqual(AuctionStatus.CANCELLED, auction_state.status)
            self.assert_app_txn_note(AuctionClient.CANCEL_NOTE, result.tx_info)

    def test_finalize(self):
        # SETUP
        def create_auction() -> (AuctionClient, AuctionBidder):
            accounts = sandbox.get_accounts()
            creator = accounts.pop()
            seller = accounts.pop()
            bidder = accounts.pop()

            creator_app_client = self.sandbox_application_client(
                Auction(), signer=creator.signer
            )
            creator_app_client.create(seller=seller.address)
            seller_app_client = AuctionClient(
                creator_app_client.prepare(signer=seller.signer)
            )
            auction_bidder = AuctionBidder(
                creator_app_client.prepare(signer=bidder.signer)
            )

            gold_asset_id, gold_asset_manager_address = self.create_test_asset("GOLD$")
            bid_asset_id, bid_asset_manager_address = self.create_test_asset("USD$")

            # opt in GOLD$ for the seller account
            starting_asset_balance = 1_000_000
            self._optin_asset_and_seed_balance(
                receiver=Address(seller.address),
                asset_id=gold_asset_id,
                amount=starting_asset_balance,
                asset_reserve_address=gold_asset_manager_address,
            )
            self._optin_asset_and_seed_balance(
                receiver=Address(seller.address),
                asset_id=bid_asset_id,
                amount=starting_asset_balance,
                asset_reserve_address=bid_asset_manager_address,
            )
            self._optin_asset_and_seed_balance(
                receiver=Address(bidder.address),
                asset_id=bid_asset_id,
                amount=starting_asset_balance,
                asset_reserve_address=bid_asset_manager_address,
            )

            min_bid = 10_000
            seller_app_client.set_bid_asset(bid_asset_id, min_bid)
            seller_app_client.optin_asset(gold_asset_id)
            seller_app_client.deposit_asset(gold_asset_id, 10_000)

            with self.subTest("finalize before it has been committed"):
                with self.assertRaises(AssertionError) as err:
                    seller_app_client.finalize()
                self.assertEqual(
                    "auction cannot be finalized because it has not ended",
                    str(err.exception),
                )

            return seller_app_client, auction_bidder

        with self.subTest("auction bid has been accepted"):
            seller_app_client, auction_bidder = create_auction()
            # commit the auction
            start_time = seller_app_client.latest_timestamp()
            end_time = start_time + timedelta(days=3)
            seller_app_client.commit(start_time, end_time)
            # bidder opts in auction assets
            txids = auction_bidder.optin_auction_assets()
            self.assert_app_txn_notes(AuctionBidder.OPTIN_AUCTION_ASSETS_NOTE, txids)

            # place bid
            auction_bidder.bid(auction_bidder.get_auction_state().min_bid)
            # accet bid
            seller_app_client.accept_bid()
            # ACT
            auction_asset_holdings = seller_app_client.get_auction_assets()
            seller_bid_asset_holding_1 = self.algod_client.account_asset_info(
                seller_app_client._app_client.sender,
                seller_app_client.get_auction_state().bid_asset_id,
            )
            results = seller_app_client.finalize()
            self.assertIsNotNone(results)
            for result in results:
                self.assert_app_txn_note(AuctionClient.FINALIZE_NOTE, result.tx_info)

            # ASSERT
            auction_account_info = self.algod_client.account_info(
                seller_app_client.contract_address
            )
            self.assertEqual(auction_account_info["total-assets-opted-in"], 0)
            self.assertEqual(
                AuctionStatus.FINALIZED, seller_app_client.get_auction_state().status
            )
            # check auction assets were transferred to highest bidder
            auction_bidder_assets = dict(
                [
                    (asset["asset-id"], asset["amount"])
                    for asset in self.algod_client.account_info(
                        auction_bidder._app_client.sender
                    )["assets"]
                ]
            )
            for asset_holding in auction_asset_holdings:
                self.assertEqual(
                    asset_holding.amount, auction_bidder_assets[asset_holding.asset_id]
                )
            # check that the bid asset was transferred to the seller
            seller_bid_asset_holding_2 = self.algod_client.account_asset_info(
                seller_app_client._app_client.sender,
                seller_app_client.get_auction_state().bid_asset_id,
            )
            print(seller_bid_asset_holding_2)
            self.assertEqual(
                seller_bid_asset_holding_1["asset-holding"]["amount"]
                + seller_app_client.get_auction_state().highest_bid,
                seller_bid_asset_holding_2["asset-holding"]["amount"],
            )

        with self.subTest("auction was cancelled"):
            seller_app_client, auction_bidder = create_auction()
            seller_app_client.cancel()

            # ACT
            results = seller_app_client.finalize()
            self.assertIsNotNone(results)
            for result in results:
                self.assert_app_txn_note(AuctionClient.FINALIZE_NOTE, result.tx_info)

            # ASSERT
            auction_account_info = self.algod_client.account_info(
                seller_app_client.contract_address
            )
            self.assertEqual(auction_account_info["total-assets-opted-in"], 0)
            self.assertEqual(
                AuctionStatus.FINALIZED, seller_app_client.get_auction_state().status
            )

    def test_auction_creation_storage_fees(self):
        accounts = sandbox.get_accounts()
        creator = accounts.pop()
        seller = accounts.pop()

        account_info_1 = self.algod_client.account_info(creator.address)
        creator_app_client = self.sandbox_application_client(
            Auction(), signer=creator.signer
        )
        creator_app_client.create(seller=seller.address)
        account_info_2 = self.algod_client.account_info(creator.address)
        expected_auction_storage_fees = (
            account_info_2["min-balance"] - account_info_1["min-balance"]
        )
        self.assertEqual(expected_auction_storage_fees, auction_storage_fees())


if __name__ == "__main__":
    unittest.main()
