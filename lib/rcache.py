# pylint: disable=line-too-long
import logging
from functools import partial
import json
from redis import StrictRedis

class DistributedCache():
    """
    Handles caching results from the API into Redis to reduce hits on the API
    Also provides communication between workers
    """
    def __init__(self, function):
        self.__redis = StrictRedis(host="localhost", decode_responses=True)
        self.logger = logging.getLogger('mdapi.redis')
        self.function = function

    def get(self, cache_key: str, rformat="json"):
        if self.__redis.exists(cache_key):
            self.logger.debug("Got {} from cache".format(cache_key))
            if rformat == "json":
                return json.loads(self.__redis.get(cache_key))
            return self.__redis.get(cache_key)
        self.logger.debug("{} not in cache".format(cache_key))
        return None

    def set(self, cache_key: str, value: str, expire=300):
        self.__redis.setex(cache_key, expire, value)
        self.logger.debug("Put {} into cache with TTL of {}".format(cache_key, expire))

    def __call__(self, instance, *args, **kwargs):
        self.logger.debug("Called wrapper with {}, {}".format(args, kwargs))
        if kwargs:
            cache_key = hash(str(args)+str(kwargs))
            self.logger.debug("Cache key generated with string:{}".format(str(args)+str(kwargs)))
        else:
            cache_key = hash(str(args))
            self.logger.debug("Cache key generated with string:{}".format(str(args)))
        self.logger.debug("Using cache key of {}".format(cache_key))
        cached_value = self.get(cache_key)
        if cached_value:
            return cached_value
        response = self.function(instance, *args, **kwargs)
        self.set(cache_key, json.dumps(response))
        return response

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return partial(self, instance)
