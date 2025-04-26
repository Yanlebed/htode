# common/db/models/__init__.py
# Import all models to ensure they're registered with SQLAlchemy
from common.db.base import Base
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.models.ad import Ad, AdImage, AdPhone
from common.db.models.favorite import FavoriteAd
from common.db.models.payment import PaymentOrder

# Import all repositories for easy access
from common.db.repositories.user_repository import UserRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.favorite_repository import FavoriteRepository

# Function to create all tables (for initial setup)
def create_tables():
    from common.db.session import engine
    Base.metadata.create_all(bind=engine)