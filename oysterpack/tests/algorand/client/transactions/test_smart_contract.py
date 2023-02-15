import base64
import unittest

from oysterpack.algorand.client.transactions.smart_contract import (
    base64_encode,
    base64_decode_int,
    base64_decode_str,
)
from tests.algorand.test_support import AlgorandTestCase


class SmartContractTestCase(AlgorandTestCase):
    def test_base64_encode_decode_arg(self):
        with self.subTest("encode str"):
            arg = "data"
            encoded_arg = base64_encode(arg)
            self.assertEqual(base64.b64decode(encoded_arg), arg.encode())
            self.assertEqual(base64.b64decode(encoded_arg).decode(), arg)
            self.assertEqual(base64_decode_str(encoded_arg), arg)

        with self.subTest("encode int"):
            arg = 10
            encoded_arg = base64_encode(arg)
            self.assertEqual(base64_decode_int(encoded_arg), arg)

        with self.subTest("encode bytes"):
            arg = b"data"
            encoded_arg = base64_encode(arg)
            self.assertEqual(base64.b64decode(encoded_arg), arg)


if __name__ == "__main__":
    unittest.main()
