from sqlalchemy.orm import Session
from typing import TypeVar, Generic, Type, Optional, List

T = TypeVar('T')


class BaseRepository(Generic[T]):
    @staticmethod
    def get_by_id(db: Session, model_class: Type[T], id: int) -> Optional[T]:
        return db.query(model_class).filter(model_class.id == id).first()

    @staticmethod
    def get_all(db: Session, model_class: Type[T]) -> List[T]:
        return db.query(model_class).all()

    @staticmethod
    def create(db: Session, model_class: Type[T], data: dict) -> T:
        entity = model_class(**data)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    @staticmethod
    def update(db: Session, entity: T, data: dict) -> T:
        for key, value in data.items():
            setattr(entity, key, value)
        db.commit()
        db.refresh(entity)
        return entity

    @staticmethod
    def delete(db: Session, entity: T) -> bool:
        db.delete(entity)
        db.commit()
        return True