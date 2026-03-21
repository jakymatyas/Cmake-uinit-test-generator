from google import genai
from google.genai import types

import time

from tools import (
    extract_cmake_blueprint,
    read_project_context,
    write_test_file,
    run_cmake_build,
    search_codebase,
    run_test_executable
)

SYSTEM_INSTRUCTION = """
You are an autonomous, senior C++ software engineer specialized in CMake, GoogleTest, and Conan.
Your goal is to write robust Google Tests (gtest) for existing C++ code on an Ubuntu environment.

The project structure separates code into `src/`, `include/`, and `utest/` directories.
Test files must be named exactly `UT_<filename>.cpp`.
The project uses CMake Presets. We are specifically targeting 'ubuntu-RelWithDebInfo'.

Follow this strict chain of thought:
1. RUN `extract_cmake_blueprint` immediately to understand the project structure and targets.
2. RUN `read_project_context` on the target cpp file to analyze the source code and headers.
3. WRITE the test using `write_test_file`. 
   - Pass the original target_cpp_path. The tool will place it in `utest/` and prepend `UT_`.
   - Provide EXACT CMake commands to build the test (e.g., add_executable, target_link_libraries). 
   - Target names MUST start with `UT_` (e.g., `UT_MyClass`).
   - Link against GTest::gtest, GTest::gmock, and the main library targets.
4. COMPILE using `run_cmake_build`. 
   - MUST pass the exact `target_name` defined in step 3 (e.g., `target_name="UT_MyClass"`).
5. IF the build fails:
   - Use `search_codebase` to find missing includes or undefined references.
   - Fix the code and recompile. 
6. ONCE COMPILED, RUN the test using `run_test_executable`.
   - Pass the same target name.
   - Fix failing assertions, recompile, and re-run. Stop only on SUCCESS.
"""

def start_agent(target_cpp_file: str):
    print(f"Starting agent for: {target_cpp_file}")
    client = genai.Client()
    
    testing_tools = [
        extract_cmake_blueprint, 
        read_project_context, 
        write_test_file, 
        run_cmake_build,
        search_codebase,
        run_test_executable
    ]
    
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=testing_tools,
            temperature=0.2, 
        )
    )

    prompt = f"Please generate and compile a unit test for {target_cpp_file}."
    response = chat.send_message(prompt)

    MAX_ITERATIONS = 10
    iteration_count = 0

    while iteration_count < MAX_ITERATIONS:
        iteration_count += 1
        
        if response.function_calls:
            function_responses = []
            
            for tool_call in response.function_calls:
                print(f"\n[Agent Action {iteration_count}/{MAX_ITERATIONS}] Executing: {tool_call.name}")
                
                try:
                    if tool_call.name == "extract_cmake_blueprint": result = extract_cmake_blueprint(**tool_call.args)
                    elif tool_call.name == "read_project_context": result = read_project_context(**tool_call.args)
                    elif tool_call.name == "write_test_file": result = write_test_file(**tool_call.args)
                    elif tool_call.name == "run_cmake_build": result = run_cmake_build(**tool_call.args)
                    elif tool_call.name == "search_codebase": result = search_codebase(**tool_call.args)
                    elif tool_call.name == "run_test_executable": result = run_test_executable(**tool_call.args)
                    else: result = f"Error: Unknown tool {tool_call.name}"
                except Exception as e:
                    result = f"Tool execution crashed with error: {str(e)}"
                
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_call.name,
                        response={"result": result}
                    )
                )
            
            print(f"\n[Sleeping for 15 seconds to respect free tier API limits...]")
            time.sleep(15)

            response = chat.send_message(function_responses)
            
        else:
            print("\n[Agent Finished Successfully]")
            print(response.text)
            break
            
    if iteration_count >= MAX_ITERATIONS:
        print("\n[Agent Aborted] Reached maximum iterations. The agent got stuck in a loop.")