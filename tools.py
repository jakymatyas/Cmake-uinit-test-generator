import os
import subprocess
import glob
import json
import fnmatch

def read_project_context(target_cpp_path: str) -> str:
    """
    Reads the target C++ file, its corresponding header, and the root CMakeLists.txt.
    Call this first to understand the code and how to link against it.
    """
    context = ""
    
    if os.path.exists(target_cpp_path):
        with open(target_cpp_path, 'r') as f:
            context += f"--- {target_cpp_path} ---\n{f.read()}\n\n"
    else:
        return f"Error: Could not find {target_cpp_path}"

    header_path_h = target_cpp_path.replace('.cpp', '.h')
    header_path_hpp = target_cpp_path.replace('.cpp', '.hpp')
    
    if os.path.exists(header_path_h):
        with open(header_path_h, 'r') as f:
            context += f"--- {header_path_h} ---\n{f.read()}\n\n"
    elif os.path.exists(header_path_hpp):
        with open(header_path_hpp, 'r') as f:
            context += f"--- {header_path_hpp} ---\n{f.read()}\n\n"

    if os.path.exists("CMakeLists.txt"):
        with open("CMakeLists.txt", 'r') as f:
            context += f"--- Root CMakeLists.txt ---\n{f.read()}\n\n"
            
    return context

def write_test_file(test_filename: str, cpp_test_content: str, cmake_content: str) -> str:
    """
    Writes the generated C++ test code to the tests/ directory and updates the tests/CMakeLists.txt.
    """
    test_dir = "tests"
    os.makedirs(test_dir, exist_ok=True)
    
    test_filepath = os.path.join(test_dir, test_filename)
    
    with open(test_filepath, 'w') as f:
        f.write(cpp_test_content)
        
    cmake_filepath = os.path.join(test_dir, "CMakeLists.txt")
    with open(cmake_filepath, 'w') as f:
        f.write(cmake_content)
        
    return f"Successfully wrote {test_filepath} and {cmake_filepath}"

def run_cmake_build(build_dir: str = "build") -> str:
    """
    Configures and builds the project using CMake. 
    Safely truncates massive C++ compiler errors to protect the LLM context window.
    """
    try:
        config_process = subprocess.run(
            ["cmake", "-B", build_dir, "-S", "."],
            capture_output=True, text=True, check=True
        )
        build_process = subprocess.run(
            ["cmake", "--build", build_dir],
            capture_output=True, text=True, check=True
        )
        return "Build Successful!\n" + build_process.stdout
        
    except subprocess.CalledProcessError as e:
        stderr_lines = e.stderr.splitlines()
        
        if len(stderr_lines) > 100:
            truncated_stderr = "\n".join(stderr_lines[:50])
            truncated_stderr += "\n\n... [HUNDREDS OF LINES OMITTED FOR BREVITY] ...\n\n"
            truncated_stderr += "\n".join(stderr_lines[-50:])
        else:
            truncated_stderr = e.stderr

        error_msg = f"Build FAILED.\nExit Code: {e.returncode}\n\nSTDERR:\n{truncated_stderr}"
        return error_msg
    
def extract_cmake_blueprint(source_dir: str = ".", build_dir: str = "build") -> str:
    """
    Forces CMake to generate a JSON blueprint of the project and extracts available targets.
    The agent uses this to know what libraries exist and how to link tests to them.
    """
    query_dir = os.path.join(build_dir, ".cmake", "api", "v1", "query")
    os.makedirs(query_dir, exist_ok=True)
    
    query_file = os.path.join(query_dir, "codemodel-v2")
    with open(query_file, "w") as f:
        pass 
        
    try:
        subprocess.run(
            ["cmake", "-S", source_dir, "-B", build_dir], 
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        return f"CMake Configure Failed:\n{e.stderr}"
        
    reply_dir = os.path.join(build_dir, ".cmake", "api", "v1", "reply")
    codemodel_files = glob.glob(os.path.join(reply_dir, "codemodel-v2-*.json"))
    
    if not codemodel_files:
        return "Error: CMake did not generate the codemodel JSON."
        
    blueprint_summary = "### Available CMake Targets Blueprint ###\n"
    
    with open(codemodel_files[0], 'r') as f:
        data = json.load(f)
        
        for config in data.get("configurations", []):
            for project in config.get("projects", []):
                blueprint_summary += f"\nProject Name: {project.get('name')}\n"
                blueprint_summary += "Targets you can link against:\n"
                
                for target in config.get("targets", []):
                    clean_name = target.get('name').split('::')[0]
                    blueprint_summary += f" - {clean_name}\n"
                    
    blueprint_summary += "\n(Use these exact target names in target_link_libraries for your tests.)"
    
    return blueprint_summary

def search_codebase(file_pattern: str, text_query: str = "", root_dir: str = ".") -> str:
    """
    Searches the repository for files matching a pattern (e.g., '*.h', 'Network*.cpp').
    Optionally searches for specific text within those files to find missing classes/functions.
    """
    matches = []
    
    for dirpath, _, filenames in os.walk(root_dir):
        if '.git' in dirpath or 'build' in dirpath or '.cmake' in dirpath:
            continue
            
        for filename in fnmatch.filter(filenames, file_pattern):
            filepath = os.path.join(dirpath, filename)
            
            if not text_query:
                matches.append(filepath)
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for line_num, line in enumerate(lines, 1):
                        if text_query in line:
                            matches.append(f"{filepath}:{line_num}: {line.strip()}")
            except Exception:
                pass
    if not matches:
        return f"No results found for pattern '{file_pattern}' and query '{text_query}'."
        
    max_results = 50
    result_str = "\n".join(matches[:max_results])
    
    if len(matches) > max_results:
        result_str += f"\n... (and {len(matches) - max_results} more results omitted)"
        
    return f"Search Results:\n{result_str}"
