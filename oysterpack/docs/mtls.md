TLS
---
https://www.golinuxcloud.com/mutual-tls-authentication-mtls/

```shell
# create private key
openssl genrsa -out private/cakey.pem 4096

# Create CA certificate
openssl req -new -x509 -days 3650 -config openssl.cnf -key private/cakey.pem -out certs/cacert.pem

# Convert certificate to PEM format
openssl x509 -in certs/cacert.pem -out certs/cacert.pem -outform PEM

# Create client certificate
openssl genrsa -out client_certs/client.key.pem 4096
openssl req -new -key client_certs/client.key.pem -out client_certs/client.csr -config openssl.cnf
openssl ca -config openssl.cnf -extfile client_certs/client_ext.cnf -days 1650 -notext -batch -in client_certs/client.csr -out client_certs/client.cert.pem

# Create server certificates
openssl genrsa -out server_certs/server.key.pem 4096
openssl req -new -key server_certs/server.key.pem -out server_certs/server.csr -config openssl.cnf
openssl ca -config openssl.cnf -extfile server_certs/server_ext.cnf -days 1650 -notext -batch -in server_certs/server.csr -out server_certs/server.cert.pem
```