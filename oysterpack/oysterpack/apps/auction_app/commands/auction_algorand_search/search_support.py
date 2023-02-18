"""
Provides Algorand search support
"""
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from oysterpack.algorand.client.model import AppId, Address


class AuctionAlgorandSearchSupport:
    """
    Provides support for searching Algorand on-chain data for Auction apps
    """

    def __init__(
        self,
        indexer_client: IndexerClient,
        algod_client: AlgodClient,
        auction_manager_app_id: AppId,
    ):
        # TODO: verify that the auction manager app ID point to a valid AuctionManager smart contract
        # waiting on bug fix from beaker team
        # verify_app_id(
        #     auction_manager_app_id,
        #     AppPrecompile(AuctionManager()),
        #     algod_client,
        # )

        self._indexer_client = indexer_client
        self._algod_client = algod_client
        self.auction_manager_app_id = auction_manager_app_id

    @property
    def auction_manager_address(self) -> Address:
        """
        :return: AuctionManager application address
        """
        return Address(get_application_address(self.auction_manager_app_id))
