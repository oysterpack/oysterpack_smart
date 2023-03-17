import unittest

from beaker import sandbox


class MyTestCase(unittest.TestCase):
    def test_get_account_info_with_exclude_bool(self):
        super().skipTest(
            """
        Waiting on Algorand fix:        
        https://github.com/algorand/py-algorand-sdk/issues/448
        """
        )

        account = sandbox.get_accounts().pop()
        algod_client = sandbox.get_algod_client()

        algod_client.account_info(account.address, exclude=True)

    def test_get_account_info_with_exclude_all(self):
        account = sandbox.get_accounts().pop()
        algod_client = sandbox.get_algod_client()

        algod_client.account_info(account.address, exclude="all")


if __name__ == "__main__":
    unittest.main()
