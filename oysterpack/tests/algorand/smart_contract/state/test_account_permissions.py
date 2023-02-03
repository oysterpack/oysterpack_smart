import unittest
from typing import Final

from beaker import Application, Authorize, sandbox
from beaker.client import ApplicationClient
from beaker.decorators import external, opt_in, delete
from beaker.sandbox.kmd import SandboxAccount
from pyteal import Global, Expr, Seq, Approve, App, If, Int
from pyteal.ast import abi

from oysterpack.algorand.smart_contract.state.account_permissions import (
    AccountPermissions,
    decode_permissions_bits,
)


class AccountPermissionsManager(Application):
    account_permissions: Final[AccountPermissions] = AccountPermissions()

    @opt_in
    def optin(self) -> Expr:
        return self.initialize_account_state()

    @external(authorize=Authorize.only(Global.creator_address()))
    def grant(
        self, account: abi.Account, permissions: abi.Uint64, *, output: abi.Uint64
    ) -> Expr:
        account_permissions = self.account_permissions[account.address()]
        return Seq(
            account_permissions.grant(permissions),
            output.set(account_permissions.get()),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def revoke(
        self, account: abi.Account, permissions: abi.Uint64, *, output: abi.Uint64
    ) -> Expr:
        return Seq(
            self.account_permissions[account.address()].revoke(permissions),
            output.set(self.account_permissions.get()),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def revoke_all(self, account: abi.Account) -> Expr:
        return self.account_permissions[account.address()].revoke_all()

    @external(read_only=True)
    def contains(
        self, account: abi.Account, permissions: abi.Uint64, *, output: abi.Bool
    ) -> Expr:
        return If(
            App.optedIn(account.address(), Global.current_application_id()),
            output.set(self.account_permissions[account.address()].contains(permissions)),
            output.set(Int(0))
        )

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self) -> Expr:
        return Approve()


class AccountPermissionsTestCase(unittest.TestCase):
    owner: SandboxAccount | None = None
    user: SandboxAccount | None = None

    owner_client: ApplicationClient | None = None
    user_client: ApplicationClient | None = None

    # permissions should be defined as constants
    PERM_0: Final[int] = 1 << 0
    PERM_1: Final[int] = 1 << 1
    PERM_2: Final[int] = 1 << 2
    PERM_63: Final[int] = 1 << 63

    @classmethod
    def setUpClass(cls) -> None:
        accounts = sandbox.get_accounts()
        cls.owner = accounts.pop()
        cls.user = accounts.pop()

        cls.owner_client = ApplicationClient(
            client=sandbox.get_algod_client(),
            sender=cls.owner.address,
            signer=cls.owner.signer,
            app=AccountPermissionsManager(),
        )

        print("created smart contract:", cls.owner_client.create())
        cls.user_client = cls.owner_client.prepare(
            sender=cls.user.address, signer=cls.user.signer
        )

        cls.owner_client.opt_in()

        print("owner:", cls.owner.address)
        print("user:", cls.user.address)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.owner_client:
            cls.owner_client.delete()

    def test_user_not_opted_in(self):
        from algosdk.account import generate_account

        _sk, address = generate_account()
        result = self.owner_client.call(
            AccountPermissionsManager.contains,
            account=address,
            permissions=self.PERM_0
        )
        print(result.decode_error)
        self.assertEqual(result.return_value, False)

    def test_permissions(self):
        with self.subTest("when user opts in, local state is initialized"):
            self.user_client.opt_in()
            account_app_info = self.user_client.client.account_application_info(
                self.user.address, self.user_client.app_id
            )
            # pp(account_app_info)
            # assert that the user has no permissions set
            self.assertEqual(
                account_app_info["app-local-state"]["key-value"][0]["value"]["uint"], 0
            )

            result = self.owner_client.call(
                AccountPermissionsManager.contains,
                account=self.user.address,
                permissions=self.PERM_0,
            )
            self.assertFalse(result.return_value)

        with self.subTest("grant opted in user permissions"):
            result = self.owner_client.call(
                AccountPermissionsManager.grant,
                account=self.user.address,
                permissions=self.PERM_0 | self.PERM_1,
            )
            account_app_info = self.user_client.client.account_application_info(
                self.user.address, self.user_client.app_id
            )
            # pp(account_app_info)
            self.assertEqual(result.return_value, self.PERM_0 | self.PERM_1)

            # check permissions
            permissions = [
                (self.PERM_0, True),
                (self.PERM_0 | self.PERM_1, True),
                (self.PERM_0 | self.PERM_1 | self.PERM_2, False),
                (self.PERM_0 | self.PERM_1 | self.PERM_2 | self.PERM_63, False),
            ]
            for perms, expected_result in permissions:
                # user's permissions can be checked by any account
                result = self.owner_client.call(
                    AccountPermissionsManager.contains,
                    account=self.user.address,
                    permissions=perms,
                )
                self.assertEqual(result.return_value, expected_result, str(perms))

                # user can check their own permissons
                result = self.user_client.call(
                    AccountPermissionsManager.contains,
                    account=self.user.address,
                    permissions=perms,
                )
                self.assertEqual(result.return_value, expected_result, str(perms))


class HelperFunctionsTestCast(unittest.TestCase):
    def test_decode_permissions(self):
        self.assertEqual(set(), decode_permissions_bits(0))
        self.assertEqual({0}, decode_permissions_bits(0 | 1))
        self.assertEqual({0, 1, 2, 4}, decode_permissions_bits(0 | 1 | 23))
        self.assertEqual({0, 1, 2, 3, 4, 5}, decode_permissions_bits(0 | 1 | 23 | 63))

        with self.assertRaises(AssertionError):
            decode_permissions_bits(-1)

        with self.assertRaises(AssertionError):
            decode_permissions_bits(1 << 63 + 1)


if __name__ == "__main__":
    unittest.main()
