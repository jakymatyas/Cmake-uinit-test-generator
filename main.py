import sys
import os
from agent import start_agent

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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <path/to/source_file.cpp>")
        sys.exit(1)
        
    target_file = os.path.abspath(sys.argv[1])
    
    project_root = find_project_root(target_file)
    
    if not project_root:
        print(f"Error: Could not find CMakePresets.json or root CMakeLists.txt anywhere above {target_file}")
        sys.exit(1)
        
    print(f"Project root found: Change working directory to {project_root}")
    os.chdir(project_root)
    
    start_agent(target_file)