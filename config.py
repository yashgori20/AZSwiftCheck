import os

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    AZURE_ENVIRONMENT = os.environ.get('AZURE_ENVIRONMENT', 'development')
    
class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    AZURE_ENVIRONMENT = 'development'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    AZURE_ENVIRONMENT = 'production'

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    AZURE_ENVIRONMENT = 'testing'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}