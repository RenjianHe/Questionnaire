# Invoked synchronously (Lambda Invoke, RequestResponse) by the create/update
# functions — not attached to API Gateway. Input/output are plain dicts, not
# API Gateway event format.
#
# Rule: the result for a given userId is stable (determined by the parity of
# the sum of the userId's character codes, resulting in 700 or 500). A real
# implementation would replace this with a call to the actual TransUnion API.


def handler(event, context):
    user_id = event.get("userId", "")
    checksum = sum(ord(ch) for ch in user_id)
    credit_score = 700 if checksum % 2 == 0 else 500
    return {"creditScore": credit_score}
