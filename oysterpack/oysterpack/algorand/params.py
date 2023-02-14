"""
Algorand protocol parameters

https://developer.algorand.org/docs/get-details/parameter_tables/
"""

from typing import Final

from beaker.consts import algo


# TODO: we need a better way to lookup these params vs hard coding them
class MinimumBalance:
    # pylint: disable=too-few-public-methods

    """
    Algorand account minimum balance requirements.

    https://developer.algorand.org/docs/get-details/parameter_tables/
    """
    ASSET_OPT_IN: Final[int] = int(0.1 * algo)
