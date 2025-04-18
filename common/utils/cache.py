# common/utils/cache.py
import json
import redis
import hashlib
from functools import wraps
from common.config import REDIS_URL

redis_client = redis.from_url(REDIS_URL)


def cache_key(prefix, *args, **kwargs):
    """Generate a cache key from the arguments"""
    key_parts = [prefix]

    # Add positional args
    for arg in args:
        key_parts.append(str(arg))

    # Add keyword args, sorted by key
    for k in sorted(kwargs.keys()):
        key_parts.append(f"{k}:{kwargs[k]}")

    # Create hash for longer keys
    if len(":".join(key_parts)) > 200:
        return f"{prefix}:{hashlib.md5(':'.join(key_parts).encode()).hexdigest()}"

    return ":".join(key_parts)


def redis_cache(prefix, ttl=3600):
    """Cache decorator that uses Redis"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):  # Remove async here
            # Generate cache key
            key = cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)

            # Execute function
            result = func(*args, **kwargs)  # Remove await here

            # Cache result
            if result:
                redis_client.set(key, json.dumps(result), ex=ttl)

            return result

        return wrapper

    return decorator