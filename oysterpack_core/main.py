# temporary scratch file

import os
from pprint import pprint

from algosdk import kmd, wallet

from oysterpack.algorand.accounts.kmd import WalletSession, WalletName, WalletPassword

# sandbox
kmd_token = os.environ.setdefault('KMD_TOKEN', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
kmd_address = os.environ.setdefault('KMD_ADDRESS', 'http://127.0.0.1:4002')

# create a kmd client
kcl = kmd.KMDClient(kmd_token, kmd_address)
wallets = kcl.list_wallets()
pprint(wallets)

import getpass

wallet_name = input('Enter wallet name:')
wallet_pswd = getpass.getpass('Enter password:')
_wallet = wallet.Wallet(wallet_name=wallet_name, wallet_pswd=wallet_pswd, kmd_client=kcl)
print(_wallet.list_keys())

wallet_session = WalletSession(kcl, WalletName(wallet_name), WalletPassword(wallet_pswd))
