import os
import logging
from flask import request, g
from azure_secrets import azure_secrets
from datetime import datetime
import time

class SimplifiedAzureMonitoring:
    def __init__(self, app=None):
        self.app = app
        self.enabled = False
        self.logger = None
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize simplified monitoring"""
        try:
            # Get connection string
            connection_string = azure_secrets.get_secret("app-insights-connection-string")
            
            if connection_string:
                # Try to use Azure Monitor OpenTelemetry
                try:
                    from azure.monitor.opentelemetry import configure_azure_monitor
                    
                    # Configure Azure Monitor
                    configure_azure_monitor(
                        connection_string=connection_string,
                        enable_live_metrics=True,
                        enable_standard_metrics=True
                    )
                    
                    # Setup OpenTelemetry Flask instrumentation
                    from opentelemetry.instrumentation.flask import FlaskInstrumentor
                    FlaskInstrumentor().instrument_app(app)
                    
                    print("✅ Azure Monitor OpenTelemetry configured")
                    self.enabled = True
                    
                except ImportError:
                    print("⚠️ Azure Monitor OpenTelemetry not available, using basic logging")
                    self.setup_basic_logging()
            else:
                print("⚠️ No Application Insights connection string, using basic logging")
                self.setup_basic_logging()
                
        except Exception as e:
            print(f"❌ Monitoring initialization error: {e}")
            self.setup_basic_logging()
    
    def setup_basic_logging(self):
        """Setup basic logging as fallback"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('swiftcheck')
        self.enabled = True
    
    def track_request(self, endpoint, method, status_code):
        """Track API request"""
        try:
            if self.logger:
                self.logger.info(f"API Request: {method} {endpoint} - Status: {status_code}")
            
            # If OpenTelemetry is working, it will automatically track requests
            
        except Exception as e:
            print(f"Request tracking error: {e}")
    
    def track_llm_call(self, model, product_name, response_length, duration_ms, cache_hit=False):
        """Track LLM call"""
        try:
            if self.logger:
                cache_status = "HIT" if cache_hit else "MISS"
                self.logger.info(
                    f"LLM Call: {model} for {product_name} - "
                    f"Duration: {duration_ms:.2f}ms - Cache: {cache_status} - "
                    f"Response Length: {response_length}"
                )
            
            # Custom metric for LLM calls
            self.track_custom_metric("llm_call_duration", duration_ms, {
                "model": model,
                "product_name": product_name,
                "cache_hit": str(cache_hit)
            })
            
        except Exception as e:
            print(f"LLM tracking error: {e}")
    
    def track_template_generation(self, product_name, parameter_count, tenant_id="default"):
        """Track template generation"""
        try:
            if self.logger:
                self.logger.info(
                    f"Template Generated: {product_name} - "
                    f"Parameters: {parameter_count} - Tenant: {tenant_id}"
                )
            
            # Custom metric for template generation
            self.track_custom_metric("template_generated", 1, {
                "product_name": product_name,
                "parameter_count": str(parameter_count),
                "tenant_id": tenant_id
            })
            
        except Exception as e:
            print(f"Template tracking error: {e}")
    
    def track_error(self, endpoint, error_type, error_message):
        """Track application errors"""
        try:
            if self.logger:
                self.logger.error(f"Error in {endpoint}: {error_type} - {error_message}")
            
            # Custom metric for errors
            self.track_custom_metric("application_error", 1, {
                "endpoint": endpoint,
                "error_type": error_type
            })
            
        except Exception as e:
            print(f"Error tracking error: {e}")
    
    def track_custom_metric(self, metric_name, value, properties=None):
        """Track custom metric"""
        try:
            # If OpenTelemetry is available, use it
            try:
                from opentelemetry import metrics
                meter = metrics.get_meter(__name__)
                counter = meter.create_counter(metric_name)
                counter.add(value, properties or {})
            except ImportError:
                # Fallback to logging
                if self.logger:
                    props_str = ", ".join([f"{k}={v}" for k, v in (properties or {}).items()])
                    self.logger.info(f"Metric: {metric_name}={value} [{props_str}]")
                    
        except Exception as e:
            print(f"Custom metric error: {e}")
    
    def track_performance(self, operation, duration_ms, metadata=None):
        """Track performance metrics"""
        try:
            if self.logger:
                meta_str = ", ".join([f"{k}={v}" for k, v in (metadata or {}).items()])
                self.logger.info(f"Performance: {operation} - {duration_ms:.2f}ms [{meta_str}]")
                
        except Exception as e:
            print(f"Performance tracking error: {e}")

# Global monitoring instance
azure_monitoring = SimplifiedAzureMonitoring()