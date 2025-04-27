# common/utils/cache.py
import json
import redis
import hashlib
import logging
from functools import wraps
from common.config import REDIS_URL

logger = logging.getLogger(__name__)

# Create a Redis client instance
redis_client = redis.from_url(REDIS_URL)


# Standardized TTL values based on data access patterns
class CacheTTL:
    """Standard TTL values for different types of cached data"""
    SHORT = 60  # 1 minute - for frequently changing data
    MEDIUM = 300  # 5 minutes - for semi-stable data
    STANDARD = 3600  # 1 hour - for stable data
    LONG = 86400  # 1 day - for very stable data
    EXTENDED = 604800  # 1 week - for nearly static data


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


def get_entity_cache_key(entity_type, entity_id, suffix=None):
    """Generate a standardized cache key for an entity"""
    key = f"{entity_type}:{entity_id}"
    if suffix:
        key += f":{suffix}"
    return key


def redis_cache(prefix, ttl=CacheTTL.STANDARD):
    """Cache decorator that uses Redis with standardized TTL"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached = redis_client.get(key)
            if cached:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(cached)

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            if result:
                redis_client.set(key, json.dumps(result), ex=ttl)
                logger.debug(f"Cached result for key: {key} with TTL: {ttl}s")

            return result

        # Add cache invalidation method to the function
        wrapper.invalidate_cache = lambda *args, **kwargs: invalidate_cache(prefix, *args, **kwargs)

        return wrapper

    return decorator


def async_redis_cache(prefix, ttl=CacheTTL.STANDARD):
    """Cache decorator for async functions"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached = redis_client.get(key)
            if cached:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(cached)

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            if result:
                redis_client.set(key, json.dumps(result), ex=ttl)
                logger.debug(f"Cached result for key: {key} with TTL: {ttl}s")

            return result

        # Add cache invalidation method to the function
        wrapper.invalidate_cache = lambda *args, **kwargs: invalidate_cache(prefix, *args, **kwargs)

        return wrapper

    return decorator


def invalidate_cache(prefix, *args, **kwargs):
    """
    Invalidate a specific cache entry or pattern of entries

    Args:
        prefix: Cache prefix to invalidate
        *args, **kwargs: If provided, invalidates specific key matching these args
                        If not provided, invalidates all keys with this prefix
    """
    if args or kwargs:
        # Invalidate specific key
        key = cache_key(prefix, *args, **kwargs)
        redis_client.delete(key)
        logger.debug(f"Invalidated cache key: {key}")
    else:
        # Invalidate all keys with this prefix
        pattern = f"{prefix}:*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.debug(f"Invalidated {len(keys)} cache keys with pattern: {pattern}")


def cache_warm(prefix, ttl=CacheTTL.STANDARD, data_generator=None):
    """
    Warms up cache with provided data or generator function

    Args:
        prefix: Cache prefix
        ttl: Cache TTL in seconds
        data_generator: Function that returns a dict of {key: value} pairs to cache,
                       where key is everything after the prefix in the cache key
    """
    if not data_generator:
        logger.warning("No data generator provided for cache warming")
        return

    if callable(data_generator):
        data = data_generator()
    else:
        data = data_generator

    for key_suffix, value in data.items():
        full_key = f"{prefix}:{key_suffix}"
        redis_client.set(full_key, json.dumps(value), ex=ttl)

    logger.info(f"Warmed up {len(data)} cache entries with prefix {prefix}")


def get_cached(key, default=None):
    """Get a value from cache with fallback default"""
    value = redis_client.get(key)
    if value:
        return json.loads(value)
    return default


def set_cached(key, value, ttl=CacheTTL.STANDARD):
    """Set a value in cache with standard TTL"""
    redis_client.set(key, json.dumps(value), ex=ttl)
    return value


def batch_get_cached(keys, prefix=""):
    """
    Get multiple values from cache in a single operation
    Returns a dict of {key: value} for found keys
    """
    if not keys:
        return {}

    prefixed_keys = [f"{prefix}:{k}" if prefix else k for k in keys]

    # Use Redis pipeline for batched operations
    with redis_client.pipeline() as pipe:
        for key in prefixed_keys:
            pipe.get(key)
        values = pipe.execute()

    result = {}
    for i, value in enumerate(values):
        if value:
            # Remove prefix from key if it exists
            original_key = keys[i]
            result[original_key] = json.loads(value)

    return result


def batch_set_cached(key_values, ttl=CacheTTL.STANDARD, prefix=""):
    """
    Set multiple values in cache in a single operation
    key_values: Dict of {key: value} pairs to cache
    """
    if not key_values:
        return

    # Use Redis pipeline for batched operations
    with redis_client.pipeline() as pipe:
        for key, value in key_values.items():
            full_key = f"{prefix}:{key}" if prefix else key
            pipe.set(full_key, json.dumps(value), ex=ttl)
        pipe.execute()
