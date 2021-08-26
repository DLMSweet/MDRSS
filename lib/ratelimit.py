'''
Rate limit public interface.

This module includes the decorator used to rate limit function invocations.
Additionally this module includes a naive retry strategy to be used in
conjunction with the rate limit decorator.

Original code from: https://github.com/tomasbasham/ratelimit
'''
from functools import wraps
from math import floor

import time
import sys
import threading
from redis import StrictRedis

def now():
    '''
    Use monotonic time if available, otherwise fall back to the system clock.
    :return: Time function.
    :rtype: function
    '''
    if hasattr(time, 'monotonic'):
        return time.monotonic
    return time.time

class RateLimitException(Exception):
    '''
    Rate limit exception class.
    '''
    def __init__(self, message, period_remaining):
        '''
        Custom exception raise when the number of function invocations exceeds
        that imposed by a rate limit. Additionally the exception is aware of
        the remaining time period after which the rate limit is reset.
        :param string message: Custom exception message.
        :param float period_remaining: The time remaining until the rate limit is reset.
        '''
        super(RateLimitException, self).__init__(message)
        self.period_remaining = period_remaining

class RateLimitDecorator(object):
    '''
    Rate limit decorator class.
    '''
    def __init__(self, calls=15, period=900, clock=now(), raise_on_limit=True):
        '''
        Instantiate a RateLimitDecorator with some sensible defaults. By
        default the Twitter rate limiting window is respected (15 calls every
        15 minutes).

        :param int calls: Maximum function invocations allowed within a time period.
        :param float period: An upper bound time period (in seconds) before the rate limit resets.
        :param function clock: An optional function retuning the current time.
        :param bool raise_on_limit: A boolean allowing the caller to avoiding rasing an exception.
        '''
        self.__redis = StrictRedis(host="localhost", decode_responses=True)
        self.clamped_calls = calls
        self.period = period
        self.clock = clock
        self.raise_on_limit = raise_on_limit

        # Initialise the decorator state.
        self.last_reset = clock()
        self.num_calls = 0

        # Add thread safety.
        self.lock = threading.RLock()

    @property
    def num_calls(self):
        return int(self.__redis.get("rl_numcalls"))

    @num_calls.setter
    def num_calls(self, calls):
        self.__redis.set("rl_numcalls", calls)
		
    @property
    def last_reset(self):
        return float(self.__redis.get("rl_last_reset"))

    @last_reset.setter
    def last_reset(self, cur_clock):
        self.__redis.set("rl_last_reset", cur_clock)

    def __call__(self, func):
        '''
        Return a wrapped function that prevents further function invocations if
        previously called within a specified period of time.

        :param function func: The function to decorate.
        :return: Decorated function.
        :rtype: function
        '''
        @wraps(func)
        def wrapper(*args, **kargs):
            '''
            Extend the behaviour of the decorated function, forwarding function
            invocations previously called no sooner than a specified period of
            time. The decorator will raise an exception if the function cannot
            be called so the caller may implement a retry strategy such as an
            exponential backoff.

            :param args: non-keyword variable length argument list to the decorated function.
            :param kargs: keyworded variable length argument list to the decorated function.
            :raises: RateLimitException
            '''
            with self.lock:
                period_remaining = self.__period_remaining()

                # If the time window has elapsed then reset.
                if period_remaining <= 0:
                    self.num_calls = 0
                    self.last_reset = self.clock()

                # Increase the number of attempts to call the function.
                self.num_calls += 1

                # If the number of attempts to call the function exceeds the
                # maximum then raise an exception.
                if self.num_calls > self.clamped_calls:
                    if self.raise_on_limit:
                        raise RateLimitException('too many calls', period_remaining)
                    return

            return func(*args, **kargs)
        return wrapper

    def __period_remaining(self):
        '''
        Return the period remaining for the current rate limit window.

        :return: The remaing period.
        :rtype: float
        '''
        elapsed = self.clock() - self.last_reset
        return self.period - elapsed

def sleep_and_retry(func):
    '''
    Return a wrapped function that rescues rate limit exceptions, sleeping the
    current thread until rate limit resets.

    :param function func: The function to decorate.
    :return: Decorated function.
    :rtype: function
    '''
    @wraps(func)
    def wrapper(*args, **kargs):
        '''
        Call the rate limited function. If the function raises a rate limit
        exception sleep for the remaing time period and retry the function.

        :param args: non-keyword variable length argument list to the decorated function.
        :param kargs: keyworded variable length argument list to the decorated function.
        '''
        while True:
            try:
                return func(*args, **kargs)
            except RateLimitException as exception:
                time.sleep(exception.period_remaining)
    return wrapper