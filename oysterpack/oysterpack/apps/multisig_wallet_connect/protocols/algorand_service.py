"""
Algorand Async Service
"""
from typing import Protocol

from algosdk.transaction import SuggestedParams

from oysterpack.algorand.client.model import Address, MicroAlgos


class AlgorandService(Protocol):
    async def suggested_params_with_flat_flee(
        self, txn_count: int = 1
    ) -> SuggestedParams:
        """
        :param txn_count:
        :return: SuggestedParams
        """
        ...

    async def get_algo_available_balance(self, account: Address) -> MicroAlgos:
        """
        :param account: Address
        :return: account's available ALGO balance
        """
        ...
