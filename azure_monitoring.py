import os
import logging
from flask import request
from azure_secrets import azure_secrets

class AzureMonitoring:
    def __init__(self, app=None):
        self.app = app
        self.enabled = False
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize simple monitoring"""
        try:
            # Set up basic logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            self.logger = logging.getLogger('swiftcheck')
            self.enabled = True
            
            print("✅ Basic monitoring enabled")
                
        except Exception as e:
            print(f"❌ Monitoring initialization failed: {e}")
    
    def track_request(self, endpoint, method, status_code):
        """Track API request with basic logging"""
        try:
            if self.enabled:
                self.logger.info(f"Request: {method} {endpoint} - Status: {status_code}")
        except Exception as e:
            print(f"Monitoring error: {e}")
    
    def track_llm_call(self, model, product_name, response_length, cache_hit=False):
        """Track LLM call with basic logging"""
        try:
            if self.enabled:
                cache_status = "HIT" if cache_hit else "MISS"
                self.logger.info(f"LLM Call: {model} for {product_name} - Cache: {cache_status} - Length: {response_length}")
        except Exception as e:
            print(f"Monitoring error: {e}")

# Global monitoring instance
azure_monitoring = AzureMonitoring()