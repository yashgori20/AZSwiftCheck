from cosmos_db_utils import enhanced_cosmos_db
from datetime import datetime, timedelta
import json
from collections import defaultdict

class AnalyticsEngine:
    def __init__(self):
        self.analytics_container = enhanced_cosmos_db.database.get_container_client("analytics_events")
    
    def track_event(self, tenant_id, event_type, event_data, user_id=None):
        """Track analytics event"""
        event_doc = {
            "id": f"{tenant_id}_{datetime.now().timestamp()}",
            "tenant_id": tenant_id,
            "event_type": event_type,
            "event_data": event_data,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "hour": datetime.now().hour
        }
        
        try:
            self.analytics_container.create_item(event_doc)
        except Exception as e:
            print(f"⚠️ Analytics tracking failed: {e}")
    
    def get_dashboard_data(self, tenant_id, days=30):
        """Get dashboard analytics data"""
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            # Get events for date range
            query = """
                SELECT * FROM c 
                WHERE c.tenant_id = @tenant_id 
                AND c.date >= @start_date
                ORDER BY c.timestamp DESC
            """
            
            events = list(self.analytics_container.query_items(
                query=query,
                parameters=[
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@start_date", "value": start_date}
                ]
            ))
            
            # Process analytics
            analytics = self.process_events(events)
            
            return {
                "tenant_id": tenant_id,
                "period_days": days,
                "total_events": len(events),
                **analytics
            }
            
        except Exception as e:
            print(f"❌ Error getting dashboard data: {e}")
            return {"error": str(e)}
    
    def process_events(self, events):
        """Process events into analytics metrics"""
        metrics = {
            "templates_created": 0,
            "templates_approved": 0,
            "files_processed": 0,
            "api_calls": 0,
            "daily_activity": defaultdict(int),
            "hourly_distribution": defaultdict(int),
            "top_products": defaultdict(int),
            "approval_times": [],
            "error_rate": 0
        }
        
        total_events = len(events)
        error_count = 0
        
        for event in events:
            event_type = event["event_type"]
            event_data = event.get("event_data", {})
            date = event["date"]
            hour = event["hour"]
            
            # Count by type
            if event_type == "template_created":
                metrics["templates_created"] += 1
                product = event_data.get("product_name", "Unknown")
                metrics["top_products"][product] += 1
                
            elif event_type == "template_approved":
                metrics["templates_approved"] += 1
                
            elif event_type == "file_processed":
                metrics["files_processed"] += 1
                
            elif event_type == "api_call":
                metrics["api_calls"] += 1
                
            elif event_type == "error":
                error_count += 1
            
            # Daily activity
            metrics["daily_activity"][date] += 1
            
            # Hourly distribution
            metrics["hourly_distribution"][hour] += 1
        
        # Calculate error rate
        metrics["error_rate"] = (error_count / total_events * 100) if total_events > 0 else 0
        
        # Convert defaultdicts to regular dicts for JSON serialization
        metrics["daily_activity"] = dict(metrics["daily_activity"])
        metrics["hourly_distribution"] = dict(metrics["hourly_distribution"])
        metrics["top_products"] = dict(sorted(
            metrics["top_products"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10])
        
        return metrics
    
    def get_performance_metrics(self, tenant_id):
        """Get performance metrics"""
        try:
            # Get recent performance data
            query = """
                SELECT * FROM c 
                WHERE c.tenant_id = @tenant_id 
                AND c.event_type = @event_type
                AND c.timestamp >= @start_time
            """
            
            start_time = (datetime.now() - timedelta(hours=24)).isoformat()
            
            performance_events = list(self.analytics_container.query_items(
                query=query,
                parameters=[
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@event_type", "value": "performance"},
                    {"name": "@start_time", "value": start_time}
                ]
            ))
            
            if not performance_events:
                return {"message": "No performance data available"}
            
            # Calculate metrics
            response_times = [e["event_data"]["response_time"] for e in performance_events if "response_time" in e["event_data"]]
            
            return {
                "avg_response_time": sum(response_times) / len(response_times) if response_times else 0,
                "max_response_time": max(response_times) if response_times else 0,
                "min_response_time": min(response_times) if response_times else 0,
                "total_requests": len(performance_events)
            }
            
        except Exception as e:
            print(f"❌ Error getting performance metrics: {e}")
            return {"error": str(e)}

# Global instance
analytics_engine = AnalyticsEngine()