import unittest
from pprint import pprint
from typing import Final

from beaker import (
    LocalStateValue,
    Application,
    unconditional_opt_in_approval,
    unconditional_create_approval,
)
from beaker.client import ApplicationClient
from beaker.consts import algo
from pyteal import TealType, Int, Seq, If, Not, App, Global
from pyteal.ast import abi

from oysterpack.algorand.application.transactions.application import execute_optin_app
from oysterpack.algorand.client.transactions import suggested_params_with_flat_flee
from tests.algorand.test_support import AlgorandTestCase


class FooState:
    counter: Final[LocalStateValue] = LocalStateValue(
        stack_type=TealType.uint64, default=Int(0)
    )


foo = Application("Foo", state=FooState())
foo.apply(unconditional_create_approval)
foo.apply(unconditional_opt_in_approval, initialize_local_state=True)

bar = Application("Bar")


@bar.external
def optin_app(app: abi.Application):
    return Seq(
        If(
            Not(
                App.optedIn(Global.current_application_address(), app.application_id())
            ),
            execute_optin_app(app.application_id()),
        )
    )


class OptinTestCase(AlgorandTestCase):
    def test_optin(self):
        account = self.get_sandbox_accounts().pop()
        foo_client = ApplicationClient(
            self.algod_client,
            app=foo,
            sender=account.address,
            signer=account.signer,
        )
        foo_app_id, _foo_app_addr, _txid = foo_client.create()

        bar_client = ApplicationClient(
            self.algod_client,
            app=bar,
            sender=account.address,
            signer=account.signer,
        )
        _bar_app_id, bar_app_addr, _txid = bar_client.create()
        bar_client.fund(1 * algo)
        bar_client.call(
            optin_app.method_signature(),
            app=foo_app_id,
            suggested_params=suggested_params_with_flat_flee(
                self.algod_client, txn_count=2
            ),
        )
        pprint(self.algod_client.account_application_info(bar_app_addr, foo_app_id))


if __name__ == "__main__":
    unittest.main()
