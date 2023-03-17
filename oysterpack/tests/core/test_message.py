import unittest

from oysterpack.core.message import Message, MessageType


class MessageTestCase(unittest.TestCase):
    def test_pack(self):
        msg = Message.create(MessageType(), b"data")

        packed_msg = msg.pack()
        msg_2 = Message.unpack(packed_msg)
        self.assertEqual(msg, msg_2)


if __name__ == "__main__":
    unittest.main()
