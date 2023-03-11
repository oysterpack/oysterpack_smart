import unittest

from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.apps.auction_app.contracts import auction


class AppTxnNoteCase(unittest.TestCase):
    def test_encode_decode(self):
        note = AppTxnNote(
            app=auction.APP_NAME,
            method=auction.set_bid_asset.method_signature(),
        )
        encoded_note = note.encode()
        decoded_note = AppTxnNote.decode(encoded_note)
        self.assertEqual(note, decoded_note)

    def test_bytes(self):
        note = AppTxnNote(
            app=auction.APP_NAME,
            method=auction.set_bid_asset.method_signature(),
        )
        encoded_note = bytes(note)
        decoded_note = AppTxnNote.decode(encoded_note)
        self.assertEqual(note, decoded_note)


if __name__ == "__main__":
    unittest.main()
