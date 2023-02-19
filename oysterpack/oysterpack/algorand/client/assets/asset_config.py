"""
Asset Config
"""
from dataclasses import dataclass
from typing import Any, Optional

from algosdk.error import AlgodHTTPError
from algosdk.transaction import AssetConfigTxn
from algosdk.v2client.algod import AlgodClient

from oysterpack.algorand.client.model import AssetId, Address

AssetConfigTxn


@dataclass(slots=True)
class AssetConfig:
    id: AssetId
    creator: Address
    total: int
    decimals: int
    default_frozen: bool | None
    unit_name: str | None
    asset_name: str | None
    manager: Address | None
    reserve: Address | None
    freeze: Address | None
    clawback: Address | None
    url: str | None
    metadata_hash: str | None

    @classmethod
    def get_asset_info(
        cls, asset_id: AssetId, algod_client: AlgodClient
    ) -> Optional["AssetConfig"]:
        """
        :return: None if the asset does not exist
        """
        try:
            asset_info = algod_client.asset_info(asset_id)
        except AlgodHTTPError as err:
            if err.code == 404:
                return None
            raise

        return cls.from_asset_info(asset_info)

    @classmethod
    def from_asset_info(cls, asset_info: dict[str, Any]) -> "AssetConfig":
        params = asset_info["params"]
        return cls(
            id=asset_info["index"],
            creator=params["creator"],
            total=params["total"],
            decimals=params["decimals"],
            default_frozen=params["default-frozen"]
            if "default-frozen" in params
            else None,
            unit_name=params["unit-name"] if "unit-name" in params else None,
            asset_name=params["name"] if "name" in params else None,
            manager=params["manager"] if "manager" in params else None,
            reserve=params["reserve"] if "reserve" in params else None,
            freeze=params["freeze"] if "freeze" in params else None,
            clawback=params["clawback"] if "clawback" in params else None,
            url=params["url"] if "url" in params else None,
            metadata_hash=params["metadata-hash"]
            if "metadata-hash" in params
            else None,
        )
