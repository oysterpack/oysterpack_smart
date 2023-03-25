"""
MultisigService Protocol
"""
from dataclasses import dataclass
from typing import Protocol

from oysterpack.algorand.client.model import MicroAlgos, Address


@dataclass(slots=True)
class ServiceFee:
    """
    ServiceFee PaymentTxn settings
    """

    amount: MicroAlgos
    pay_to: Address
    description: str


class MultisigService(Protocol):
    """
    MultisigService
    """

    async def service_fee(self) -> ServiceFee:
        """
        :return: ServiceFee
        """
        ...
