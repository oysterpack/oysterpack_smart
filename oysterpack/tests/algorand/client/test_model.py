import unittest

from beaker import sandbox
from beaker.application import Application
from beaker.client import ApplicationClient

from oysterpack.algorand.client.model import AppID


class Foo(Application):
    pass


class AppIdTestCase(unittest.TestCase):
    def test_to_address(self):
        account = sandbox.get_accounts().pop()
        app_client = ApplicationClient(
            client=sandbox.get_algod_client(),
            app=Foo(),
            sender=account.address,
            signer=account.signer,
        )

        app_id, app_addess, _tx_id = app_client.create()
        app_id = AppID(app_id)
        self.assertEqual(app_id.to_address(), app_addess)


if __name__ == "__main__":
    unittest.main()
