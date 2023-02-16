"""
Provides creating standardized transaction notes.
"""
from dataclasses import dataclass


@dataclass(slots=True)
class AppTxnNote:
    """
    Application transaction note
    """

    app: str
    method: str

    def __bytes__(self) -> bytes:
        return self.encode()

    def encode(self) -> bytes:
        """
        Returns the encoded transaction note using the following format:
        >>> f"{self.app}/{self.method}"
        """
        return f"{self.app}/{self.method}".encode()

    @classmethod
    def decode(cls, note: bytes) -> "AppTxnNote":
        """
        Decodes the note into an AppTxnNote instance
        """
        decoded_note = note.decode().split("/")
        return AppTxnNote(
            app=decoded_note[0],
            method=decoded_note[1],
        )
