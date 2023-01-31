from base64 import b64encode, b64decode

import algosdk


def base64_encode_arg(arg: bytes | bytearray | str | int) -> bytes:
    """
    Encodes an argument for an application call
    """
    return b64encode(algosdk.encoding.encode_as_bytes(arg))


def base64_decode_int_arg(arg: str | bytes) -> int:
    """
    Decodes an int arg that was encoded for an application call.
    """
    return int.from_bytes(b64decode(arg))


def base64_decode_str_arg(arg: str | bytes) -> str:
    """
    Decodes a str arg that was encoded for an application call.
    """
    return b64decode(arg).decode()
