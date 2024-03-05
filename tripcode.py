import hashlib


def generate_tripcode(ip_address):
    # Simple hashing using SHA-256 for illustration purposes
    hashed_ip = hashlib.sha256(ip_address.encode()).hexdigest()

    # Use the first 8 characters of the uppercase hash as the tripcode
    return hashed_ip[:8].upper()
