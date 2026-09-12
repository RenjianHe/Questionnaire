import functools
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log_invocation(func):
    """Decorator that logs the full incoming event and outgoing response
    to CloudWatch, regardless of which branch of the handler returns."""

    @functools.wraps(func)
    def wrapper(event, context):
        logger.info("REQUEST: %s", json.dumps(event, default=str))
        response = func(event, context)
        logger.info("RESPONSE: %s", json.dumps(response, default=str))
        return response

    return wrapper