"""
Provides creating standardized transaction notes.
"""
from dataclasses import dataclass


@dataclass(slots=True)
class AppTxnNote:
    """
    Application transaction note
    """

    app_name: str
    method_signature: str

    def __bytes__(self) -> bytes:
        return self.encode()

    def encode(self) -> bytes:
        """
        Returns the encoded transaction note using the following format:
        >>> f"{self.app_name}/{self.method_signature}"
        """
        return f"{self.app_name}/{self.method_signature}".encode()

    @classmethod
    def decode(cls, note: bytes) -> "AppTxnNote":
        """
        Decodes the note into an AppTxnNote instance
        """
        decoded_note = note.decode().split("/")
        return AppTxnNote(
            app_name=decoded_note[0],
            method_signature=decoded_note[1],
        )
