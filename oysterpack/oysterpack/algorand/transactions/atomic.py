from algosdk.atomic_transaction_composer import TransactionSigner
from algosdk.transaction import Transaction, SignedTransaction

from oysterpack.algorand.accounts.kmd import WalletSession


class WalletTransactionSigner(TransactionSigner):
    """
    Signs the transaction using a KMD wallet session
    """

    def __init__(self, wallet: WalletSession):
        self.__wallet = wallet

    def sign_transactions(self, txn_group: list[Transaction], indexes: list[int]) -> list[SignedTransaction]:
        """

        :param txn_group:
        :param indexes: array of indexes in the atomic transaction group that should be signed
        :return:
        """

        return [self.__wallet.sign_transaction(txn_group[i]) for i in indexes]
