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