from flask_session.sqlalchemy import SqlAlchemySessionInterface
from sqlalchemy.exc import IntegrityError, PendingRollbackError, OperationalError, ResourceClosedError
from flask import current_app

class CustomSqlAlchemySessionInterface(SqlAlchemySessionInterface):
    """
    Custom session interface to handle IntegrityError (race conditions) and connection issues.
    """
    
    def __init__(self, app, db, table, key_prefix, use_signer=False, permanent=True, sql_session_model=None):
        # Allow passing existing model to avoid re-declaration warning
        self._existing_model = sql_session_model
        super().__init__(app, db, table, key_prefix, use_signer, permanent)

    def _create_model(self, db, table):
        """
        Check if the Session model already exists to avoid SAWarning about double declaration.
        """
        if self._existing_model:
            return self._existing_model
            
        try:
            # Check SQLAlchemy's mapper registry for existing mapped class
            if hasattr(db.Model, 'registry'):
                for mapper in db.Model.registry.mappers:
                    if mapper.class_.__tablename__ == table:
                        return mapper.class_
            # Falback for older SQLAlchemy or different setups
            elif hasattr(db.Model, '_decl_class_registry'):
                for name, cls in db.Model._decl_class_registry.items():
                    if hasattr(cls, '__tablename__') and cls.__tablename__ == table:
                        return cls
        except Exception:
            pass
            
        # If not found, create it using parent method
        return super()._create_model(db, table)

    def _safe_rollback(self):
        """
        Attempt to rollback the session. If the connection is lost/invalid, 
        remove the session to force a fresh connection on next use.
        """
        try:
            self.db.session.rollback()
        except Exception as e:
            current_app.logger.warning(f"Session rollback failed: {e}. Removing session.")
            try:
                self.db.session.remove()
            except Exception:
                pass

    def save_session(self, *args, **kwargs):
        try:
            return super().save_session(*args, **kwargs)
        except (IntegrityError, PendingRollbackError, OperationalError, ResourceClosedError) as e:
            current_app.logger.warning(f"Session save error: {e}. Retrying...")
            self._safe_rollback()
            try:
                # Retry once
                return super().save_session(*args, **kwargs)
            except Exception as e2:
                current_app.logger.error(f"Retry session save failed: {e2}")
                # Try one last safe rollback to clean up
                self._safe_rollback()

    def _upsert_session(self, store_id, data, expiry):
        """
        Handle upsert with race condition and connection error protection.
        """
        try:
            return super()._upsert_session(store_id, data, expiry)
        except IntegrityError:
            self._safe_rollback()
            # Handle duplicate: try to update existing
            try:
                record = self.sql_session_model.query.filter_by(session_id=store_id).first()
                if record:
                    record.data = data
                    record.expiry = expiry
                    self.db.session.add(record)
                    self.db.session.commit()
                else:
                    # Rare case: Duplicate error but not found?
                    current_app.logger.error("IntegrityError (duplicate) but session not found.")
            except Exception as e:
                current_app.logger.error(f"Failed to recover from IntegrityError: {e}")
                self._safe_rollback()
        except (PendingRollbackError, OperationalError, ResourceClosedError) as e:
            current_app.logger.warning(f"Connection error in _upsert_session: {e}. Retrying...")
            self._safe_rollback()
            try:
                return super()._upsert_session(store_id, data, expiry)
            except Exception as e2:
                current_app.logger.error(f"Retry _upsert_session failed: {e2}")
                self._safe_rollback()
        except Exception as e:
            # Catch-all for weird SQLAlchemy errors like "AttributeError" during broken state
            current_app.logger.error(f"Unexpected error in _upsert_session: {e}. Retrying...")
            self._safe_rollback()
            try:
                return super()._upsert_session(store_id, data, expiry)
            except Exception as e2:
                current_app.logger.error(f"Retry _upsert_session failed (generic): {e2}")
                self._safe_rollback()
