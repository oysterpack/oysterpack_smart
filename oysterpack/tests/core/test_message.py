import unittest

from ulid import ULID

from oysterpack.core.message import Message


class MessageTestCase(unittest.TestCase):
    def test_to_tuple(self):
        msg = Message.create(ULID(), b"data")

        msg_tuple = msg.to_tuple()
        msg_2 = Message.from_tuple(msg_tuple)
        self.assertEqual(msg, msg_2)

    def test_pack(self):
        msg = Message.create(ULID(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
