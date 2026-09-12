import json

_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": _HEADERS,
        "body": json.dumps(body, default=str),
    }


def ok(body: dict):
    return _response(200, body)


def created(body: dict):
    return _response(201, body)


def bad_request(message: str):
    return _response(400, {"error": "BadRequest", "message": message})


def not_found(message: str):
    return _response(404, {"error": "NotFound", "message": message})


def internal_error(message: str):
    return _response(500, {"error": "InternalServerError", "message": message})
