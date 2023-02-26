"""
Provides Algorand search support
"""
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient


class AuctionAlgorandSearchSupport:
    """
    Provides support for searching Algorand on-chain data for Auction apps
    """

    def __init__(
        self,
        indexer_client: IndexerClient,
        algod_client: AlgodClient,
    ):
        self._indexer_client = indexer_client
        self._algod_client = algod_client
