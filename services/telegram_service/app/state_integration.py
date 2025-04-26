# services/telegram_service/app/state_integration.py

import logging
from aiogram.dispatcher import FSMContext

from common.state_management import state_manager

logger = logging.getLogger(__name__)


class UnifiedFSMContextAdapter:
    """
    Adapter class to make the unified state manager compatible with aiogram's FSMContext.
    This allows for a smooth transition to the unified state management system.
    """

    def __init__(self, user_id: str, platform: str = "telegram"):
        """
        Initialize the adapter.

        Args:
            user_id: User's platform-specific ID
            platform: Platform identifier (defaults to "telegram")
        """
        self.user_id = str(user_id)
        self.platform = platform

    async def get_data(self) -> dict:
        """
        Get state data for the user, mimicking FSMContext.get_data().

        Returns:
            State data dictionary or empty dict if not found
        """
        return await state_manager.get_state(self.platform, self.user_id) or {}

    async def get_state(self) -> str:
        """
        Get current state name for the user, mimicking FSMContext.get_state().

        Returns:
            Current state name or None
        """
        return await state_manager.get_current_state_name(self.platform, self.user_id)

    async def set_state(self, state: str = None) -> None:
        """
        Set state for the user, mimicking FSMContext.set_state().

        Args:
            state: State name to set
        """
        current_data = await self.get_data()
        current_data['state'] = state
        await state_manager.set_state(self.platform, self.user_id, current_data)

    async def update_data(self, **kwargs) -> None:
        """
        Update state data for the user, mimicking FSMContext.update_data().

        Args:
            **kwargs: Data to update
        """
        await state_manager.update_state(self.platform, self.user_id, kwargs)

    async def set_data(self, data: dict) -> None:
        """
        Set state data for the user, mimicking FSMContext.set_data().

        Args:
            data: Data to set
        """
        await state_manager.set_state(self.platform, self.user_id, data)

    async def reset_state(self, with_data: bool = True) -> None:
        """
        Reset state for the user, mimicking FSMContext.reset_state().

        Args:
            with_data: Whether to clear data as well
        """
        if with_data:
            await state_manager.clear_state(self.platform, self.user_id)
        else:
            current_data = await self.get_data()
            current_data.pop('state', None)
            await state_manager.set_state(self.platform, self.user_id, current_data)

    async def finish(self) -> None:
        """
        Finish the current state for the user, mimicking FSMContext.finish().
        """
        current_data = await self.get_data()
        current_data.pop('state', None)
        await state_manager.set_state(self.platform, self.user_id, current_data)


# Factory function to create an adapter from a user_id
def get_state_for_user(user_id: str) -> UnifiedFSMContextAdapter:
    """
    Get a state adapter for a Telegram user.

    Args:
        user_id: User's Telegram ID

    Returns:
        FSMContext-compatible adapter for the user
    """
    return UnifiedFSMContextAdapter(user_id)


# Function to migrate existing state from aiogram to unified system
async def migrate_existing_state(old_context: FSMContext, user_id: str) -> None:
    """
    Migrate existing state from aiogram's FSMContext to unified system.

    Args:
        old_context: Existing FSMContext
        user_id: User's Telegram ID
    """
    try:
        # Get existing state data
        state = await old_context.get_state()
        data = await old_context.get_data()

        # If there's existing data, migrate it
        if data:
            # Add state name to data if it exists
            if state:
                data['state'] = state

            # Save to unified state manager
            await state_manager.set_state("telegram", str(user_id), data)
            logger.info(f"Migrated state for Telegram user {user_id}")
    except Exception as e:
        logger.error(f"Error migrating state for Telegram user {user_id}: {e}")