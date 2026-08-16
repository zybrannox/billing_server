from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import HTTPException


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit the maximum request body size"""
    
    def __init__(self, app, max_upload_size: int = 2 * 1024 * 1024 * 1024):  # 2GB default
        super().__init__(app)
        self.max_upload_size = max_upload_size
    
    async def dispatch(self, request: Request, call_next):
        # Check content-length header
        content_length = request.headers.get("content-length")
        
        if content_length:
            content_length = int(content_length)
            if content_length > self.max_upload_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body too large. Maximum size is {self.max_upload_size / (1024*1024):.0f}MB"
                )
        
        response = await call_next(request)
        return response
