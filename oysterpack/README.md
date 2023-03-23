Developer Workspace Setup
--------------------------

1. Ensure python installation supports sqlite3 extensions

How to build python with sqlite support:

```shell
sudo apt install libsqlite3-dev
# cd to python source directory
./configure --enable-loadable-sqlite-extensions --enable-optimizations
make
make test
sudo make install
```

Algorand
--------
- [AlgoNode](https://algonode.io/api/)
  - provides algod and indexer hosting services
    - free tier provides 50 req/s per IP (6000 req/s globally
- [PyWalletConnect](https://pypi.org/project/pyWalletConnect)


RX
--
- https://rxmarbles.com/

TLS
---
- https://www.golinuxcloud.com/mutual-tls-authentication-mtls/

Async Logging
-------------
- https://www.zopatista.com/python/2019/05/11/asyncio-logging/

Local Secret Storage
--------------------
- https://secretstorage.readthedocs.io/en/latest/index.html
  - https://wiki.gnome.org/Projects/GnomeKeyring/