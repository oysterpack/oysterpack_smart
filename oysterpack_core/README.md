Python Installation Notes
-------------------------
## How to support sqlite3
```shell
sudo apt install libsqlite3-dev
# cd to python source directory
./configure --enable-loadable-sqlite-extensions
make
make test
sudo make install
```
