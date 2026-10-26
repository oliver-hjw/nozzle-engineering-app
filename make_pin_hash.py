import getpass, hashlib
pin=getpass.getpass('PIN: ')
print(hashlib.sha256(pin.encode('utf-8')).hexdigest())
