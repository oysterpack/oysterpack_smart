## Algorand Node Installation
After installing via the debian package installer, the node was failing to start up.
When the node starts up it was looking for a `genesis.json` file in the $ALGORAND_DATA directory.
The file was missing, but genesis config files are located in the $ALGORAND_DATA/genesis directory.
The solution is to copy over the file for the desired environment:
```shell
cp $ALGORAND_DATA/genesis/mainnet/genesis.json $ALGORAND_DATA/
```

## Development tools for Algorand
- https://dappflow.org/

## Useful goal commands

### Watch algod node status
```shell
sudo -u algorand goal -d $ALGORAND_DATA node status -w 1000
```

### KMD commands
```shell
# start KMD
sudo -u algorand goal -d $ALGORAND_DATA kmd start

# stop KMD
sudo -u algorand goal -d $ALGORAND_DATA kmd stop
```