"""
Algorand KMD shell
"""
import json
from builtins import enumerate
from pathlib import Path

import click
from click_shell import shell  # type: ignore

from oysterpack.algorand.client.accounts.kmd import WalletName, WalletPassword
from oysterpack.algorand.client.model import Address, MicroAlgos
from oysterpack.apps.kmd_shell.app import App, WalletNotConnected

__app: App | None = None
__config_file: Path | None = None


class AppNotInitialized(Exception):
    pass


@shell(
    prompt="oysterpack-kmd > ",
    intro="Algorand KMD Shell",
)
@click.option(
    "--config-file",
    required=True,
    prompt="Config File",
    type=click.Path(exists=True, resolve_path=True, readable=True, path_type=Path),
)
def app(config_file: Path | None = None):
    if config_file is None:
        return

    global __app
    global __config_file

    __app = App.from_config_file(config_file)
    __config_file = config_file


@app.command
def show_config():
    """
    Displays the application config as JSON
    """

    if __app is None:
        raise AppNotInitialized

    click.echo(__config_file)
    click.echo(json.dumps(__app.config, indent=3))


@app.command
def list_wallets():
    """
    List KMD wallets
    """

    if __app is None:
        raise AppNotInitialized

    for wallet in __app.list_wallets():
        click.echo(wallet)


@app.command
@click.option("--name", required=True, prompt="Wallet Name", help="Wallet name")
@click.password_option(prompt="Wallet Password", help="Wallet password")
def connect_wallet(name: str, password: str):
    """
    Connects to a KMD wallet.
    """

    if __app is None:
        raise AppNotInitialized

    __app.connect_wallet(
        WalletName(name.strip()),
        WalletPassword(password.strip()),
    )


@app.command
@click.option("--name", required=True, prompt="Wallet Name", help="Wallet name")
@click.password_option(prompt="Wallet Password", help="Wallet password")
@click.option(
    "--account", required=True, prompt="Account", help="Algorand account address"
)
def export_key(name: WalletName, password: WalletPassword, account: Address):
    """
    Exports wallet account key mnemonic
    """

    if __app is None:
        raise AppNotInitialized

    mnemonic = __app.export_key(
        WalletName(name.strip()), WalletPassword(password.strip()), account
    )
    click.echo(mnemonic)
    click.echo("-" * len(str(mnemonic)))
    for i, word in enumerate(mnemonic.word_list, start=1):
        click.echo(f"{i} : {word}")


@app.command
def disconnect_wallet():
    """
    Closes any connected wallet session.
    """
    if __app is None:
        raise AppNotInitialized

    __app.disconnect_wallet()


@app.command
def connected_wallet():
    """
    Displays the wallet name for the current connected wallet session.
    """
    if __app is None:
        raise AppNotInitialized

    wallet_name = __app.connected_wallet
    if wallet_name is None:
        raise WalletNotConnected

    click.echo(wallet_name)


@app.command
def list_accounts():
    """
    Lists the accounts for the current connected wallet session.
    """

    if __app is None:
        raise AppNotInitialized

    for account in __app.list_wallet_accounts():
        click.echo(account)


@app.command
@click.option(
    "--account", required=True, prompt="From", help="Algorand account to rekey"
)
@click.option("--to", required=True, prompt="To", help="Algorand account rekey target")
def rekey(account: Address, to: Address):
    """
    Rekeys a wallet account to another account in the same wallet.
    Both accounts must exist in the current connected wallet session.
    """
    if __app is None:
        raise AppNotInitialized

    if click.confirm("Please confirm to rekey the account"):
        txid = __app.rekey(
            Address(str(account.strip())),
            Address(str(to).strip()),
        )
        click.echo("Account has been successfully rekeyed:")
        click.echo(f"{account} -> {to}")
        click.echo(f"Transaction ID: {txid}")
    else:
        click.echo("Rekeying has been cancelled")


@app.command
@click.option("--account", required=True, prompt=True, help="Algorand account")
def rekey_back(account: Address):
    """
    Rekeys the account back to itself.
    The account and its authorized account must both exist in the current connected wallet session.
    """

    if __app is None:
        raise AppNotInitialized

    txid = __app.rekey_back(Address(str(account.strip())))
    click.echo("Account has been successfully rekeyed back.")
    click.echo(f"Transaction ID: {txid}")


@app.command
def get_rekeyed_accounts():
    """
    Returns list of accounts that have been rekeyed in the current connected wallet session
    """

    if __app is None:
        raise AppNotInitialized

    rekeyed_accounts = __app.get_rekeyed_accounts()
    if len(rekeyed_accounts) == 0:
        click.echo("There are no rekeyed accounts")
    else:
        click.echo("Account -> Authorized Account")
        click.echo("-----------------------------")
        for account, auth_account in rekeyed_accounts.items():
            click.echo(f"{account} -> {auth_account}")


@app.command
@click.option("--account", required=True, prompt="Account", help="Algorand account")
def get_auth_account(account: Address):
    """
    Returns the account's authorized account.
    The authorized account is the account that controls the underlying account.
    The authorized account is used to sign transaction for the underlying account.
    Rekeying an account is the mechanism used to transfer the account's authorization to another account.
    """

    if __app is None:
        raise AppNotInitialized

    auth_address = __app.get_auth_address(account)
    click.echo(f"Authorized Account: {auth_address}")
    if auth_address == account:
        click.echo("This account is NOT rekeyed.")
    else:
        click.echo("This account is rekeyed.")


@app.command
@click.option("--account", required=True, prompt="Account", help="Algorand account")
@click.option(
    "--summary",
    default=True,
    prompt="Summary",
    help="Summary excludes app and asset details",
)
def get_account_info(account: Address, summary: bool):
    """
    Returns the Algorand account information.
    """
    if __app is None:
        raise AppNotInitialized

    account_info = __app.get_account_info(account, summary=summary)
    click.echo(json.dumps(account_info, indent=3))


@app.command
def generate_account():
    """
    Generates a new account in the current connected wallet session.
    """
    if __app is None:
        raise AppNotInitialized

    if __app.connected_wallet is None:
        raise WalletNotConnected

    click.echo(f"Current connected wallet: {__app.connected_wallet}")
    if click.confirm("Please confirm account generation for the above wallet"):
        address = __app.generate_wallet_account()
        click.echo(address)
    else:
        click.echo("Account generation has been cancelled")


@app.command
@click.option("--wallet-name", required=True, prompt="Wallet Name", help="Wallet name")
@click.password_option(
    "--wallet-password", prompt="Wallet Password", help="Wallet password"
)
@click.option(
    "--sender", required=True, prompt="Sender Account", help="Sender Algorand account"
)
@click.option(
    "--receiver",
    required=True,
    prompt="Receiver Account",
    help="Receiver Algorand account",
)
@click.option(
    "--amount",
    required=True,
    prompt="Amount (microalgos)",
    help="ALGO amount in microalgos",
    type=click.INT,
)
@click.option("--note", help="Transaction note")
def transfer_algo(
    wallet_name: WalletName,
    wallet_password: WalletPassword,
    sender: Address,
    receiver: Address,
    amount: MicroAlgos,
    note: str | None,
):
    if __app is None:
        raise AppNotInitialized

    if click.confirm("Please confirm the above ALGO transfer"):
        txid = __app.transfer_algo(
            wallet_name=WalletName(str(wallet_name).strip()),
            wallet_password=WalletPassword(str(wallet_password).strip()),
            sender=sender,
            receiver=receiver,
            amount=amount,
            note=note,
        )
        click.echo("ALGO transfer was successful.")
        click.echo(f"Transaction ID: {txid}")
    else:
        click.echo("ALGO transfer has been cancelled.")


if __name__ == "__main__":
    app()
