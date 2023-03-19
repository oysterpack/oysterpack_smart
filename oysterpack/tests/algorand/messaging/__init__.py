import pathlib
import ssl
from ssl import SSLContext


def server_ssl_context() -> SSLContext:
    ssl_context = SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_cert_pem = pathlib.Path(__file__).with_name("server.cert.pem")
    server_key_pem = pathlib.Path(__file__).with_name("server.key.pem")
    ssl_context.load_cert_chain(server_cert_pem, server_key_pem)
    return ssl_context


def client_ssl_context() -> SSLContext:
    ssl_context = SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cacert_pem = pathlib.Path(__file__).with_name("cacert.pem")
    ssl_context.load_verify_locations(cacert_pem)
    ssl_context.check_hostname = False
    return ssl_context
