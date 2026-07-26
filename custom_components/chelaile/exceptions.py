"""车来了集成自定义异常."""


class ChelaileError(Exception):
    """车来了集成基础异常."""


class ChelaileApiError(ChelaileError):
    """上游 API 返回非成功状态(jsonr.status 非 00)。"""

    def __init__(self, status: str, message: str = "") -> None:
        super().__init__(f"upstream error status={status}: {message}")
        self.status = status
        self.message = message


class ChelaileAuthError(ChelaileApiError):
    """签名/版本问题(如 12009 版本废弃)。视为需重新配置或修复客户端。"""


class ChelaileNotFoundError(ChelaileError):
    """线路或站点未找到。"""
