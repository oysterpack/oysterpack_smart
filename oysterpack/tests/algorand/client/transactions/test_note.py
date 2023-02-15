import unittest

from beaker.application import get_method_signature

from oysterpack.algorand.client.transactions.note import AppTxnNote
from oysterpack.apps.auction_app.contracts.auction import Auction


class AppTxnNoteCase(unittest.TestCase):
    def test_encode_decode(self):
        note = AppTxnNote(
            app_name=Auction.APP_NAME,
            method_signature=get_method_signature(Auction.set_bid_asset),
        )
        encoded_note = note.encode()
        decoded_note = AppTxnNote.decode(encoded_note)
        self.assertEqual(note, decoded_note)

    def test_bytes(self):
        note = AppTxnNote(
            app_name=Auction.APP_NAME,
            method_signature=get_method_signature(Auction.set_bid_asset),
        )
        encoded_note = bytes(note)
        decoded_note = AppTxnNote.decode(encoded_note)
        self.assertEqual(note, decoded_note)


if __name__ == "__main__":
    unittest.main()
