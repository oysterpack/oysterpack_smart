import unittest

from ulid import ULID

from oysterpack.core.message import Message


class MessageTestCase(unittest.TestCase):
    def test_pack(self):
        msg = Message.create(ULID(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
