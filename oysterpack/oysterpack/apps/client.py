"""
Provides client side support to interact with Algorand smart contracts, i.e., applications.
"""
from base64 import b64decode
from typing import Any, cast

from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.transaction import SuggestedParams
from algosdk.v2client.algod import AlgodClient
from beaker import Application
from beaker.client.application_client import ApplicationClient
from beaker.precompile import PrecompiledApplication

from oysterpack.algorand.client.model import AppId, Address, MicroAlgos
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee


# TODO: this approach did not work - beaker team has identified this as a bug
# The TEAL code is not being deterministically compiled. The compiled TEAL code is logically the same.
# However, the issue lies in how scratch var slots are assigned.
def verify_app(app_client: ApplicationClient):
    """
    Verifies that the app ID references an app whose program binaries matches the app referenced by the ApplicationClient.

    :raise AssertionError: if code does not match
    """

    try:
        app = cast(
            dict[str, Any], app_client.client.application_info(app_client.app_id)
        )
        approval_program = b64decode(app["params"]["approval-program"])
        clear_state_program = b64decode(app["params"]["clear-state-program"])

        assert app_client.approval
        assert app_client.clear

        if approval_program != app_client.approval.raw_binary:
            raise AssertionError("Invalid app ID - approval program does not match")

        if clear_state_program != app_client.clear.raw_binary:
            raise AssertionError("Invalid app ID - clear program does not match")
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AssertionError("Invalid app ID") from err
        raise err


def verify_app_id(
    app_id: AppId,
    app: Application,
    algod_client: AlgodClient,
):
    """
    Verifies that the app ID references an app whose program binaries matches the specified AppPrecompile

    :raise AssertionError: if code does not match
    """

    try:
        precompiled_app = PrecompiledApplication(app, algod_client)

        app_info = cast(dict[str, Any], algod_client.application_info(app_id))
        approval_program = b64decode(app_info["params"]["approval-program"])
        clear_state_program = b64decode(app_info["params"]["clear-state-program"])

        if precompiled_app.approval_program.raw_binary != approval_program:
            raise AssertionError("Invalid app ID - approval program does not match")

        if precompiled_app.clear_program.raw_binary != clear_state_program:
            raise AssertionError("Invalid app ID - clear program does not match")
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AssertionError("Invalid app ID") from err
        raise err


class AppClient:
    """
    Algorand application client
    """

    def __init__(self, app_client: ApplicationClient):
        # create a new instance to clear the internal client state
        self._app_client = ApplicationClient(
            app=app_client._app_client.app_spec,
            app_id=app_client.app_id,
            signer=app_client.signer,
            sender=app_client.sender,
            client=app_client.client,
        )

        # TODO: waiting on a beaker fix for this to work
        # verify_app(self._app_client)

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
        return self._app_client.get_global_state()

    def get_application_info(self) -> dict[str, Any]:
        """
        :return: application smart contract info
        """
        return cast(
            dict[str, Any], self._app_client.client.application_info(self.app_id)
        )

    def suggested_params(self, txn_count: int = 1) -> SuggestedParams:
        """
        Uses flat fees based on the min fee and number of transactions.

        :param txn_count: number of tr
        :return:
        """
        return suggested_params_with_flat_flee(
            algod_client=self._app_client.client, txn_count=txn_count
        )
