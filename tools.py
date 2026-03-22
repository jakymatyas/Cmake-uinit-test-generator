import os
import subprocess
import glob
import json
import fnmatch
import stat


def list_directory_tree(root_dir: str = ".", max_depth: int = 4) -> str:
    """
    Lists the directory tree of the project, showing folders and files up to max_depth levels.
    Skips build artifacts, .git, and __pycache__ directories.
    Use this to understand the full project layout before generating tests.
    """
    SKIP_DIRS = {'.git', 'build', '__pycache__', '.cmake', 'node_modules', '.cache'}
    tree_lines = [f"Directory tree of: {os.path.abspath(root_dir)}\n"]

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]

        depth = dirpath.replace(root_dir, '').count(os.sep)
        if depth >= max_depth:
            dirnames.clear()
            continue

        indent = "  " * depth
        tree_lines.append(f"{indent}{os.path.basename(dirpath)}/")

        file_indent = "  " * (depth + 1)
        for f in sorted(filenames):
            tree_lines.append(f"{file_indent}{f}")

    return "\n".join(tree_lines)


def read_file_content(file_path: str) -> str:
    """
    Reads and returns the full content of any file in the project.
    Use this to read CMakeLists.txt files, headers, configs, or any source file
    that you need to understand before writing tests.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if len(content) > 50000:
            content = content[:50000] + "\n\n... [FILE TRUNCATED AT 50000 CHARS] ..."
        return f"--- {file_path} ---\n{content}"
    except Exception as e:
        return f"Error reading {file_path}: {str(e)}"


def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """
    Replaces an exact occurrence of old_text with new_text in any file.
    Use this to modify existing CMakeLists.txt files (e.g., adding add_subdirectory).
    The old_text must match exactly (including whitespace). Returns an error if not found.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_text not in content:
            return f"Error: Could not find the exact text to replace in {file_path}."
        if content.count(old_text) > 1:
            return f"Error: old_text appears multiple times in {file_path}. Make it more specific."
        new_content = content.replace(old_text, new_text, 1)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"Successfully edited {file_path}."
    except Exception as e:
        return f"Error editing {file_path}: {str(e)}"


def append_to_file(file_path: str, text_to_append: str) -> str:
    """
    Appends text to the end of an existing file, or creates it if it doesn't exist.
    Use this to add add_subdirectory(utest) to a parent CMakeLists.txt.
    """
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(text_to_append)
        return f"Successfully appended to {file_path}."
    except Exception as e:
        return f"Error appending to {file_path}: {str(e)}"


def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a file, completely overwriting it if it exists or creating it if it doesn't.
    Use this to fix corrupted files (e.g., a utest/CMakeLists.txt with duplicate entries).
    Creates parent directories if needed.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote {file_path}."
    except Exception as e:
        return f"Error writing {file_path}: {str(e)}"

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
    Manages utest/CMakeLists.txt: replaces existing config for this target or appends if new.
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
    marker = f"# --- Auto-generated test for {base_name} ---"
    new_block = f"{marker}\n{cmake_content_to_append}"

    if os.path.exists(cmake_filepath):
        with open(cmake_filepath, 'r') as f:
            existing = f.read()

        if marker in existing:
            # Replace the existing block for this target
            import re
            pattern = re.escape(marker) + r'.*?(?=\n# --- Auto-generated test for |\Z)'
            new_content = re.sub(pattern, new_block, existing, count=1, flags=re.DOTALL)
            with open(cmake_filepath, 'w') as f:
                f.write(new_content)
        else:
            with open(cmake_filepath, 'a') as f:
                f.write(f"\n\n{new_block}")
    else:
        with open(cmake_filepath, 'w') as f:
            f.write(f"# Auto-generated CMakeLists for {os.path.basename(parent_dir)} tests\n\n")
            f.write(new_block)

    # Ensure the parent CMakeLists.txt includes the utest subdirectory
    parent_cmake = os.path.join(parent_dir, "CMakeLists.txt")
    if os.path.exists(parent_cmake):
        with open(parent_cmake, 'r') as f:
            parent_content = f.read()
        if "add_subdirectory(utest)" not in parent_content:
            with open(parent_cmake, 'a') as f:
                f.write("\n\nadd_subdirectory(utest)\n")
            result_msg = f"Successfully wrote {test_filepath}, appended to {cmake_filepath}, and added add_subdirectory(utest) to {parent_cmake}"
        else:
            result_msg = f"Successfully wrote {test_filepath} and appended to {cmake_filepath} (add_subdirectory(utest) already present in {parent_cmake})"
    else:
        result_msg = f"Successfully wrote {test_filepath} and appended to {cmake_filepath}. WARNING: No CMakeLists.txt found at {parent_cmake} — you may need to manually add add_subdirectory(utest)."

    return result_msg

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
        full_output = (e.stdout or "") + "\n" + (e.stderr or "")
        lines = full_output.splitlines()

        error_lines = []
        for i, line in enumerate(lines):
            if any(marker in line for marker in [' error:', ' error ', 'undefined reference', 'No such file',
                                                  'fatal error', 'ld returned', 'ninja: build stopped',
                                                  'was not declared', 'no matching function',
                                                  'cannot convert', 'no member named']):
                start = max(0, i - 2)
                for ctx_line in lines[start:i + 1]:
                    if ctx_line not in error_lines:
                        error_lines.append(ctx_line)

        if not error_lines:
            error_lines = lines[-80:]

        if len(error_lines) > 150:
            error_lines = error_lines[:150]
            error_lines.append(f"\n... [{len(lines) - 150} more lines omitted]")

        failed_target = target_name if target_name else "all"
        error_msg = f"Build FAILED for target '{failed_target}'.\nExit Code: {e.returncode}\n\n"
        error_msg += "\n".join(error_lines)
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
            timeout=1 # 1 second
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
