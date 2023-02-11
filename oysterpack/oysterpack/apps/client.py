from typing import Any

from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from beaker import Application
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import AppId, Address


class AppClient:
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
        return Address(get_application_address(self._app_client.app_id))

    @property
    def app_id(self) -> AppId:
        return AppId(self._app_client.app_id)

    def fund(self, algo_amount: int):
        if algo_amount > 0:
            self._app_client.fund(algo_amount)

    def get_application_account_info(self) -> dict[str, Any]:
        return self._app_client.get_application_account_info()

    def get_application_state(self) -> dict[bytes | str, bytes | str | int]:
        return self._app_client.get_application_state()
