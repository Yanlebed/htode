# services/viber_service/app/state_integration.py

from common.unified_state_management import state_manager

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from . import logger

# Constant for the platform name
PLATFORM_NAME = "viber"


@log_operation("get_user_state")
async def get_user_state(user_id: str) -> dict:
    """
    Get state for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        User state dictionary or empty dict if not found
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME):
        try:
            state = await state_manager.get_state(PLATFORM_NAME, user_id) or {}
            logger.debug(f"Retrieved user state", extra={
                'user_id': user_id,
                'state_keys': list(state.keys()) if state else [],
                'has_state': bool(state)
            })
            return state
        except Exception as e:
            logger.error(f"Error getting user state", exc_info=True, extra={
                'user_id': user_id,
                'platform': PLATFORM_NAME,
                'error_type': type(e).__name__
            })
            return {}


@log_operation("set_user_state")
async def set_user_state(user_id: str, state_data: dict) -> bool:
    """
    Set state for a Viber user.

    Args:
        user_id: User's Viber ID
        state_data: State data to store

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME):
        try:
            result = await state_manager.set_state(PLATFORM_NAME, user_id, state_data)

            if result:
                logger.info(f"Set user state successfully", extra={
                    'user_id': user_id,
                    'state_keys': list(state_data.keys()),
                    'state_size': len(str(state_data))
                })
            else:
                logger.warning(f"Failed to set user state", extra={
                    'user_id': user_id,
                    'state_keys': list(state_data.keys())
                })

            return result
        except Exception as e:
            logger.error(f"Error setting user state", exc_info=True, extra={
                'user_id': user_id,
                'platform': PLATFORM_NAME,
                'error_type': type(e).__name__,
                'state_keys': list(state_data.keys())
            })
            return False


@log_operation("update_user_state")
async def update_user_state(user_id: str, updates: dict) -> bool:
    """
    Update state for a Viber user.

    Args:
        user_id: User's Viber ID
        updates: State updates to apply

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME):
        try:
            result = await state_manager.update_state(PLATFORM_NAME, user_id, updates)

            if result:
                logger.info(f"Updated user state successfully", extra={
                    'user_id': user_id,
                    'update_keys': list(updates.keys()),
                    'updates_size': len(str(updates))
                })
            else:
                logger.warning(f"Failed to update user state", extra={
                    'user_id': user_id,
                    'update_keys': list(updates.keys())
                })

            return result
        except Exception as e:
            logger.error(f"Error updating user state", exc_info=True, extra={
                'user_id': user_id,
                'platform': PLATFORM_NAME,
                'error_type': type(e).__name__,
                'update_keys': list(updates.keys())
            })
            return False


@log_operation("clear_user_state")
async def clear_user_state(user_id: str) -> bool:
    """
    Clear state for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME):
        try:
            result = await state_manager.clear_state(PLATFORM_NAME, user_id)

            if result:
                logger.info(f"Cleared user state successfully", extra={
                    'user_id': user_id
                })
            else:
                logger.warning(f"Failed to clear user state", extra={
                    'user_id': user_id
                })

            return result
        except Exception as e:
            logger.error(f"Error clearing user state", exc_info=True, extra={
                'user_id': user_id,
                'platform': PLATFORM_NAME,
                'error_type': type(e).__name__
            })
            return False


@log_operation("get_current_state_name")
async def get_current_state_name(user_id: str) -> str:
    """
    Get current state name for a Viber user.

    Args:
        user_id: User's Viber ID

    Returns:
        Current state name or None
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME):
        try:
            state_name = await state_manager.get_current_state_name(PLATFORM_NAME, user_id)

            logger.debug(f"Retrieved current state name", extra={
                'user_id': user_id,
                'state_name': state_name,
                'has_state': bool(state_name)
            })

            return state_name
        except Exception as e:
            logger.error(f"Error getting current state name", exc_info=True, extra={
                'user_id': user_id,
                'platform': PLATFORM_NAME,
                'error_type': type(e).__name__
            })
            return None


@log_operation("migrate_from_old_state_manager")
async def migrate_from_old_state_manager(user_id: str, old_state_manager: Any) -> None:
    """
    Migrate existing state from the old state manager to the unified system.

    Args:
        user_id: User's Viber ID
        old_state_manager: Old state manager instance
    """
    with log_context(logger, user_id=user_id, platform=PLATFORM_NAME, operation="migration"):
        try:
            # Get existing state data
            old_state = await old_state_manager.get_state(user_id)

            # If there's existing data, migrate it
            if old_state:
                logger.info(f"Migrating state for user", extra={
                    'user_id': user_id,
                    'state_keys': list(old_state.keys()),
                    'state_size': len(str(old_state))
                })

                # Save to unified state manager
                success = await state_manager.set_state(PLATFORM_NAME, user_id, old_state)

                if success:
                    logger.info(f"Successfully migrated state for Viber user {user_id}")
                else:
                    logger.error(f"Failed to migrate state for Viber user {user_id}")
            else:
                logger.info(f"No state to migrate for user {user_id}")

        except Exception as e:
            logger.error(f"Error migrating state for Viber user {user_id}", exc_info=True, extra={
                'error_type': type(e).__name__,
                'platform': PLATFORM_NAME
            })