"""错误类型与退出码映射。"""

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_QUOTA = 3
EXIT_AUTH = 4
EXIT_UNAVAILABLE = 5
EXIT_OLD = 6

QUOTA_CODES = {"SERVICE_BUDGET_PAUSED", "TOKEN_RATE_LIMIT"}
UNAVAILABLE_CODES = {"TOKEN_QUOTA_UNAVAILABLE", "MODERATION_UNAVAILABLE", "STORAGE_UNAVAILABLE",
                     "NETWORK_ERROR", "WAIT_TIMEOUT"}


# 服务端的 AUTHORIZED_EXPORT_REQUIRED：受保护的音频（如 Suno）没有下载任务，只能在小程序里打开或转发。
PROTECTED_AUDIO = "AUTHORIZED_EXPORT_REQUIRED"
PROTECTED_AUDIO_MESSAGE = "这条音频受平台保护，命令行不能提取；请在拾帧小程序里打开或转发。"


class CliError(Exception):
    def __init__(self, exit_code, code, message, retryable=False, reset_at=None, extra=None):
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.reset_at = reset_at
        self.extra = extra or {}


def exit_code_for(status, code, retryable=False):
    """按服务端状态码与错误码决定退出码。status 为 0 表示来自任务内的错误。"""
    code = code or ""
    if status == 426 or code == "CLI_TOO_OLD":
        return EXIT_OLD
    if code in QUOTA_CODES or code.startswith("DAILY_") or status == 429:
        return EXIT_QUOTA
    if code in UNAVAILABLE_CODES:
        return EXIT_UNAVAILABLE
    if status == 401 or code.startswith("TOKEN_") or code == "GUEST_LOGIN_REQUIRED":
        return EXIT_AUTH
    if status in (502, 503, 504) or status >= 500:
        return EXIT_UNAVAILABLE
    if retryable:
        return EXIT_UNAVAILABLE
    return EXIT_INPUT


def from_response(status, body):
    """把服务端错误响应转成 CliError。兼容 detail 为对象或字符串。"""
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        code = str(detail.get("code") or "HTTP_%d" % status)
        message = str(detail.get("message") or "请求失败（HTTP %d）" % status)
        retryable = bool(detail.get("retryable", status >= 500))
        reset_at = detail.get("resetAt")
    else:
        code = "HTTP_%d" % status
        message = str(detail) if detail else "请求失败（HTTP %d）" % status
        retryable = status >= 500
        reset_at = None
    if code == PROTECTED_AUDIO:
        message, retryable = PROTECTED_AUDIO_MESSAGE, False
    if status == 426 and code.startswith("HTTP_"):
        code = "CLI_TOO_OLD"
    if status == 401 and code.startswith("HTTP_"):
        code = "TOKEN_INVALID"
        message = "令牌无效、已过期或已被吊销，请到小程序重新生成。"
    return CliError(exit_code_for(status, code, retryable), code, message, retryable, reset_at)
