"""
Provides client side support to interact with Algorand smart contracts, i.e., applications.
"""

from typing import Any

from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.logic import get_application_address
from algosdk.transaction import SuggestedParams
from algosdk.v2client.algod import AlgodClient
from beaker import Application
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import AppId, Address, MicroAlgos
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee


class AppClient:
    """
    Algorand application client
    """

    def __init__(
        self,
        app: Application,
        app_id: AppId,
        algod_client: AlgodClient,
        signer: TransactionSigner,
        sender: Address | None = None,
    ):
        self._app_client = ApplicationClient(
            app=app,
            app_id=app_id,
            client=algod_client,
            signer=signer,
            sender=sender,
        )

    @property
    def contract_address(self) -> Address:
        """
        NOTE: the address is derived from its app ID
        :return: application Algorand account Address
        """
        return Address(get_application_address(self._app_client.app_id))

    @property
    def app_id(self) -> AppId:
        """
        :return: AppId
        """
        return AppId(self._app_client.app_id)

    def fund(self, amount: MicroAlgos):
        """
        Transfers the specified ALGO amount from the transaction sender to the app.

        :param amount: amount of ALGO to send to the app
        """
        if amount > 0:
            self._app_client.fund(amount)

    def get_application_account_info(self) -> dict[str, Any]:
        """
        :return: app Algorand account info
        """
        return self._app_client.get_application_account_info()

    def get_application_state(self) -> dict[bytes | str, bytes | str | int]:
        """
        The app's state is automatically converted to python native types using its ApplicationSpec

        :return: app's global state
        """
        return self._app_client.get_application_state()

    def get_application_info(self) -> dict[str, Any]:
        """
        :return: application smart contract info
        """
        return self._app_client.client.application_info(self.app_id)

    def suggested_params(self, txn_count: int = 1) -> SuggestedParams:
        """
        Uses flat fees based on the min fee and number of transactions.

        :param txn_count: number of tr
        :return:
        """
        return suggested_params_with_flat_flee(
            algod_client=self._app_client.client, txn_count=txn_count
        )
