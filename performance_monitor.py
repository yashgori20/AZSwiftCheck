import time
import psutil
import threading
from datetime import datetime, timedelta
from azure_cache_utils import azure_cache
from azure_monitoring import azure_monitoring
import json

class PerformanceMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.request_metrics = {}
        self.system_metrics = {}
        self.redis_client = azure_cache.redis_client
        
        # Start background monitoring
        self.monitoring_thread = threading.Thread(target=self.monitor_system, daemon=True)
        self.monitoring_thread.start()
        
    def track_request_start(self, endpoint, method):
        """Track request start time"""
        request_id = f"{endpoint}_{method}_{time.time()}"
        self.request_metrics[request_id] = {
            "endpoint": endpoint,
            "method": method,
            "start_time": time.time(),
            "memory_start": psutil.Process().memory_info().rss
        }
        return request_id
    
    def track_request_end(self, request_id, status_code, response_size=0):
        """Track request completion and performance"""
        if request_id not in self.request_metrics:
            return
        
        metrics = self.request_metrics[request_id]
        end_time = time.time()
        duration = end_time - metrics["start_time"]
        memory_end = psutil.Process().memory_info().rss
        memory_used = memory_end - metrics["memory_start"]
        
        # Create performance record
        perf_data = {
            "endpoint": metrics["endpoint"],
            "method": metrics["method"],
            "duration_ms": round(duration * 1000, 2),
            "status_code": status_code,
            "response_size": response_size,
            "memory_used": memory_used,
            "timestamp": datetime.now().isoformat()
        }
        
        # Store in Redis for analytics
        self.store_performance_data(perf_data)
        
        # Send to Application Insights
        azure_monitoring.track_request(
            metrics["endpoint"], 
            metrics["method"], 
            status_code
        )
        
        # Cleanup
        del self.request_metrics[request_id]
        
        return perf_data
    
    def store_performance_data(self, perf_data):
        """Store performance data in Redis"""
        try:
            # Store individual request
            redis_key = f"perf:request:{int(time.time())}"
            self.redis_client.setex(redis_key, 3600, json.dumps(perf_data))  # Keep for 1 hour
            
            # Update endpoint averages
            endpoint_key = f"perf:avg:{perf_data['endpoint']}"
            endpoint_data = self.redis_client.get(endpoint_key)
            
            if endpoint_data:
                avg_data = json.loads(endpoint_data)
                avg_data["count"] += 1
                avg_data["total_duration"] += perf_data["duration_ms"]
                avg_data["avg_duration"] = avg_data["total_duration"] / avg_data["count"]
                avg_data["last_request"] = perf_data["timestamp"]
            else:
                avg_data = {
                    "endpoint": perf_data["endpoint"],
                    "count": 1,
                    "total_duration": perf_data["duration_ms"],
                    "avg_duration": perf_data["duration_ms"],
                    "last_request": perf_data["timestamp"]
                }
            
            self.redis_client.setex(endpoint_key, 86400, json.dumps(avg_data))  # Keep for 24 hours
            
        except Exception as e:
            print(f"❌ Error storing performance data: {e}")
    
    def monitor_system(self):
        """Background system monitoring"""
        while True:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                system_data = {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available": memory.available,
                    "disk_percent": disk.percent,
                    "uptime": time.time() - self.start_time,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Store in Redis
                self.redis_client.setex(
                    "system:metrics", 
                    300,  # Keep for 5 minutes
                    json.dumps(system_data)
                )
                
                # Sleep for 30 seconds
                time.sleep(30)
                
            except Exception as e:
                print(f"❌ System monitoring error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def get_performance_stats(self):
        """Get performance statistics"""
        try:
            # Get system metrics
            system_data = self.redis_client.get("system:metrics")
            system_metrics = json.loads(system_data) if system_data else {}
            
            # Get endpoint averages
            endpoint_keys = self.redis_client.keys("perf:avg:*")
            endpoint_stats = {}
            
            for key in endpoint_keys:
                endpoint_data = self.redis_client.get(key)
                if endpoint_data:
                    data = json.loads(endpoint_data)
                    endpoint_name = key.split(":")[-1]
                    endpoint_stats[endpoint_name] = data
            
            # Get recent requests
            recent_keys = self.redis_client.keys("perf:request:*")
            recent_requests = []
            
            for key in sorted(recent_keys)[-10:]:  # Last 10 requests
                request_data = self.redis_client.get(key)
                if request_data:
                    recent_requests.append(json.loads(request_data))
            
            return {
                "system_metrics": system_metrics,
                "endpoint_stats": endpoint_stats,
                "recent_requests": recent_requests,
                "total_requests": len(recent_keys)
            }
            
        except Exception as e:
            print(f"❌ Error getting performance stats: {e}")
            return {"error": str(e)}

# Global performance monitor
performance_monitor = PerformanceMonitor()