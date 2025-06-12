from cosmos_db_utils import enhanced_cosmos_db
from datetime import datetime
import uuid
import json
from flask import request, g
import functools

class AuditLogger:
    def __init__(self):
        try:
            # Get or create audit logs container
            self.container = enhanced_cosmos_db.database.get_container_client("audit_logs")
        except:
            # Create container if it doesn't exist
            enhanced_cosmos_db.database.create_container(
                id="audit_logs",
                partition_key={"paths": ["/tenant_id"], "kind": "Hash"}
            )
            self.container = enhanced_cosmos_db.database.get_container_client("audit_logs")
    
    def log_event(self, event_type, entity_type, entity_id, details=None, user_id=None, tenant_id="default"):
        """Log audit event"""
        try:
            audit_record = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "event_type": event_type,  # CREATE, UPDATE, DELETE, VIEW, APPROVE, REJECT
                "entity_type": entity_type,  # TEMPLATE, PARAMETER, WORKFLOW, USER
                "entity_id": entity_id,
                "user_id": user_id or "system",
                "timestamp": datetime.now().isoformat(),
                "ip_address": self.get_client_ip(),
                "user_agent": request.headers.get('User-Agent', '') if request else '',
                "details": details or {},
                "session_id": getattr(g, 'session_id', None) if hasattr(g, 'session_id') else None
            }
            
            self.container.create_item(audit_record)
            print(f"✅ Audit logged: {event_type} on {entity_type}:{entity_id}")
            
        except Exception as e:
            print(f"❌ Audit logging failed: {e}")
    
    def get_client_ip(self):
        """Get client IP address"""
        if request:
            return request.headers.get('X-Forwarded-For', request.remote_addr)
        return "unknown"
    
    def get_audit_trail(self, entity_type=None, entity_id=None, tenant_id="default", limit=100):
        """Get audit trail for entity"""
        try:
            query = "SELECT * FROM c WHERE c.tenant_id = @tenant_id"
            parameters = [{"name": "@tenant_id", "value": tenant_id}]
            
            if entity_type:
                query += " AND c.entity_type = @entity_type"
                parameters.append({"name": "@entity_type", "value": entity_type})
            
            if entity_id:
                query += " AND c.entity_id = @entity_id"
                parameters.append({"name": "@entity_id", "value": entity_id})
            
            query += " ORDER BY c.timestamp DESC"
            
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                max_item_count=limit
            ))
            
            return items
            
        except Exception as e:
            print(f"❌ Error getting audit trail: {e}")
            return []
    
    def get_user_activity(self, user_id, tenant_id="default", days=30):
        """Get user activity summary"""
        try:
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = """
                SELECT c.event_type, COUNT(1) as count
                FROM c 
                WHERE c.tenant_id = @tenant_id 
                AND c.user_id = @user_id
                AND c.timestamp >= @start_date
                GROUP BY c.event_type
            """
            
            items = list(self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@user_id", "value": user_id},
                    {"name": "@start_date", "value": start_date}
                ]
            ))
            
            return items
            
        except Exception as e:
            print(f"❌ Error getting user activity: {e}")
            return []

# Global audit logger
audit_logger = AuditLogger()

# Decorator for automatic audit logging
def audit_log(event_type, entity_type, get_entity_id=None):
    """Decorator to automatically log audit events"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Extract entity ID
                entity_id = "unknown"
                if get_entity_id:
                    if callable(get_entity_id):
                        entity_id = get_entity_id(result, *args, **kwargs)
                    else:
                        entity_id = get_entity_id
                elif hasattr(result, 'json') and result.json:
                    # Try to get ID from response
                    response_data = result.json
                    entity_id = response_data.get('request_id', response_data.get('id', 'unknown'))
                
                # Get tenant ID (you may need to adjust this based on your auth system)
                tenant_id = request.args.get('tenant_id', 'default') if request else 'default'
                
                # Log the event
                audit_logger.log_event(
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    tenant_id=tenant_id,
                    details={"endpoint": request.endpoint if request else func.__name__}
                )
                
                return result
                
            except Exception as e:
                print(f"❌ Audit decorator error: {e}")
                return func(*args, **kwargs)
        
        return wrapper
    return decorator