import os
import subprocess
import glob
import json
import fnmatch
import stat

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
    
    header_name = os.path.basename(target_cpp_path).split('.')[0]
    
    direct_h = target_cpp_path.replace('.cpp', '.h')
    direct_hpp = target_cpp_path.replace('.cpp', '.hpp')
    
    found_header_path = None
    if os.path.exists(direct_h):
        found_header_path = direct_h
    elif os.path.exists(direct_hpp):
        found_header_path = direct_hpp
    else:
        search_result = search_codebase(file_pattern=f"{header_name}.h*")
        if "Search Results:" in search_result:
            found_header_path = search_result.split('\n')[1].strip()

    if found_header_path and os.path.exists(found_header_path):
        with open(found_header_path, 'r') as f:
            context += f"--- {found_header_path} ---\n{f.read()}\n\n"
    else:
        context += f"Warning: Could not automatically locate header for {header_name}.\n\n"

    if os.path.exists("CMakeLists.txt"):
        with open("CMakeLists.txt", 'r') as f:
            context += f"--- Root CMakeLists.txt ---\n{f.read()}\n\n"
            
    return context

def write_test_file(target_cpp_path: str, cpp_test_content: str, cmake_content_to_append: str) -> str:
    """
    Writes a unit test file to the 'utest' directory next to the 'src' directory.
    Automatically prefixes the filename with 'UT_'.
    Appends the CMake configuration to utest/CMakeLists.txt instead of overwriting.
    """

    target_dir = os.path.dirname(target_cpp_path)
    base_name = os.path.basename(target_cpp_path)
    name_without_ext = os.path.splitext(base_name)[0]
    
    if os.path.basename(target_dir) == 'src':
        parent_dir = os.path.dirname(target_dir)
    else:
        parent_dir = target_dir
        
    utest_dir = os.path.join(parent_dir, 'utest')
    os.makedirs(utest_dir, exist_ok=True)
    
    test_filename = f"UT_{name_without_ext}.cpp"
    test_filepath = os.path.join(utest_dir, test_filename)
    
    with open(test_filepath, 'w') as f:
        f.write(cpp_test_content)
        
    cmake_filepath = os.path.join(utest_dir, "CMakeLists.txt")
    
    mode = 'a' if os.path.exists(cmake_filepath) else 'w'
    
    with open(cmake_filepath, mode) as f:
        if mode == 'a':
            f.write(f"\n\n# --- Auto-generated test for {base_name} ---\n")
        else:
            f.write(f"# Auto-generated CMakeLists for {os.path.basename(parent_dir)} tests\n\n")
            
        f.write(cmake_content_to_append)
        
    return f"Successfully wrote {test_filepath} and appended to {cmake_filepath}"

def run_cmake_build(target_name: str = "") -> str:
    """
    Configures and builds a specific target using the 'ubuntu-RelWithDebInfo' CMake preset.
    Safely truncates massive C++ compiler errors to protect the LLM context window.
    """
    try:
        subprocess.run(
            ["cmake", "--preset", "ubuntu-RelWithDebInfo"],
            capture_output=True, text=True, check=True
        )
        
        build_cmd = ["cmake", "--build", "--preset", "ubuntu-RelWithDebInfo"]
        if target_name:
            build_cmd.extend(["--target", target_name])
            
        build_process = subprocess.run(
            build_cmd,
            capture_output=True, text=True, check=True
        )
        return f"Build Successful for target '{target_name or 'all'}'!\n" + build_process.stdout
        
    except subprocess.CalledProcessError as e:
        stderr_lines = e.stderr.splitlines()
        
        if len(stderr_lines) > 100:
            truncated_stderr = "\n".join(stderr_lines[:50])
            truncated_stderr += "\n\n... [HUNDREDS OF LINES OMITTED FOR BREVITY] ...\n\n"
            truncated_stderr += "\n".join(stderr_lines[-50:])
        else:
            truncated_stderr = e.stderr

        failed_target = target_name if target_name else "all"
        error_msg = f"Build FAILED for target '{failed_target}'.\nExit Code: {e.returncode}\n\nSTDERR:\n{truncated_stderr}"
        return error_msg
    
def extract_cmake_blueprint() -> str:
    """
    Forces CMake to generate a JSON blueprint using the 'ubuntu-RelWithDebInfo' preset.
    Extracts available targets so the agent knows how to link tests.
    """
    build_dir = "build/ubuntu-RelWithDebInfo"
    query_dir = os.path.join(build_dir, ".cmake", "api", "v1", "query")
    os.makedirs(query_dir, exist_ok=True)
    
    query_file = os.path.join(query_dir, "codemodel-v2")
    with open(query_file, "w") as f:
        pass 
        
    try:
        subprocess.run(
            ["cmake", "--preset", "ubuntu-RelWithDebInfo"], 
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        return f"CMake Configure Failed:\n{e.stderr}"
        
    reply_dir = os.path.join(build_dir, ".cmake", "api", "v1", "reply")
    codemodel_files = glob.glob(os.path.join(reply_dir, "codemodel-v2-*.json"))
    
    if not codemodel_files:
        return "Error: CMake did not generate the codemodel JSON. Check if the build directory is correct."
        
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

def run_test_executable(test_target_name: str, build_dir: str = "build/ubuntu-RelWithDebInfo") -> str:
    """
    Locates and executes the compiled test binary on Ubuntu/Linux.
    Captures the output so the agent can see if assertions passed, failed, or segfaulted.
    """
    executable_path = None
    
    for root, _, files in os.walk(build_dir):
        if test_target_name in files:
            executable_path = os.path.join(root, test_target_name)
            break
            
    if not executable_path:
        return f"Error: Could not find compiled test executable named '{test_target_name}' in {build_dir}/."
        
    try:
        st = os.stat(executable_path)
        os.chmod(executable_path, st.st_mode | stat.S_IEXEC)

        process = subprocess.run(
            [executable_path],
            capture_output=True,
            text=True,
            timeout=30 # 30 seconds
        )
        
        output = f"Test Executed: {executable_path}\nExit Code: {process.returncode}\n\n"
        output += "--- STDOUT ---\n" + process.stdout + "\n"
        
        if process.stderr:
            output += "--- STDERR ---\n" + process.stderr + "\n"
            
        if process.returncode == 0:
            return "SUCCESS: All tests passed!\n" + output
        else:
            return "FAILURE: Tests failed or crashed.\n" + output
            
    except subprocess.TimeoutExpired:
        return f"Error: Test execution timed out after 30 seconds. You might have an infinite loop in {test_target_name}."
    except Exception as e:
        return f"Error running test: {str(e)}"
