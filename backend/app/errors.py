from fastapi import HTTPException


def fail(code: str, message: str, status: int = 409, retryable: bool = False, headers: dict | None = None):
    raise HTTPException(status_code=status, detail={"code": code, "message": message, "retryable": retryable},
                        headers=headers)
