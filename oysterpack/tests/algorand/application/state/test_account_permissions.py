import unittest
from typing import Final

import algosdk.error
from beaker import Application, Authorize, sandbox
from beaker.client import ApplicationClient
from beaker.decorators import external, opt_in, delete
from beaker.sandbox.kmd import SandboxAccount
from pyteal import Global, Expr, Seq, Approve, App, If, Int
from pyteal.ast import abi

from oysterpack.algorand.application.state.account_permissions import (
    AccountPermissions,
)
from oysterpack.algorand.application.state.bitset import decode_bit_mask


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
        account_permissions = self.account_permissions[account.address()]
        return Seq(
            account_permissions.revoke(permissions),
            output.set(account_permissions.get()),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def revoke_all(self, account: abi.Account) -> Expr:
        return self.account_permissions[account.address()].revoke_all()

    @external(read_only=True)
    def contains(
        self, account: abi.Account, permissions: abi.Uint64, *, output: abi.Bool
    ) -> Expr:
        return output.set(
            If(
                App.optedIn(account.address(), Global.current_application_id()),
                self.account_permissions[account.address()].contains(permissions),
                Int(0),
            )
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

        # optin the accounts
        cls.owner_client.opt_in()
        cls.user_client.opt_in()

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
            AccountPermissionsManager.contains, account=address, permissions=self.PERM_0
        )
        print(result.decode_error)
        self.assertEqual(result.return_value, False)

    def test_permissions(self):
        with self.subTest("grant permissions"):
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

            with self.subTest("revoke permission"):
                result = self.owner_client.call(
                    AccountPermissionsManager.revoke,
                    account=self.user.address,
                    permissions=self.PERM_0,
                )
                self.assertEqual(result.return_value, self.PERM_1)

            with self.subTest("revoke all permissions"):
                result = self.owner_client.call(
                    AccountPermissionsManager.grant,
                    account=self.user.address,
                    permissions=self.PERM_2,
                )
                self.assertTrue(result.return_value > 0)

                self.owner_client.call(
                    AccountPermissionsManager.revoke_all,
                    account=self.user.address,
                )
                account_app_info = self.user_client.get_account_state()
                # assert that the user has no permissions set
                self.assertEqual(account_app_info["account_permissions"], 0)

    def test_with_negative_permission(self):
        with self.assertRaises(algosdk.error.ABIEncodingError) as err:
            self.owner_client.call(
                AccountPermissionsManager.grant,
                account=self.user.address,
                permissions=-1,
            )
        self.assertTrue("value -1 is not a non-negative int" in str(err.exception))

    def test_with_zero_permission(self):
        self.owner_client.call(
            AccountPermissionsManager.revoke_all,
            account=self.user.address,
        )
        self.owner_client.call(
            AccountPermissionsManager.grant,
            account=self.user.address,
            permissions=self.PERM_0 | self.PERM_63,
        )
        result = self.owner_client.call(
            AccountPermissionsManager.grant,
            account=self.user.address,
            permissions=0,
        )
        self.assertEqual(result.return_value, self.PERM_0 | self.PERM_63)


class HelperFunctionsTestCast(unittest.TestCase):
    def test_decode_permissions(self):
        self.assertEqual(set(), decode_bit_mask(0))
        self.assertEqual({0}, decode_bit_mask(0 | 1))
        self.assertEqual({0, 1, 2, 4}, decode_bit_mask(0 | 1 | 23))
        self.assertEqual({0, 1, 2, 3, 4, 5}, decode_bit_mask(0 | 1 | 23 | 63))

        with self.assertRaises(AssertionError):
            decode_bit_mask(-1)

        with self.assertRaises(AssertionError):
            decode_bit_mask(1 << 63 + 1)


if __name__ == "__main__":
    unittest.main()
