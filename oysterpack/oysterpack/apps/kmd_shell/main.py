"""
Algorand KMD shell
"""
# Append the project root to the python path
import sys
from pathlib import Path

path_root = Path(__file__).parents[3]
sys.path.append(str(path_root))
# END - Append the project root to the python path

import json
from pathlib import Path

import click
from click_shell import shell  # type: ignore

from oysterpack.algorand.client.accounts import kmd, get_auth_address
from oysterpack.apps.kmd_shell.app import App
from oysterpack.algorand.client.model import Address

__app: App | None = None
__config_file: Path | None = None


class WalletNotConnected(Exception):
    def __init__(self):
        super().__init__("No wallet is connect. Please run 'connect-wallet'")


class AppNotInitialized(Exception):
    pass


def check_wallet_connection():
    if __app.wallet_session is None:  # type: ignore
        raise WalletNotConnected


@shell(
    prompt="oysterpack-kmd > ",
    intro="Algorand KMD Shell",
)
@click.argument(
    "config-file",
    type=click.Path(exists=True, resolve_path=True, readable=True, path_type=Path),
)
def app(config_file: Path | None = None):
    if config_file is None:
        return

    click.echo(f"Config File: {config_file.absolute()}")

    global __app
    global __config_file

    __app = App.from_config_file(config_file)
    __config_file = config_file


@app.command
def show_config():
    click.echo(__config_file)
    click.echo(json.dumps(__app.config, indent=3))  # type: ignore


@app.command
def list_wallets():
    for wallet in kmd.list_wallets(__app.kmd_client):  # type: ignore
        click.echo(wallet)


@app.command
@click.option("--name", required=True, prompt="wallet name")
@click.password_option(prompt="wallet password")
def connect_wallet(name: str, password: str):
    if __app is None:
        raise AppNotInitialized
    __app.connect_wallet(name.strip(), password.strip())  # type: ignore


@app.command
def connected_wallet():
    check_wallet_connection()

    click.echo(__app.wallet_session.name)  # type: ignore


@app.command
def list_accounts():
    check_wallet_connection()

    for account in __app.wallet_session.list_keys():  # type: ignore
        click.echo(account)


@app.command
@click.option("--account", required=True, prompt="From")
@click.option("--to", required=True, prompt="To")
@click.confirmation_option(prompt="Are you sure you want to rekey?")
def rekey(account: Address, to: Address):
    check_wallet_connection()

    click.echo("Are you sure you want to rekey:")
    click.echo(f"{account} -> {to}")

    __app.wallet_session.rekey(account, to, __app.algod_client)  # type: ignore
    click.echo("Account has been successfully rekeyed:")
    click.echo(f"{account} -> {to}")


@app.command
@click.option("--account", required=True, prompt="From")
def rekey_back(account: Address):
    check_wallet_connection()

    __app.wallet_session.rekey_back(account, __app.algod_client)  # type: ignore


@app.command
@click.option("--account", required=True, prompt="Account")
def get_auth_account(account: Address):
    auth_address = get_auth_address(address=account, algod_client=__app.algod_client)  # type: ignore
    click.echo(f"Authorized Account: {auth_address}")
    click.echo("Account has been successfully rekeyed back.")


@app.command
def generate_account():
    check_wallet_connection()
    address = __app.wallet_session.generate_key()  # type: ignore
    click.echo(address)


if __name__ == "__main__":
    app()
