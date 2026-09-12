# 被 create/update 函数以 Lambda Invoke（RequestResponse）方式同步调用，
# 不挂在 API Gateway 上，入参/出参就是普通 dict，不是 API Gateway 事件格式。
#
# 规则：同一个 userId 每次查询结果稳定（用 userId 的哈希奇偶性决定 700 或 500），
# 真实实现应替换为对 TransUnion 官方 API 的调用。


def handler(event, context):
    user_id = event.get("userId", "")
    checksum = sum(ord(ch) for ch in user_id)
    credit_score = 700 if checksum % 2 == 0 else 500
    return {"creditScore": credit_score}
