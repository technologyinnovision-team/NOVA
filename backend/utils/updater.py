
import os
import requests
import shutil
import subprocess
import zipfile
import sys
import platform
import time
import gc
import stat
from flask import current_app
from alembic.config import Config
from alembic import script

# Windows-compatible file deletion utilities
def handle_remove_readonly(func, path, exc):
    """Error handler for Windows readonly files during shutil.rmtree"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass  # If we still can't delete, let the retry logic handle it

def safe_rmtree(path, logger=None, max_retries=5, retry_delay=1.0):
    """
    Remove directory tree with retry logic for Windows file locking.
    
    Args:
        path: Path to directory to remove
        logger: Optional logger function for status messages
        max_retries: Maximum number of retry attempts (default: 5)
        retry_delay: Initial delay between retries in seconds (default: 1.0)
    
    Returns:
        True if successful, raises exception otherwise
    """
    def log(msg):
        if logger:
            logger(msg)
    
    if not os.path.exists(path):
        return True
    
    for attempt in range(max_retries):
        try:
            # Force garbage collection to release file handles
            gc.collect()
            time.sleep(0.1)  # Small delay to allow Windows to release handles
            
            # Try to remove the directory tree
            shutil.rmtree(path, onerror=handle_remove_readonly)
            log(f"Successfully removed {path}")
            return True
            
        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                log(f"Retry {attempt + 1}/{max_retries} for {path}: {e}. Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                log(f"Failed to remove {path} after {max_retries} attempts: {e}")
                raise
    
    return False

class GitReleaseManager:
    def __init__(self, repo_owner, repo_name, token, logger=None):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.token = token
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"
        self.logger = logger

    def log(self, message):
        if self.logger:
            self.logger(message)
        else:
            print(message)

    def get_headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def check_updates(self, current_version):
        """
        Check for updates on GitHub.
        Returns the latest release info if it's newer than current_version, else None.
        """
        try:
            response = requests.get(self.api_url, headers=self.get_headers())
            response.raise_for_status()
            releases = response.json()

            if not releases:
                return None

            # Filter out drafts and prereleases if needed, for now take the latest
            latest_release = releases[0]
            latest_version = latest_release['tag_name'].lstrip('v')
            
            # Simple version comparison (can be improved with semver lib)
            if latest_version != current_version:
                 # Find the best asset (prefer backend.zip)
                 download_url = latest_release.get('zipball_url') # Default to source code
                 
                 for asset in latest_release.get('assets', []):
                     if asset['name'].lower() == 'backend.zip':
                         download_url = asset['browser_download_url']
                         break
                 
                 return {
                    'version': latest_version,
                    'tag_name': latest_release['tag_name'],
                    'body': latest_release['body'],
                    'assets': latest_release['assets'],
                    'published_at': latest_release['published_at'],
                    'download_url': download_url
                }
            return None

        except Exception as e:
            self.log(f"Error checking for updates: {e}")
            return None

    def get_all_releases(self):
        """
        Fetches all releases from GitHub.
        """
        try:
            response = requests.get(self.api_url, headers=self.get_headers())
            response.raise_for_status()
            releases = response.json()
            
            formatted_releases = []
            for release in releases:
                version = release['tag_name'].lstrip('v')
                
                # Find download url
                download_url = release.get('zipball_url')
                for asset in release.get('assets', []):
                     if asset['name'].lower() == 'backend.zip':
                         download_url = asset['browser_download_url']
                         break
                
                formatted_releases.append({
                    'version': version,
                    'tag_name': release['tag_name'],
                    'download_url': download_url,
                    'published_at': release['published_at']
                })
            
            return formatted_releases
        except Exception as e:
            self.log(f"Error fetching all releases: {e}")
            return []

    def download_release(self, asset_url, download_path):
        """Downloads the release asset to the specified path."""
        try:
            self.log(f"Starting download from {asset_url}...")
            # GitHub release assets might be redirected, so allow redirects
            headers = self.get_headers()
            headers["Accept"] = "application/octet-stream"
            
            with requests.get(asset_url, headers=headers, stream=True, allow_redirects=True) as r:
                r.raise_for_status()
                total_length = r.headers.get('content-length')
                
                with open(download_path, 'wb') as f:
                    if total_length is None: # no content length header
                        f.write(r.content)
                    else:
                        dl = 0
                        total_length = int(total_length)
                        for chunk in r.iter_content(chunk_size=8192):
                            dl += len(chunk)
                            f.write(chunk)
            self.log(f"Download completed: {download_path}")
            return download_path
        except Exception as e:
            self.log(f"Error downloading release: {e}")
            raise

class SystemManager:
    def __init__(self, base_dir, logger=None):
        self.base_dir = base_dir  # The 'backend' folder
        self.backup_dir = os.path.join(base_dir, '.backup')
        self.temp_dir = os.path.join(base_dir, '.temp_update')
        self.logger = logger

    def log(self, message):
        if self.logger:
            self.logger(message)
        else:
            print(message)

    def create_backup(self):
        """
        Creates a backup of the current backend folder before updating.
        Excludes: __pycache__, .backup, .temp_update, releases, storage
        """
        self.log("Creating backup of current version...")
        
        # Remove old backup if exists
        if os.path.exists(self.backup_dir):
            self.log("Removing old backup...")
            safe_rmtree(self.backup_dir, logger=self.log)
        
        # Define what to ignore
        def ignore_patterns(directory, files):
            ignored = []
            for f in files:
                # Ignore these folders
                if f in ['__pycache__', '.backup', '.temp_update', 'releases', 'storage']:
                    ignored.append(f)
                # Ignore .pyc files
                elif f.endswith('.pyc'):
                    ignored.append(f)
            return ignored
        
        # Copy entire backend to .backup
        try:
            shutil.copytree(self.base_dir, self.backup_dir, ignore=ignore_patterns)
            self.log(f"Backup created at {self.backup_dir}")
        except Exception as e:
            self.log(f"Error creating backup: {e}")
            raise

    def extract_release(self, zip_path):
        """
        Extracts the zip file directly to the backend folder, overwriting existing files.
        """
        self.log(f"Extracting update to {self.base_dir}...")
        
        # First extract to temp directory
        if os.path.exists(self.temp_dir):
            safe_rmtree(self.temp_dir, logger=self.log)
        os.makedirs(self.temp_dir)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            
            # GitHub zips often have a top-level folder (e.g. Repo-v1.0.0/). 
            # We want the contents directly.
            extracted_items = os.listdir(self.temp_dir)
            
            source_dir = self.temp_dir
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(self.temp_dir, extracted_items[0])):
                # There's a single top-level directory, use its contents
                source_dir = os.path.join(self.temp_dir, extracted_items[0])
                self.log(f"Flattening directory structure from {source_dir}...")
            
            # Now copy all files from source_dir to base_dir, overwriting
            self.log("Copying files to backend folder...")
            for item in os.listdir(source_dir):
                s = os.path.join(source_dir, item)
                d = os.path.join(self.base_dir, item)
                
                # Skip special directories
                if item in ['.backup', '.temp_update', 'storage', 'releases']:
                    self.log(f"Skipping {item}...")
                    continue
                
                if os.path.isdir(s):
                    # Remove existing directory and replace
                    if os.path.exists(d):
                        if item == 'uploads':
                            # Don't replace uploads folder
                            self.log(f"Preserving existing {item} folder...")
                            continue
                        safe_rmtree(d, logger=self.log)
                    shutil.copytree(s, d)
                else:
                    # Copy file, overwriting
                    if item == '.env':
                        # Don't overwrite .env
                        self.log("Preserving existing .env file...")
                        continue
                    shutil.copy2(s, d)
            
            # Clean up temp directory
            safe_rmtree(self.temp_dir, logger=self.log)
            self.log("Extraction complete.")
            
        except Exception as e:
            self.log(f"Error extracting release: {e}")
            # Clean up on error
            if os.path.exists(self.temp_dir):
                try:
                    safe_rmtree(self.temp_dir, logger=self.log)
                except Exception as cleanup_error:
                    self.log(f"Warning: Could not clean up temp directory: {cleanup_error}")
            raise

    def run_migrations(self):
        """
        Runs flask db upgrade in the current directory.
        """
        env = os.environ.copy()
        python_exe = sys.executable
        
        self.log("Running database migrations...")
        try:
            process = subprocess.Popen(
                [python_exe, '-m', 'flask', 'db', 'upgrade'], 
                cwd=self.base_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Stream output
            for line in process.stdout:
                self.log(line.strip())
            for line in process.stderr:
                self.log(line.strip())
                 
            process.wait()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args)
                
        except subprocess.CalledProcessError as e:
            self.log(f"Migration failed: {e}")
            raise

    def update_config_version(self, version):
        """
        Updates the VERSION constant in config.py to reflect the new version.
        """
        config_path = os.path.join(self.base_dir, 'config.py')
        if not os.path.exists(config_path):
            self.log(f"Warning: config.py not found at {config_path}")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace the VERSION line
            import re
            # Match VERSION = '...' or VERSION = "..."
            pattern = r"VERSION\s*=\s*['\"][^'\"]*['\"]"
            replacement = f"VERSION = '{version}'"
            
            if re.search(pattern, content):
                new_content = re.sub(pattern, replacement, content)
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                self.log(f"Updated VERSION in config.py to {version}")
            else:
                self.log("Warning: Could not find VERSION constant in config.py")
        except Exception as e:
            self.log(f"Error updating config.py: {e}")
            # Don't raise - this is not critical enough to fail the update

    def restore_from_backup(self):
        """
        Restores files from backup directory to rollback an update.
        """
        if not os.path.exists(self.backup_dir):
            raise FileNotFoundError(f"Backup directory not found at {self.backup_dir}")
        
        self.log("Restoring files from backup...")
        
        # Define what to skip
        skip_items = ['.backup', '.temp_update', 'storage', 'releases', '__pycache__']
        
        try:
            # Copy all files from backup to base_dir
            for item in os.listdir(self.backup_dir):
                if item in skip_items:
                    continue
                
                s = os.path.join(self.backup_dir, item)
                d = os.path.join(self.base_dir, item)
                
                if os.path.isdir(s):
                    # Remove existing and restore from backup
                    if os.path.exists(d) and item != 'uploads':
                        safe_rmtree(d, logger=self.log)
                    if not os.path.exists(d):
                        shutil.copytree(s, d)
                else:
                    # Restore file
                    shutil.copy2(s, d)
            
            self.log("Restore from backup complete.")
        except Exception as e:
            self.log(f"Error restoring from backup: {e}")
            raise

    def get_backup_version(self):
        """
        Gets the version from the backed up config.py if it exists.
        """
        backup_config = os.path.join(self.backup_dir, 'config.py')
        if not os.path.exists(backup_config):
            return None
        
        try:
            with open(backup_config, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            match = re.search(r"VERSION\s*=\s*['\"]([^'\"]*)['\"]", content)
            if match:
                return match.group(1)
        except:
            pass
        
        return None

    def has_backup(self):
        """
        Checks if a backup exists.
        """
        return os.path.exists(self.backup_dir) and os.path.isdir(self.backup_dir)

    def restart_services(self):
        """
        Restarts the application services using supervisorctl.
        """
        self.log("Restarting services...")
        try:
            # We use supervisorctl restart all
            subprocess.check_call(['supervisorctl', 'restart', 'all'])
            self.log("Services restarted successfully.")
        except subprocess.CalledProcessError as e:
            self.log(f"Failed to restart services: {e}")
        except FileNotFoundError:
             self.log("supervisorctl not found. Is Supervisor installed?")

