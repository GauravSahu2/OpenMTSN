import datetime
import os
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = Path("certs")
CERTS_DIR.mkdir(exist_ok=True)

def generate_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

def save_key(key, filename):
    with open(CERTS_DIR / filename, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

def save_cert(cert, filename):
    with open(CERTS_DIR / filename, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

# 1. Generate Root CA
print("Generating Root CA...")
ca_key = generate_key()
save_key(ca_key, "ca.key")

ca_subject = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "KA"),
    x509.NameAttribute(NameOID.LOCALITY_NAME, "Bengaluru"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenMTSN Root Authority"),
    x509.NameAttribute(NameOID.COMMON_NAME, "openmtsn-ca"),
])

ca_cert = (
    x509.CertificateBuilder()
    .subject_name(ca_subject)
    .issuer_name(ca_subject)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(ca_key, hashes.SHA256())
)
save_cert(ca_cert, "ca.crt")

# 2. Generate Server Certificate
print("Generating Server certificate...")
server_key = generate_key()
save_key(server_key, "server.key")

server_subject = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "api.mtsn.local"),
])

server_cert = (
    x509.CertificateBuilder()
    .subject_name(server_subject)
    .issuer_name(ca_subject)
    .public_key(server_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("api.mtsn.local"),
            x509.DNSName("localhost"),
            x509.DNSName("api"),
        ]),
        critical=False,
    )
    .sign(ca_key, hashes.SHA256())
)
save_cert(server_cert, "server.crt")

# 3. Generate Client Certificates
def generate_client_cert(name):
    print(f"Generating Client certificate for {name}...")
    key = generate_key()
    save_key(key, f"{name}.key")
    
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenMTSN Nodes"),
        x509.NameAttribute(NameOID.COMMON_NAME, name),
    ])
    
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )
    save_cert(cert, f"{name}.crt")

for node in ["node-alpha", "node-beta", "node-gamma", "dashboard"]:
    generate_client_cert(node)

print(f"Success! Certificates generated in {CERTS_DIR.absolute()}")
