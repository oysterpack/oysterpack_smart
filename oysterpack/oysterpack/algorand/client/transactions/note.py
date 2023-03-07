"""
Provides creating standardized transaction notes.
"""
from dataclasses import dataclass


@dataclass(slots=True)
class AppTxnNote:
    """
    Application transaction note.

    Format: app/group/method
    - where group is optional
    """

    app: str
    method: str
    # used to group related methods
    group: str | None = None

    def __bytes__(self) -> bytes:
        return self.encode()

    def encode(self) -> bytes:
        """
        :returns: encoded transaction note
        """
        if self.group:
            return f"{self.app}/{self.group}/{self.method}".encode()

        return f"{self.app}/{self.method}".encode()

    @classmethod
    def decode(cls, note: bytes | str) -> "AppTxnNote":
        """
        Decodes the note into an AppTxnNote instance
        """
        decoded_note = (
            note.decode().split("/") if isinstance(note, bytes) else note.split("/")
        )
        if len(decoded_note) == 2:
            return AppTxnNote(
                app=decoded_note[0],
                method=decoded_note[1],
            )

        return AppTxnNote(
            app=decoded_note[0],
            group=decoded_note[1],
            method=decoded_note[2],
        )
