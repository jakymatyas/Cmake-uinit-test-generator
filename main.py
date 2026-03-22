import sys
import os
import json
from dotenv import load_dotenv
from agent import start_agent

load_dotenv()

def find_project_root(start_path: str) -> str:
    """
    Walks up the directory tree looking specifically for CMakePresets.json.
    Ignores sub-directory CMakeLists.txt files.
    """
    current_dir = os.path.dirname(os.path.abspath(start_path))
    fallback_root = ""
    
    while current_dir != '/' and current_dir != '':
        if os.path.exists(os.path.join(current_dir, "CMakePresets.json")):
            return current_dir
            
        if os.path.exists(os.path.join(current_dir, "CMakeLists.txt")):
            fallback_root = current_dir
            
        current_dir = os.path.dirname(current_dir)
        
    return fallback_root

def run_single_file(target_path: str):
    """Run the agent for a single .cpp file."""
    target_file = os.path.abspath(target_path)
    project_root = find_project_root(target_file)
    
    if not project_root:
        print(f"Error: Could not find CMakePresets.json or root CMakeLists.txt anywhere above {target_file}")
        sys.exit(1)
        
    print(f"Project root found: {project_root}")
    os.chdir(project_root)
    start_agent(target_file)

def run_from_config(config_path: str):
    """Run the agent for each file listed in a JSON config."""
    config_path = os.path.abspath(config_path)
    
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
        
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    project_root = config.get("project_root")
    files = config.get("files", [])
    
    if not project_root:
        print("Error: Config must specify 'project_root'.")
        sys.exit(1)
        
    project_root = os.path.abspath(project_root)
    
    if not os.path.isdir(project_root):
        print(f"Error: project_root does not exist: {project_root}")
        sys.exit(1)
    
    if not files:
        print("Error: Config 'files' list is empty.")
        sys.exit(1)
    
    print(f"Project root: {project_root}")
    print(f"Generating tests for {len(files)} file(s):\n")
    os.chdir(project_root)
    
    for i, file_entry in enumerate(files, 1):
        filepath = file_entry if isinstance(file_entry, str) else file_entry.get("path", "")
        abs_path = os.path.join(project_root, filepath) if not os.path.isabs(filepath) else filepath
        
        print(f"\n{'='*60}")
        print(f"[{i}/{len(files)}] {abs_path}")
        print(f"{'='*60}")
        
        if not os.path.exists(abs_path):
            print(f"  SKIPPING: File not found: {abs_path}")
            continue

        try:
            start_agent(abs_path)
        except Exception as e:
            print(f"\n[ERROR] Agent failed for {abs_path}: {e}")
            print("  Continuing with next file...\n")

        if i < len(files):
            print("\n[Cooldown] Waiting 60s before next file to avoid rate limits...")
            import time
            time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py <path/to/source_file.cpp>       # Single file")
        print("  python main.py --config <path/to/config.json>   # Batch from config")
        sys.exit(1)
    
    if sys.argv[1] == "--config":
        if len(sys.argv) < 3:
            print("Error: --config requires a path to a JSON config file.")
            sys.exit(1)
        run_from_config(sys.argv[2])
    else:
        run_single_file(sys.argv[1])
