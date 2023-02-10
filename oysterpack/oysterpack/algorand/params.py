"""
Algorand protocol parameters

https://developer.algorand.org/docs/get-details/parameter_tables/
"""

from typing import Final

from beaker.consts import algo


# TODO: we need a better way to lookup these params vs hard coding them

class MinimumBalance:
    asset_opt_in: Final[int] = int(0.1 * algo)
