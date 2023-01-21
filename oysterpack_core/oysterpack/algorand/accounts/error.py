from urllib.error import URLError

from algosdk.error import KMDHTTPError


class WalletAlreadyExistsError(Exception): pass


class WalletDoesNotExistError(Exception): pass


class KmdClientError(Exception):
    """KMD client base exception"""


class InvalidKmdTokenError(KmdClientError): pass


class KmdUrlError(KmdClientError): pass


class WalletSessionError(Exception):
    """Base exception class for WalletSession errors"""


class InvalidWalletPasswordError(WalletSessionError): pass


class DuplicateWalletNameError(WalletSessionError): pass


class KeyNotFoundError(WalletSessionError): pass


def handle_kmd_client_errors(command):
    """
    Decorator function that is used to handle the below exceptions by trying to map them to KmdClientError exceptions.
    If the exceptions cannot be mapped, then they are simply re-raised.

    - algosdk.error.KMDHTTPError
        - if the error was caused by an invalid token, then an InvalidKmdTokenError is raised.
        - If the HTTP error was a 'Not Found', then an InvalidKmdUrlError is raised
        - Otherwise the exception is re-raised
    - urllib.error.URLError - raises an InvalidKmdUrlError
    """

    def wrapped_command(*args, **kwargs):
        try:
            # check the KMD client connection by retrieving the list of wallets from the KMD server
            return command(*args, **kwargs)
        except KMDHTTPError as err:
            if 'invalid API token' in str(err):
                raise InvalidKmdTokenError() from err
            if 'key does not exist in this wallet' in str(err):
                raise KeyNotFoundError() from err
            if 'Not Found' in str(err):
                raise KmdUrlError() from err
            raise
        except URLError as err:
            raise KmdUrlError() from err
        except ValueError as err:
            if 'unknown url type' in str(err):
                raise KmdUrlError() from err
            raise

    return wrapped_command
