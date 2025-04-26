# common/flows/__init__.py

from common.messaging.flow_builder import flow_library

# Import all flows to ensure they're registered
from .subscription_flow import subscription_flow
from .property_search_flow import property_search_flow

# Add any additional flows here as they're created

# Export flow_library for easy access
__all__ = ['flow_library']