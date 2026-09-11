from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None
    display_name: str


class LoginResponse(BaseModel):
    authenticated: bool
    user: UserResponse


class CurrentUserResponse(BaseModel):
    authenticated: bool
    user: UserResponse


class LogoutResponse(BaseModel):
    authenticated: bool
    message: str