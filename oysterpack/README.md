Developer Workspace Setup
--------------------------

1. Ensure python installation supports sqlite3

How to build and python with sqlite support:

```shell
sudo apt install libsqlite3-dev
# cd to python source directory
./configure --enable-loadable-sqlite-extensions
make
make test
sudo make install
```
