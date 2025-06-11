import time
import json
from functools import wraps
from flask import request, jsonify, g
from azure_cache_utils import azure_cache
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self):
        self.redis_client = azure_cache.redis_client
        self.default_limits = {
            "/refine": {"requests": 10, "window": 60},      # 10 requests per minute
            "/edit": {"requests": 15, "window": 60},        # 15 requests per minute  
            "/digitize": {"requests": 5, "window": 60},     # 5 requests per minute (expensive)
            "/upload/async": {"requests": 20, "window": 60}, # 20 uploads per minute
            "default": {"requests": 100, "window": 60}       # 100 requests per minute for other endpoints
        }
    
    def get_client_id(self):
        """Get client identifier for rate limiting"""
        # Use IP address as client identifier
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'unknown')
        
        # Create a more specific client ID
        client_id = f"{client_ip}:{hash(user_agent) % 10000}"
        return client_id
    
    def is_rate_limited(self, endpoint=None):
        """Check if client is rate limited"""
        try:
            client_id = self.get_client_id()
            endpoint = endpoint or request.endpoint or request.path
            
            # Get rate limit for this endpoint
            limits = self.default_limits.get(endpoint, self.default_limits["default"])
            max_requests = limits["requests"]
            window_seconds = limits["window"]
            
            # Redis key for this client and endpoint
            redis_key = f"rate_limit:{client_id}:{endpoint}"
            
            # Get current request count
            current_requests = self.redis_client.get(redis_key)
            
            if current_requests is None:
                # First request in this window
                self.redis_client.setex(redis_key, window_seconds, 1)
                remaining = max_requests - 1
                reset_time = int(time.time()) + window_seconds
                
                g.rate_limit_info = {
                    "limit": max_requests,
                    "remaining": remaining,
                    "reset": reset_time,
                    "window": window_seconds
                }
                return False
            
            current_requests = int(current_requests)
            
            if current_requests >= max_requests:
                # Rate limit exceeded
                ttl = self.redis_client.ttl(redis_key)
                reset_time = int(time.time()) + (ttl if ttl > 0 else window_seconds)
                
                g.rate_limit_info = {
                    "limit": max_requests,
                    "remaining": 0,
                    "reset": reset_time,
                    "window": window_seconds,
                    "exceeded": True
                }
                return True
            
            # Increment counter
            self.redis_client.incr(redis_key)
            remaining = max_requests - (current_requests + 1)
            ttl = self.redis_client.ttl(redis_key)
            reset_time = int(time.time()) + (ttl if ttl > 0 else window_seconds)
            
            g.rate_limit_info = {
                "limit": max_requests,
                "remaining": remaining,
                "reset": reset_time,
                "window": window_seconds
            }
            
            return False
            
        except Exception as e:
            print(f"❌ Rate limiting error: {e}")
            # If Redis fails, allow the request
            return False
    
    def get_rate_limit_headers(self):
        """Get rate limit headers for response"""
        if hasattr(g, 'rate_limit_info'):
            info = g.rate_limit_info
            return {
                'X-RateLimit-Limit': str(info['limit']),
                'X-RateLimit-Remaining': str(info['remaining']),
                'X-RateLimit-Reset': str(info['reset']),
                'X-RateLimit-Window': str(info['window'])
            }
        return {}

# Global rate limiter
rate_limiter = RateLimiter()

def rate_limit(endpoint=None):
    """Decorator for rate limiting endpoints"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if rate_limiter.is_rate_limited(endpoint):
                info = g.rate_limit_info
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {info['limit']} per {info['window']} seconds",
                    "retry_after": info['reset'] - int(time.time()),
                    "limit": info['limit'],
                    "window": info['window']
                }), 429
            
            # Execute the original function
            response = func(*args, **kwargs)
            
            # Add rate limit headers to response
            if hasattr(response, 'headers'):
                headers = rate_limiter.get_rate_limit_headers()
                for key, value in headers.items():
                    response.headers[key] = value
            
            return response
        return wrapper
    return decorator