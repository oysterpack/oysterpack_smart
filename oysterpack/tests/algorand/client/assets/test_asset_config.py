import unittest
from base64 import b64decode

from algosdk.account import generate_account

from oysterpack.algorand.client.assets.asset_config import AssetConfig
from oysterpack.algorand.client.model import Address
from tests.algorand.test_support import AlgorandTestCase


class AssetConfigTestCase(AlgorandTestCase):
    def test_get_asset_info(self):
        _, manager = generate_account()
        _, reserve = generate_account()
        _, freeze = generate_account()
        _, clawback = generate_account()

        def generate_metadata_hash() -> bytes:
            import hashlib

            m = hashlib.sha256()
            m.update(b"asset metadata")
            return m.digest()

        asset_id, _creator = self.create_test_asset(
            asset_name="GOLD",
            manager=Address(manager),
            reserve=Address(reserve),
            freeze=Address(freeze),
            clawback=Address(clawback),
            unit_name="g",
            url="http://meld.gold.com",
            metadata_hash=generate_metadata_hash(),
        )

        asset_config = AssetConfig.get_asset_info(asset_id, self.algod_client)
        self.assertEqual(asset_id, asset_config.id)
        self.assertEqual("GOLD", asset_config.asset_name)
        self.assertEqual(manager, asset_config.manager)
        self.assertEqual(reserve, asset_config.reserve)
        self.assertEqual(freeze, asset_config.freeze)
        self.assertEqual(clawback, asset_config.clawback)
        self.assertEqual("g", asset_config.unit_name)
        self.assertEqual("http://meld.gold.com", asset_config.url)
        self.assertEqual(
            generate_metadata_hash(), b64decode(asset_config.metadata_hash)
        )


if __name__ == "__main__":
    unittest.main()
