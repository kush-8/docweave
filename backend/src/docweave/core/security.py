import hashlib, hmac


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(settings, cookie):
    return hmac.new(settings.encryption_key.encode(), ("csrf:" + cookie).encode(), hashlib.sha256).hexdigest()
