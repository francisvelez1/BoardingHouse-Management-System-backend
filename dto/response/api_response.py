from pydantic import BaseModel
from typing import TypeVar, Generic, Optional

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success:     bool
    message:     str
    data:        Optional[T] = None
    status_code: int         = 200

    @classmethod
    def success(
        cls,
        data:        Optional[T] = None,
        message:     str         = "Success",
        status_code: int         = 200,
    ) -> "ApiResponse[T]":
        return cls(success=True, message=message, data=data, status_code=status_code)

    @classmethod
    def error(
        cls,
        message:     str = "An error occurred",
        status_code: int = 400,
    ) -> "ApiResponse[None]":
        return cls(success=False, message=message, data=None, status_code=status_code)