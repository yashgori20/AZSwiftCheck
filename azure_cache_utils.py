from gptcache import cache
from gptcache.manager import CacheBase, VectorBase
from gptcache.embedding import Onnx
from azure_secrets import get_redis_config
import redis
import hashlib
import json
from datetime import datetime

class AzureRedisCacheManager:
    def __init__(self):
        redis_config = get_redis_config()
        
        # Connect to Azure Redis
        self.redis_client = redis.Redis(
            host=redis_config["host"],
            port=6380,  # Azure Redis SSL port
            password=redis_config["key"],
            ssl=True,
            decode_responses=True
        )
        
        # Test connection
        try:
            self.redis_client.ping()
            print("✅ Connected to Azure Redis Cache")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
    
    def get_cache_key(self, user_message, doc_type, product_name, supplier_name):
        """Generate cache key for LLM request"""
        # Create deterministic key from request parameters
        cache_data = {
            "user_message": user_message,
            "doc_type": doc_type,
            "product_name": product_name,
            "supplier_name": supplier_name
        }
        
        # Create hash of the request
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_key = hashlib.sha256(cache_string.encode()).hexdigest()
        
        return f"swiftcheck:llm:{cache_key}"
    
    def get_cached_response(self, user_message, doc_type, product_name, supplier_name):
        """Get cached LLM response if available"""
        try:
            cache_key = self.get_cache_key(user_message, doc_type, product_name, supplier_name)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                cached_response = json.loads(cached_data)
                print(f"✅ Cache HIT for {product_name}")
                return cached_response["response"]
            else:
                print(f"⚡ Cache MISS for {product_name}")
                return None
                
        except Exception as e:
            print(f"❌ Cache retrieval error: {e}")
            return None
    
    def cache_response(self, user_message, doc_type, product_name, supplier_name, llm_response):
        """Cache LLM response"""
        try:
            cache_key = self.get_cache_key(user_message, doc_type, product_name, supplier_name)
            
            cache_data = {
                "response": llm_response,
                "cached_at": datetime.now().isoformat(),
                "product_name": product_name,
                "doc_type": doc_type
            }
            
            # Cache for 24 hours (86400 seconds)
            self.redis_client.setex(
                cache_key, 
                86400,  # 24 hours TTL
                json.dumps(cache_data)
            )
            
            print(f"✅ Cached response for {product_name}")
            
        except Exception as e:
            print(f"❌ Cache storage error: {e}")
    
    def clear_cache(self, pattern="swiftcheck:llm:*"):
        """Clear cache by pattern"""
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                print(f"✅ Cleared {len(keys)} cache entries")
            else:
                print("⚡ No cache entries to clear")
        except Exception as e:
            print(f"❌ Cache clear error: {e}")
    
    def get_cache_stats(self):
        """Get cache statistics"""
        try:
            keys = self.redis_client.keys("swiftcheck:llm:*")
            stats = {
                "total_entries": len(keys),
                "memory_usage": self.redis_client.memory_usage("swiftcheck:llm:*") if keys else 0,
                "redis_info": self.redis_client.info("memory")
            }
            return stats
        except Exception as e:
            print(f"❌ Stats error: {e}")
            return {"error": str(e)}

# Global instance
azure_cache = AzureRedisCacheManager()