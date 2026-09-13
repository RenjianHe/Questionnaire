import json
from decimal import Decimal

_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def _json_default(value):
    # DynamoDB returns numbers as Decimal. Convert back to int/float so the
    # API response has real JSON numbers instead of stringified ones.
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return str(value)


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": _HEADERS,
        "body": json.dumps(body, default=_json_default),
    }


def ok(body: dict):
    return _response(200, body)


def created(body: dict):
    return _response(201, body)


def bad_request(message: str):
    return _response(400, {"error": "BadRequest", "message": message})


def not_found(message: str):
    return _response(404, {"error": "NotFound", "message": message})


def conflict(message: str):
    return _response(409, {"error": "Conflict", "message": message})


def internal_error(message: str):
    return _response(500, {"error": "InternalServerError", "message": message})
