# services/viber_service/app/state_integration.py

import logging
from common.unified_state_management import state_manager

logger = logging.getLogger(__name__)

# Constant for the platform name
PLATFORM_NAME = "viber"


async def get_user_state(user_id: str) -> dict:
    """
    Get state for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        User state dictionary or empty dict if not found
    """
    return await state_manager.get_state(PLATFORM_NAME, user_id) or {}


async def set_user_state(user_id: str, state_data: dict) -> bool:
    """
    Set state for a Viber user.

    Args:
        user_id: User's Viber ID
        state_data: State data to store

    Returns:
        True if successful, False otherwise
    """
    return await state_manager.set_state(PLATFORM_NAME, user_id, state_data)


async def update_user_state(user_id: str, updates: dict) -> bool:
    """
    Update state for a Viber user.

    Args:
        user_id: User's Viber ID
        updates: State updates to apply

    Returns:
        True if successful, False otherwise
    """
    return await state_manager.update_state(PLATFORM_NAME, user_id, updates)


async def clear_user_state(user_id: str) -> bool:
    """
    Clear state for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        True if successful, False otherwise
    """
    return await state_manager.clear_state(PLATFORM_NAME, user_id)


async def get_current_state_name(user_id: str) -> str:
    """
    Get current state name for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        Current state name or None
    """
    return await state_manager.get_current_state_name(PLATFORM_NAME, user_id)


# Function to migrate from the old state manager to the new unified one
async def migrate_from_old_state_manager(user_id: str, old_state_manager: Any) -> None:
    """
    Migrate existing state from the old state manager to the unified system.

    Args:
        user_id: User's Viber ID
        old_state_manager: Old state manager instance
    """
    try:
        # Get existing state data
        old_state = await old_state_manager.get_state(user_id)

        # If there's existing data, migrate it
        if old_state:
            # Save to unified state manager
            await state_manager.set_state(PLATFORM_NAME, user_id, old_state)
            logger.info(f"Migrated state for Viber user {user_id}")
    except Exception as e:
        logger.error(f"Error migrating state for Viber user {user_id}: {e}")