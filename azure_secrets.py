import os
import subprocess
import json

class AzureSecrets:
    def __init__(self):
        self._cache = {}
        self.vault_name = "swiftcheckai-keyvault"
        
        # Check if we're in production
        self.is_production = os.getenv("AZURE_ENVIRONMENT") == "production"
        print(f"🌍 Environment: {os.getenv('AZURE_ENVIRONMENT', 'development')}")
    
    def get_secret(self, secret_name):
        """Get secret with production environment support"""
        if secret_name not in self._cache:
            try:
                # Map secret names to environment variable names
                env_var_mapping = {
                    "cosmos-connection-string": "COSMOS_CONNECTION_STRING",
                    "openai-endpoint": "OPENAI_ENDPOINT", 
                    "openai-key": "OPENAI_KEY",
                    "search-endpoint": "SEARCH_ENDPOINT",
                    "search-admin-key": "SEARCH_ADMIN_KEY",
                    "blob-connection-string": "BLOB_CONNECTION_STRING",
                    "redis-host": "REDIS_HOST",
                    "redis-key": "REDIS_KEY",
                    "form-recognizer-endpoint": "FORM_RECOGNIZER_ENDPOINT",
                    "form-recognizer-key": "FORM_RECOGNIZER_KEY",
                    "event-grid-endpoint": "EVENT_GRID_ENDPOINT",
                    "event-grid-key": "EVENT_GRID_KEY"
                }
                
                # First try environment variable (for Container Apps)
                env_var_name = env_var_mapping.get(secret_name, secret_name.replace('-', '_').upper())
                env_value = os.getenv(env_var_name)
                
                if env_value:
                    self._cache[secret_name] = env_value
                    print(f"✅ Retrieved {secret_name} from environment")
                    return env_value
                
                # Fallback to Azure CLI (for local development)
                if not self.is_production:
                    cmd = f'az keyvault secret show --vault-name {self.vault_name} --name {secret_name} --query "value" --output tsv'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        self._cache[secret_name] = result.stdout.strip()
                        print(f"✅ Retrieved {secret_name} from Key Vault")
                    else:
                        print(f"❌ Error getting secret {secret_name}: {result.stderr}")
                        self._cache[secret_name] = None
                else:
                    print(f"❌ Secret {secret_name} not found in environment variables")
                    self._cache[secret_name] = None
                    
            except Exception as e:
                print(f"❌ Error getting secret {secret_name}: {e}")
                self._cache[secret_name] = None
        
        return self._cache[secret_name]

# Global instance
azure_secrets = AzureSecrets()

# Convenience functions
def get_cosmos_connection():
    return azure_secrets.get_secret("cosmos-connection-string")

def get_openai_config():
    return {
        "endpoint": azure_secrets.get_secret("openai-endpoint"),
        "key": azure_secrets.get_secret("openai-key")
    }

def get_search_config():
    return {
        "endpoint": azure_secrets.get_secret("search-endpoint"),
        "admin_key": azure_secrets.get_secret("search-admin-key")
    }

def get_blob_connection():
    return azure_secrets.get_secret("blob-connection-string")

def get_redis_config():
    return {
        "host": azure_secrets.get_secret("redis-host"),
        "key": azure_secrets.get_secret("redis-key")
    }

def get_form_recognizer_config():
    return {
        "endpoint": azure_secrets.get_secret("form-recognizer-endpoint"),
        "key": azure_secrets.get_secret("form-recognizer-key")
    }