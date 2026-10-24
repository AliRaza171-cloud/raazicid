from fastapi import HTTPException


def api_error(status: int, code: str, message: str) -> HTTPException:
    """Errors in the shape promised by docs/api-contract.md: {"detail": {"code", "message"}}."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})
