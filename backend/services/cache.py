"""Simple in-memory caching layer for API responses.

Provides decorator-based caching with TTL support.
"""
import asyncio
import functools
import time
from typing import Any, Callable, Dict, Optional, Tuple
import hashlib
import json


class SimpleCache:
    """In-memory cache with TTL support.

    Simple cache implementation using dict storage with time-based expiration.
    """

    def __init__(self, default_ttl: int = 300) -> None:
        """Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds (default 5 minutes).
        """
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl

    def _generate_key(self, func: Callable, args: Tuple, kwargs: Dict) -> str:
        """Generate cache key from function and arguments.

        Args:
            func: Function being cached.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Cache key string.
        """
        # Convert kwargs to string representation for hashing
        # Handle non-JSON-serializable types like date objects
        kwargs_str = str(sorted(kwargs.items()))

        key_parts = [
            func.__module__,
            func.__name__,
            str(args),
            kwargs_str,
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired.

        Args:
            key: Cache key.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                # Expired, remove from cache
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds (uses default if not specified).
        """
        expiry = time.time() + (ttl if ttl is not None else self.default_ttl)
        self._cache[key] = (value, expiry)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def __call__(self, ttl: Optional[int] = None) -> Callable:
        """Decorator for caching function results.

        Args:
            ttl: Optional TTL override for this cached function.

        Returns:
            Decorator function.
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                cache_key = self._generate_key(func, args, kwargs)

                # Try to get from cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Execute function and cache result
                result = await func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                cache_key = self._generate_key(func, args, kwargs)

                # Try to get from cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Execute function and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result

            # Return appropriate wrapper based on whether function is async
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator


# Create global cache instance
cache = SimpleCache(default_ttl=300)  # 5 minute default TTL
