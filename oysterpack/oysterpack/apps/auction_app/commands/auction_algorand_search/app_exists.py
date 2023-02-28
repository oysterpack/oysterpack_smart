"""
Command used to check if an application exists on Algorand
"""

from algosdk.error import AlgodHTTPError
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import AppId
from oysterpack.core.command import Command


class AppExists(Command[AppId, bool]):
    """
    Checks that the application exists on Algorand
    """

    def __init__(self, algod_client: AlgodClient):
        self._algod_client = algod_client

    def __call__(self, app_id: AppId) -> bool:

        try:
            self._algod_client.application_info(app_id)
            return True
        except AlgodHTTPError as err:
            if err.code == 404:
                return False
            raise
