import unittest
from typing import Final, cast, Any

from algosdk import kmd
from algosdk.account import generate_account
from algosdk.error import AlgodHTTPError, KMDHTTPError
from algosdk.transaction import (
    Multisig,
    PaymentTxn,
    wait_for_confirmation,
    SuggestedParams,
    MultisigTransaction,
)
from algosdk.v2client.algod import AlgodClient
from algosdk.wallet import Wallet
from beaker import sandbox
from beaker.consts import algo
from beaker.sandbox import SandboxAccount
from beaker.sandbox.kmd import get_sandbox_default_wallet, wallet_handle_by_name
from ulid import ULID


class AccountDoesNotExist(Exception):
    pass


Address = str
MicroAlgos = int


def get_auth_address(address: Address, algod_client: AlgodClient) -> Address:
    """
    Returns the authorized signing account for the specified address. This only applies to rekeyed acccounts.
    If the account is not rekeyed, then the account is the authorized account, i.e., the account signs for itself.
    """

    try:
        account_info = cast(
            dict[str, Any],
            algod_client.account_info(address, exclude="all"),  # type: ignore
        )
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AccountDoesNotExist from err
        raise
    if "auth-addr" in account_info:
        return Address(account_info["auth-addr"])
    return address


def rekey(
    account: Address,
    rekey_to: Address,
    suggested_params: SuggestedParams,
) -> PaymentTxn:
    """
    Creates a transaction to rekey the account to the specified authorized account.

    NOTE: the transaction must be signed by the current authorized account.
    """

    return PaymentTxn(
        sender=account,
        receiver=account,
        amt=0,
        rekey_to=rekey_to,
        sp=suggested_params,
    )


def sign_multisig_transaction(
    self,
    txn: MultisigTransaction,
    account: Address | None = None,
) -> MultisigTransaction:
    """
    :param account: If None, then any multisig public keys contained by the wallet will sign the transaction.

    Notes
    -----
    - Rekeyed accounts are not taken into consideration when signing multisig transaction. For example,
      if a multisig contains an account that has been rekeyed, the account is still required to sign the
      multisig txn, i.e., not the account that it has been rekeyed to.


    :return: multisig txn with added signatures
    """
    multisig = self.export_multisig(txn.multisig.address())
    if multisig is None:
        raise ValueError("multisig not found")

    if account is not None:
        if account not in multisig.get_public_keys():
            raise ValueError(
                f"multisig ({txn.multisig.address()}) does not contain account {account}"
            )
        if not self.contains_key(account):
            raise ValueError(f"wallet does not contain account: {account}")
        return self._wallet.sign_multisig_transaction(account, txn)

    for account in multisig.get_public_keys():
        if self.contains_key(account):
            txn = self._wallet.sign_multisig_transaction(account, txn)

    return txn


def get_algo_balance(address: Address, algod_client: AlgodClient) -> MicroAlgos:
    """
    Returns the authorized signing account for the specified address. This only applies to rekeyed acccounts.
    If the account is not rekeyed, then the account is the authorized account, i.e., the account signs for itself.
    """

    try:
        account_info = cast(
            dict[str, Any],
            algod_client.account_info(address, exclude="all"),  # type: ignore
        )
    except AlgodHTTPError as err:
        if err.code == 404:
            raise AccountDoesNotExist from err
        raise

    return MicroAlgos(account_info["amount"])


def get_sandbox_accounts() -> list[SandboxAccount]:
    def key(account: SandboxAccount) -> int:
        return get_algo_balance(Address(account.address), sandbox.get_algod_client())

    return sorted(
        sandbox.get_accounts(),
        key=key,
    )


class KmdMultisigRekeyTestCase(unittest.TestCase):
    """
    https://github.com/algorand/py-algorand-sdk/issues/458
    """

    kmd_client: Final[kmd.KMDClient] = sandbox.kmd.get_client()
    algod_client: Final[AlgodClient] = sandbox.get_algod_client()
    sandbox_default_wallet: Final[Wallet] = get_sandbox_default_wallet()

    def test_multisig_rekeying(self):
        """
        1. create multisig_1
        2. import multisig_1 into KMD wallet
        3. fund multisig_1
        4. create multisig_2
        5. import multisig_2 into KMD wallet
        6. rekey multisig_1 -> multisig_2
        7. rekey back to multisig_1
        """
        funding_account = get_sandbox_accounts().pop()
        wallet_name = wallet_password = str(ULID())
        self.kmd_client.create_wallet(wallet_name, wallet_password)
        account_1 = sandbox.add_account(
            generate_account()[0],
            wallet_name=wallet_name,
            wallet_password=wallet_password,
        )
        account_2 = sandbox.add_account(
            generate_account()[0],
            wallet_name=wallet_name,
            wallet_password=wallet_password,
        )
        account_3 = sandbox.add_account(
            generate_account()[0],
            wallet_name=wallet_name,
            wallet_password=wallet_password,
        )

        multisig_1 = Multisig(
            version=1,
            threshold=2,
            addresses=[
                account_1,
                account_2,
            ],
        )
        if multisig_1.address() not in self.sandbox_default_wallet.list_multisig():
            with wallet_handle_by_name(
                self.kmd_client, wallet_name, wallet_password
            ) as wallet_handle:
                self.kmd_client.import_multisig(wallet_handle, multisig_1)

        multisig_1_auth_address = get_auth_address(
            multisig_1.address(),
            self.algod_client,
        )
        self.assertEqual(multisig_1.address(), multisig_1_auth_address)

        # fund multisig_1 account
        txn = PaymentTxn(
            sender=funding_account.address,
            receiver=multisig_1.address(),
            amt=MicroAlgos(1 * algo),
            sp=self.algod_client.suggested_params(),
        )
        signed_txn = self.sandbox_default_wallet.sign_transaction(txn)
        txid = self.algod_client.send_transaction(signed_txn)
        wait_for_confirmation(self.algod_client, txid)

        # create and import multisig_2
        multisig_2 = Multisig(
            version=1,
            threshold=2,
            addresses=[
                account_1,
                account_3,
            ],
        )
        if multisig_2.address() not in self.sandbox_default_wallet.list_multisig():
            with wallet_handle_by_name(
                self.kmd_client, wallet_name, wallet_password
            ) as wallet_handle:
                self.kmd_client.import_multisig(wallet_handle, multisig_2)

        # rekey multisig_1 -> multisig_2
        txn = rekey(
            account=multisig_1.address(),
            rekey_to=multisig_2.address(),
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, multisig_1)
        for account in multisig_1.get_public_keys():
            with wallet_handle_by_name(
                self.kmd_client, wallet_name, wallet_password
            ) as wallet_handle:
                multisig_txn = self.kmd_client.sign_multisig_transaction(
                    wallet_handle,
                    wallet_password,
                    account,
                    multisig_txn,
                )
        txid = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txid)

        multisig_1_auth_address = get_auth_address(
            multisig_1.address(),
            self.algod_client,
        )
        self.assertEqual(multisig_2.address(), multisig_1_auth_address)

        # rekey back to self
        txn = rekey(
            account=multisig_1.address(),
            rekey_to=multisig_1.address(),
            suggested_params=self.algod_client.suggested_params(),
        )
        multisig_txn = MultisigTransaction(txn, multisig_2)

        try:
            for account in multisig_2.get_public_keys():
                # THIS SHOULD WORK BUT FAILS AND RAISES AN EXCEPTION
                with wallet_handle_by_name(
                    self.kmd_client, wallet_name, wallet_password
                ) as wallet_handle:
                    multisig_txn = self.kmd_client.sign_multisig_transaction(
                        wallet_handle,
                        wallet_password,
                        account,
                        multisig_txn,
                    )
        except KMDHTTPError as err:
            print(f"KMD failed to sign multisig transaction: {err}")
            print("falling back to explicit signing")

            for account in multisig_2.get_public_keys():
                with wallet_handle_by_name(
                    self.kmd_client, wallet_name, wallet_password
                ) as wallet_handle:
                    private_key = self.kmd_client.export_key(
                        wallet_handle, wallet_password, account
                    )
                    multisig_txn.sign(private_key)

        txid = self.algod_client.send_transaction(multisig_txn)
        wait_for_confirmation(self.algod_client, txid)

        multisig_1_auth_address = get_auth_address(
            multisig_1.address(),
            self.algod_client,
        )
        self.assertEqual(multisig_1.address(), multisig_1_auth_address)


if __name__ == "__main__":
    unittest.main()
