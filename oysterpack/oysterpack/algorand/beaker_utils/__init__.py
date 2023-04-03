from algokit_utils import ApplicationSpecification
from algosdk.abi import Method
from algosdk.encoding import encode_address

from oysterpack.algorand.client.model import Address


def to_address(hex_encoded_address_bytes: str) -> Address:
    """
    Helper function to encode an address stored in the app's global state as a standard Algorand address.

    Notes
    -----
    - seller address is stored as bytes in the contract
    - beaker's ApplicationClient will return the bytes as a hex encoded string

    :param hex_encoded_address_bytes:
    :return:
    """
    return Address(encode_address(bytes.fromhex(hex_encoded_address_bytes)))


def get_app_method(app_spec: ApplicationSpecification, name: str) -> Method:
    for method in app_spec.contract.methods:
        if method.name == name:
            return method
    raise ValueError(f"invalid method name: {name}")
