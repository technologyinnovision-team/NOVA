
import os
import zipfile
import datetime
from sqlalchemy import inspect, text
from flask import current_app
from werkzeug.utils import secure_filename
import io
import shutil

class BackupService:
    @staticmethod
    def dump_database(db_engine):
        """
        Generates a SQL dump of the database.
        Returns a string containing the SQL dump.
        """
        inspector = inspect(db_engine)
        tables = inspector.get_table_names()
        
        output = io.StringIO()
        output.write(f"-- Backup created at {datetime.datetime.now()}\n\n")
        
        # Disable foreign key checks
        output.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
        
        connection = db_engine.connect()
        try:
            for table_name in tables:
                # Get table schema (Create Table)
                # Note: SQLAlchemy doesn't provide a direct "SHOW CREATE TABLE" equivalent 
                # that works identically across all DBs easily without raw SQL.
                # For MySQL we can use SHOW CREATE TABLE
                try:
                    create_table_sql = connection.execute(text(f"SHOW CREATE TABLE `{table_name}`")).fetchone()[1]
                    output.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
                    output.write(f"{create_table_sql};\n\n")
                except Exception as e:
                    output.write(f"-- Error getting schema for {table_name}: {str(e)}\n\n")

                # Get data
                try:
                    data = connection.execute(text(f"SELECT * FROM `{table_name}`")).fetchall()
                    if data:
                        # Get column names
                        columns = [col['name'] for col in inspector.get_columns(table_name)]
                        cols_str = ", ".join([f"`{c}`" for c in columns])
                        
                        output.write(f"INSERT INTO `{table_name}` ({cols_str}) VALUES \n")
                        
                        values_list = []
                        for row in data:
                            row_values = []
                            for val in row:
                                if val is None:
                                    row_values.append("NULL")
                                elif isinstance(val, int) or isinstance(val, float):
                                    row_values.append(str(val))
                                elif isinstance(val, bool):
                                     row_values.append('1' if val else '0')
                                else:
                                    # Escape quotes
                                    val_str = str(val).replace("'", "''").replace("\\", "\\\\")
                                    row_values.append(f"'{val_str}'")
                            values_list.append(f"({', '.join(row_values)})")
                        
                        output.write(",\n".join(values_list))
                        output.write(";\n\n")
                except Exception as e:
                    output.write(f"-- Error getting data for {table_name}: {str(e)}\n\n")
            
            output.write("SET FOREIGN_KEY_CHECKS=1;\n")
            
        finally:
            connection.close()
            
        return output.getvalue()

    @staticmethod
    def create_backup(include_db=True, include_media=True):
        """
        Creates a zip backup.
        
        Args:
            include_db: Boolean, include database dump
            include_media: Boolean, include uploads folder
            
        Returns:
            Path to the created zip file
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.zip"
        
        # Ensure backups directory exists
        base_dir = current_app.root_path
        backup_dir = os.path.join(base_dir, 'backups')
        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            
        zip_path = os.path.join(backup_dir, filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. Database Backup
            if include_db:
                try:
                    # Import db here to avoid circular imports
                    from models import db
                    sql_content = BackupService.dump_database(db.engine)
                    zipf.writestr('database.sql', sql_content)
                except Exception as e:
                    current_app.logger.error(f"Database backup failed: {e}")
                    zipf.writestr('database_error.txt', str(e))
            
            # 2. Media Backup
            if include_media:
                uploads_dir = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                if not os.path.isabs(uploads_dir):
                    uploads_dir = os.path.join(base_dir, uploads_dir)
                
                if os.path.exists(uploads_dir):
                    for root, dirs, files in os.walk(uploads_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, os.path.dirname(uploads_dir))
                            zipf.write(file_path, arcname)
                else:
                    zipf.writestr('media_error.txt', f"Uploads directory not found at: {uploads_dir}")
                    
        return zip_path
