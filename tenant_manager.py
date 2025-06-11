from cosmos_db_utils import enhanced_cosmos_db
from azure_cache_utils import azure_cache
import uuid
from datetime import datetime
import json

class TenantManager:
    def __init__(self):
        self.container = enhanced_cosmos_db.database.get_container_client("tenants")
    
    def create_tenant(self, company_name, contact_email, subscription_plan="basic"):
        """Create new tenant"""
        tenant_id = str(uuid.uuid4())
        
        tenant_doc = {
            "id": tenant_id,
            "company_name": company_name,
            "contact_email": contact_email,
            "subscription_plan": subscription_plan,
            "features": self.get_plan_features(subscription_plan),
            "settings": {
                "max_users": 10 if subscription_plan == "basic" else 100,
                "max_templates": 50 if subscription_plan == "basic" else 500,
                "api_rate_limit": 100 if subscription_plan == "basic" else 1000,
                "storage_limit_gb": 5 if subscription_plan == "basic" else 50,
                "custom_branding": subscription_plan != "basic",
                "advanced_analytics": subscription_plan == "enterprise"
            },
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        try:
            self.container.create_item(tenant_doc)
            
            # Create tenant-specific containers
            self.setup_tenant_resources(tenant_id)
            
            print(f"✅ Created tenant: {tenant_id} ({company_name})")
            return tenant_id
            
        except Exception as e:
            print(f"❌ Error creating tenant: {e}")
            raise
    
    def get_plan_features(self, plan):
        """Get features for subscription plan"""
        plans = {
            "basic": [
                "qc_template_generation",
                "basic_analytics",
                "email_support"
            ],
            "professional": [
                "qc_template_generation",
                "workflow_approvals", 
                "advanced_analytics",
                "api_access",
                "priority_support"
            ],
            "enterprise": [
                "qc_template_generation",
                "workflow_approvals",
                "advanced_analytics", 
                "api_access",
                "custom_integrations",
                "dedicated_support",
                "white_labeling",
                "audit_logs"
            ]
        }
        
        return plans.get(plan, plans["basic"])
    
    def setup_tenant_resources(self, tenant_id):
        """Setup tenant-specific resources"""
        try:
            # Create tenant-specific containers
            database = enhanced_cosmos_db.database
            
            containers = [
                f"tenant_{tenant_id}_templates",
                f"tenant_{tenant_id}_users", 
                f"tenant_{tenant_id}_analytics"
            ]
            
            for container_name in containers:
                try:
                    database.create_container(
                        id=container_name,
                        partition_key={"paths": ["/tenant_id"], "kind": "Hash"}
                    )
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠️ Error creating container {container_name}: {e}")
            
            print(f"✅ Setup resources for tenant: {tenant_id}")
            
        except Exception as e:
            print(f"❌ Error setting up tenant resources: {e}")
    
    def get_tenant(self, tenant_id):
        """Get tenant information"""
        try:
            return self.container.read_item(item=tenant_id, partition_key=tenant_id)
        except Exception as e:
            print(f"❌ Error getting tenant {tenant_id}: {e}")
            return None
    
    def validate_tenant_limits(self, tenant_id, operation_type):
        """Validate if tenant can perform operation"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False, "Tenant not found"
        
        settings = tenant.get("settings", {})
        
        # Check rate limits
        if operation_type == "api_call":
            rate_limit = settings.get("api_rate_limit", 100)
            cache_key = f"tenant_{tenant_id}_api_calls"
            
            try:
                current_calls = azure_cache.redis_client.get(cache_key) or 0
                if int(current_calls) >= rate_limit:
                    return False, "Rate limit exceeded"
                
                # Increment counter (expires in 1 hour)
                azure_cache.redis_client.incr(cache_key)
                azure_cache.redis_client.expire(cache_key, 3600)
                
            except Exception as e:
                print(f"⚠️ Rate limit check failed: {e}")
        
        # Check storage limits
        elif operation_type == "file_upload":
            storage_limit = settings.get("storage_limit_gb", 5) * 1024 * 1024 * 1024  # Convert to bytes
            # TODO: Implement storage usage tracking
            pass
        
        return True, "OK"
    
    def get_tenant_analytics(self, tenant_id):
        """Get analytics for tenant"""
        try:
            # Get usage statistics
            analytics_container = enhanced_cosmos_db.database.get_container_client(
                f"tenant_{tenant_id}_analytics"
            )
            
            # Get recent activity
            query = """
                SELECT * FROM c 
                WHERE c.tenant_id = @tenant_id 
                ORDER BY c.created_at DESC
                OFFSET 0 LIMIT 100
            """
            
            activities = list(analytics_container.query_items(
                query=query,
                parameters=[{"name": "@tenant_id", "value": tenant_id}]
            ))
            
            return {
                "tenant_id": tenant_id,
                "recent_activities": activities,
                "total_templates": len([a for a in activities if a.get("type") == "template_created"]),
                "total_users": self.get_tenant_user_count(tenant_id),
                "api_calls_today": self.get_api_calls_today(tenant_id)
            }
            
        except Exception as e:
            print(f"❌ Error getting tenant analytics: {e}")
            return {"error": str(e)}
    
    def get_tenant_user_count(self, tenant_id):
        """Get user count for tenant"""
        try:
            users_container = enhanced_cosmos_db.database.get_container_client(
                f"tenant_{tenant_id}_users"
            )
            
            query = "SELECT VALUE COUNT(1) FROM c WHERE c.tenant_id = @tenant_id"
            result = list(users_container.query_items(
                query=query,
                parameters=[{"name": "@tenant_id", "value": tenant_id}]
            ))
            
            return result[0] if result else 0
            
        except Exception as e:
            print(f"❌ Error getting user count: {e}")
            return 0
    
    def get_api_calls_today(self, tenant_id):
        """Get API calls for today"""
        try:
            cache_key = f"tenant_{tenant_id}_api_calls"
            calls = azure_cache.redis_client.get(cache_key) or 0
            return int(calls)
        except Exception as e:
            print(f"❌ Error getting API calls: {e}")
            return 0

# Global instance
tenant_manager = TenantManager()