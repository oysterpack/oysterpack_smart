import asyncio
import unittest
from concurrent.futures import ProcessPoolExecutor
from typing import ClassVar

from algosdk.account import generate_account
from algosdk.transaction import Transaction
from beaker.consts import algo
from black import Tuple
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos, AppId, Address
from oysterpack.algorand.client.transactions.payment import transfer_algo
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    SecureMessageWebsocketHandler,
)
from oysterpack.apps.multisig_wallet_connect.domain.activity import (
    TxnActivityId,
    AppActivityId,
    AppActivitySpec,
    TxnActivitySpec,
    InvalidAppActivity,
    InvalidTxnActivity,
)
from oysterpack.apps.multisig_wallet_connect.message_handlers.sign_transactions import (
    SignTransactionsHandler,
)
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    SignTransactionsRequestAccepted,
)
from oysterpack.apps.multisig_wallet_connect.protocols.multisig_service import (
    MultisigService,
    ServiceFee,
)
from tests.algorand.messaging import server_ssl_context, client_ssl_context
from tests.algorand.test_support import AlgorandTestCase
from tests.support.websockets import create_websocket_server
from tests.test_support import OysterPackIsolatedAsyncioTestCase


class AppActivitySpecMock(AppActivitySpec):
    def __init__(
        self,
        activity_id: AppActivityId,
        name: str,
        description: str,
        validation_exception: InvalidAppActivity | None = None,
    ):
        super().__init__(
            activity_id=activity_id,
            name=name,
            description=description,
        )
        self._validation_exception = validation_exception

    async def validate(self, txns: list[Tuple[Transaction, TxnActivityId]]):
        if self._validation_exception:
            raise self._validation_exception


class TxnActivitySpecMock(TxnActivitySpec):
    def __init__(
        self,
        activity_id: TxnActivityId,
        name: str,
        description: str,
        validation_exception: InvalidTxnActivity | None = None,
    ):
        super().__init__(
            activity_id=activity_id,
            name=name,
            description=description,
        )
        self._validation_exception = validation_exception

    async def validate(self, txn: Transaction):
        if self._validation_exception:
            raise self._validation_exception


class MultisigServiceMock(MultisigService):
    """
    MultisigService
    """

    service_fee_payee: ClassVar[Address] = generate_account()[1]

    async def service_fee(self) -> ServiceFee:
        """
        :return: ServiceFee
        """
        return ServiceFee(amount=MicroAlgos(2000), pay_to=self.service_fee_payee)

    async def is_app_registered(self, app_id: AppId) -> bool:
        """
        :param app_id: AppId
        :return: True if the app is registered with the service
        """
        return True

    async def is_account_registered(self, account: Address, app_id: AppId) -> bool:
        """
        In order for an account to receive transactions through the multisig service, the account must be opted into
        the multisig service and the app.

        If an account opts out of the multisig service, then the account effectively disables the multisig service.
        Even though the account may still be opted into apps, they will stop receiving transactions.

        :param account: Address
        :param app_id: AppId
        :return: True if the account has opted into the multisig service and the app
        """
        return True

    async def is_app_activity_registered(
        self, app_id: AppId, app_activity_id: AppActivityId
    ) -> bool:
        """
        Returns false if the app activity is not registered.
        """
        return True

    def get_app_activity_spec(
        self, app_activity_id: AppActivityId
    ) -> AppActivitySpec | None:
        """
        Looks up the AppActivitySpec for the specified AppActivityId
        """
        return AppActivitySpecMock(
            activity_id=app_activity_id, name="name", description="description"
        )

    def get_txn_activity_spec(
        self, txn_activity_id: TxnActivityId
    ) -> TxnActivitySpec | None:
        """
        Looks up the TxnActivitySpec for the specified TxnActivityId
        """
        return TxnActivitySpecMock(
            activity_id=txn_activity_id, name="name", description="description"
        )


class SignTransactionsMessageHandlerTestCase(
    AlgorandTestCase, OysterPackIsolatedAsyncioTestCase
):
    executor: ProcessPoolExecutor

    @classmethod
    def setUpClass(cls) -> None:
        cls.executor = ProcessPoolExecutor()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.executor.shutdown(wait=True)

    def setUp(self) -> None:
        self.sender_private_key = AlgoPrivateKey(generate_account()[0])
        self.recipient_private_key = AlgoPrivateKey(generate_account()[0])

    async def test_single_transaction(self):
        # SETUP
        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[
                SignTransactionsHandler(
                    multisig_service=MultisigServiceMock(),
                )
            ],
            executor=self.executor,
        )

        txn = transfer_algo(
            sender=self.sender_private_key.signing_address,
            receiver=self.recipient_private_key.signing_address,
            amount=MicroAlgos(1 * algo),
            suggested_params=self.algod_client.suggested_params(),
        )
        request = SignTransactionsRequest(
            app_id=AppId(100),
            signer=self.sender_private_key.signing_address,
            transactions=[(txn, TxnActivityId())],
            app_activity_id=AppActivityId(),
        )

        server = create_websocket_server(
            handler=SecureMessageWebsocketHandler(handler=secure_message_handler),
            ssl_context=server_ssl_context(),
        )

        async with server.running_server() as server:
            async with connect(
                f"wss://localhost:{server.port}",
                ssl=client_ssl_context(),
            ) as websocket:
                client = SecureMessageClient(
                    websocket=websocket,
                    private_key=self.sender_private_key,
                    executor=self.executor,
                )
                await client.send(
                    request,
                    self.recipient_private_key.encryption_address,
                )
                msg = await asyncio.wait_for(client.recv(), 0.1)
                await client.close()
                self.assertEqual(
                    SignTransactionsRequestAccepted.message_type(), msg.msg_type
                )
                SignTransactionsRequestAccepted.unpack(msg.data)


if __name__ == "__main__":
    unittest.main()
