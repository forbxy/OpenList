import os
import sys
import tarfile
import shutil
import json
import subprocess

try:
    import requests
except ImportError:
    print("Installing requests module...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# GitHub token from environment variable if available
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
HEADERS = {'Accept': 'application/vnd.github.v3+json'}
if GITHUB_TOKEN:
    HEADERS['Authorization'] = f'token {GITHUB_TOKEN}'

REPO = 'OpenListTeam/OpenList-Frontend'

def get_git_tag():
    try:
        # Run git describe --tags --abbrev=0 to get the latest tag from current commit ancestry
        # Ensure we run this command from the script's directory or project root
        cwd = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.check_output(
            ['git', 'describe', '--tags', '--abbrev=0'],
            cwd=cwd,
            stderr=subprocess.PIPE
        )
        tag = result.decode('utf-8').strip()
        if not tag:
            raise ValueError("Empty tag returned")
        return tag
    except Exception as e:
        print(f"Error: Could not determine git tag using 'git describe --tags --abbrev=0'.\nDetails: {e}")
        print("Please ensure you are in a git repository with tags fetched.")
        sys.exit(1)

# Release tag determined dynamically from git
RELEASE_TAG = get_git_tag()

def fetch_frontend():
    print(f"Fetching frontend assets for release: {RELEASE_TAG}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    public_dist_dir = os.path.join(root_dir, 'public', 'dist')
    version_file = os.path.join(public_dist_dir, 'VERSION')

    # Check if VERSION file exists and matches current RELEASE_TAG
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                current_version = f.read().strip()
                if current_version == RELEASE_TAG:
                    print(f"Frontend version {current_version} already exists. Skipping download.")
                    return True
        except Exception:
            pass # Continue if read fails

    # 1. Get Release Info
    if RELEASE_TAG == 'latest':
        url = f'https://api.github.com/repos/{REPO}/releases/latest'
    else:
        url = f'https://api.github.com/repos/{REPO}/releases/tags/{RELEASE_TAG}'
        
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        release_data = response.json()
    except Exception as e:
        if RELEASE_TAG == 'rolling':
            print("Rolling release not found, trying latest...")
            url = f'https://api.github.com/repos/{REPO}/releases/latest'
            try:
                response = requests.get(url, headers=HEADERS)
                response.raise_for_status()
                release_data = response.json()
            except Exception as e2:
                print(f"Failed to fetch release info: {e2}")
                return False
        else:
            print(f"Failed to fetch release info: {e}")
            return False

    # 2. Find Asset
    assets = release_data.get('assets', [])
    download_url = None
    target_name = 'openlist-frontend-dist.tar.gz'
    
    for asset in assets:
        name = asset.get('name', '')
        # Filter logic from build.sh: contain openlist-frontend-dist, not contain lite, end with .tar.gz
        if 'openlist-frontend-dist' in name and 'lite' not in name and name.endswith('.tar.gz'):
             download_url = asset.get('browser_download_url')
             break
             
    if not download_url:
        print(f"Asset {target_name} not found in release assets.")
        return False
        
    print(f"Downloading from: {download_url}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 3. Create output dir if needed
    output_dir = os.path.join(script_dir, 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 4. Download
    local_filename = os.path.join(output_dir, 'dist.tar.gz')
    try:
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f"Download failed: {e}")
        return False
        
    # 5. Extract
    # Since this script is now in kodi_lib/, target is one level up in root public/dist
    root_dir = os.path.dirname(script_dir)
    public_dist_dir = os.path.join(root_dir, 'public', 'dist')
    
    # Backup README.md if it exists
    readme_path = os.path.join(public_dist_dir, 'README.md')
    readme_content = None
    if os.path.exists(readme_path):
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
        except Exception as e:
            print(f"Warning: Failed to backup README.md: {e}")

    # Cleanup existing
    if os.path.exists(public_dist_dir):
        print(f"Cleaning existing dist dir: {public_dist_dir}")
        shutil.rmtree(public_dist_dir)
    os.makedirs(public_dist_dir, exist_ok=True)
    
    # Restore README.md immediately after cleanup/creation
    if readme_content is not None:
        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            print("Restored README.md")
        except Exception as e:
             print(f"Warning: Failed to restore README.md: {e}")
    
    print(f"Extracting to: {public_dist_dir}")
    try:
        with tarfile.open(local_filename, 'r:gz') as tar:
            
            # Helper to strip leading components if archive has them (e.g., dist/)
            # But usually npm pack or build artifacts might be flat or in a folder. 
            # build.sh does: tar -zxvf dist.tar.gz -C public/dist
            # Which suggests the tarball contents go directly into public/dist.
            # If the tarball has a top-level folder 'dist', we might end up with public/dist/dist.
            # Let's inspect first member.
            
            prefix = ""
            members = tar.getmembers()
            if members and members[0].name.startswith('dist/'):
                # Strip 'dist/' prefix if present
                for member in members:
                    if member.name.startswith('dist/'):
                        member.name = member.name[5:] # len('dist/')
                        tar.extract(member, path=public_dist_dir)
            else:
                 tar.extractall(path=public_dist_dir)

        # Create/Update VERSION file
        version_file = os.path.join(public_dist_dir, 'VERSION')
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(RELEASE_TAG)

    except Exception as e:
        print(f"Extraction failed: {e}")
        return False
    finally:
        # Cleanup tar
        if os.path.exists(local_filename):
            os.remove(local_filename)

    print("Frontend fetch completed successfully.")
    return True

if __name__ == '__main__':
    if fetch_frontend():
        exit(0)
    else:
        exit(1)
