# services/whatsapp_service/app/state_integration.py

from common.unified_state_management import state_manager
from .bot import sanitize_phone_number
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from . import logger

# Constant for the platform name
PLATFORM_NAME = "whatsapp"


@log_operation("get_user_state")
async def get_user_state(user_id: str) -> dict:
    """
    Get state for a WhatsApp user.

    Args:
        user_id: User's WhatsApp number (will be sanitized)

    Returns:
        User state dictionary or empty dict if not found
    """
    with log_context(logger, user_id=user_id):
        # Sanitize the phone number first
        clean_user_id = sanitize_phone_number(user_id)
        logger.debug(f"Sanitized user ID: {clean_user_id}")

        state = await state_manager.get_state(PLATFORM_NAME, clean_user_id) or {}
        logger.debug(f"Retrieved state for user {clean_user_id}: {bool(state)}")

        return state


@log_operation("set_user_state")
async def set_user_state(user_id: str, state_data: dict) -> bool:
    """
    Set state for a WhatsApp user.

    Args:
        user_id: User's WhatsApp number (will be sanitized)
        state_data: State data to store

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id, state_keys=list(state_data.keys())):
        # Sanitize the phone number first
        clean_user_id = sanitize_phone_number(user_id)
        logger.debug(f"Setting state for sanitized user ID: {clean_user_id}")

        success = await state_manager.set_state(PLATFORM_NAME, clean_user_id, state_data)
        logger.info(f"State set for user {clean_user_id}: success={success}")

        return success


@log_operation("update_user_state")
async def update_user_state(user_id: str, updates: dict) -> bool:
    """
    Update state for a WhatsApp user.

    Args:
        user_id: User's WhatsApp number (will be sanitized)
        updates: State updates to apply

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id, update_keys=list(updates.keys())):
        # Sanitize the phone number first
        clean_user_id = sanitize_phone_number(user_id)
        logger.debug(f"Updating state for sanitized user ID: {clean_user_id}")

        success = await state_manager.update_state(PLATFORM_NAME, clean_user_id, updates)
        logger.info(f"State updated for user {clean_user_id}: success={success}")

        return success


@log_operation("clear_user_state")
async def clear_user_state(user_id: str) -> bool:
    """
    Clear state for a WhatsApp user.

    Args:
        user_id: User's WhatsApp number (will be sanitized)

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id):
        # Sanitize the phone number first
        clean_user_id = sanitize_phone_number(user_id)
        logger.debug(f"Clearing state for sanitized user ID: {clean_user_id}")

        success = await state_manager.clear_state(PLATFORM_NAME, clean_user_id)
        logger.info(f"State cleared for user {clean_user_id}: success={success}")

        return success


@log_operation("get_current_state_name")
async def get_current_state_name(user_id: str) -> str:
    """
    Get current state name for a WhatsApp user.

    Args:
        user_id: User's WhatsApp number (will be sanitized)

    Returns:
        Current state name or None
    """
    with log_context(logger, user_id=user_id):
        # Sanitize the phone number first
        clean_user_id = sanitize_phone_number(user_id)
        logger.debug(f"Getting current state name for sanitized user ID: {clean_user_id}")

        state_name = await state_manager.get_current_state_name(PLATFORM_NAME, clean_user_id)
        logger.debug(f"Current state name for user {clean_user_id}: {state_name}")

        return state_name


@log_operation("migrate_from_old_state_manager")
async def migrate_from_old_state_manager(user_id: str, old_state_manager: Any) -> None:
    """
    Migrate existing state from the old state manager to the unified system.

    Args:
        user_id: User's WhatsApp number
        old_state_manager: Old state manager instance
    """
    with log_context(logger, user_id=user_id):
        logger.info(f"Starting state migration for user {user_id}")

        try:
            # Sanitize the phone number first
            clean_user_id = sanitize_phone_number(user_id)
            logger.debug(f"Sanitized user ID for migration: {clean_user_id}")

            # Get existing state data
            old_state = await old_state_manager.get_state(clean_user_id)
            logger.debug(f"Retrieved old state for user {clean_user_id}: {bool(old_state)}")

            # If there's existing data, migrate it
            if old_state:
                # Save to unified state manager
                success = await state_manager.set_state(PLATFORM_NAME, clean_user_id, old_state)
                logger.info(f"Migrated state for WhatsApp user {clean_user_id}: success={success}")
            else:
                logger.info(f"No existing state to migrate for user {clean_user_id}")

        except Exception as e:
            logger.error(f"Error migrating state for WhatsApp user {user_id}", exc_info=True, extra={
                'error_type': type(e).__name__
            })