import os
from google import genai
from google.genai import types

from tools import (
    read_project_context, 
    write_test_file, 
    run_cmake_build, 
    extract_cmake_blueprint,
    search_codebase
)

client = genai.Client()

SYSTEM_INSTRUCTION = """
You are an autonomous, senior C++ software engineer specialized in CMake and testing.
Your goal is to write robust Google Tests (gtest) for existing C++ code.

Follow this strict chain of thought:
1. RUN `extract_cmake_blueprint` immediately to understand the project structure and targets.
2. RUN `read_project_context` to analyze the source code and headers.
3. WRITE the test using `write_test_file`. 
   - MOCK external dependencies using gmock.
   - UPDATE tests/CMakeLists.txt. Use ONLY target names found in the blueprint.
4. COMPILE using `run_cmake_build`.
5. IF the build fails:
   - If it's a "file not found" error, use `search_codebase` (e.g., file_pattern="*.h") to find the correct include path.
   - If it's an "undefined reference", use `search_codebase` (e.g., text_query="MyClass::MyFunction") to find where it's implemented and fix your CMake linking.
   - Fix the code and recompile. Stop when the build passes.
"""

def start_agent(target_cpp_file: str):
    print(f"Starting agent for: {target_cpp_file}")
    
    testing_tools = [
        extract_cmake_blueprint, 
        read_project_context, 
        write_test_file, 
        run_cmake_build,
        search_codebase
    ]
    
    chat = client.chats.create(
        model="gemini-2.5-pro",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=testing_tools,
            temperature=0.2, 
        )
    )

    prompt = f"Please generate and compile a unit test for {target_cpp_file}."
    response = chat.send_message(prompt)

    MAX_ITERATIONS = 7
    iteration_count = 0

    while iteration_count < MAX_ITERATIONS:
        iteration_count += 1
        
        if response.function_calls:
            function_responses = []
            
            for tool_call in response.function_calls:
                print(f"\n[Agent Action {iteration_count}/{MAX_ITERATIONS}] Executing: {tool_call.name}")
                
                try:
                    if tool_call.name == "extract_cmake_blueprint":
                        result = extract_cmake_blueprint(**tool_call.args)
                    elif tool_call.name == "read_project_context":
                        result = read_project_context(**tool_call.args)
                    elif tool_call.name == "write_test_file":
                        result = write_test_file(**tool_call.args)
                    elif tool_call.name == "run_cmake_build":
                        result = run_cmake_build(**tool_call.args)
                    elif tool_call.name == "search_codebase":
                        result = search_codebase(**tool_call.args)
                    else:
                        result = f"Error: Unknown tool {tool_call.name}"
                except Exception as e:
                    result = f"Tool execution crashed with error: {str(e)}"
                
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_call.name,
                        response={"result": result}
                    )
                )
            
            response = chat.send_message(function_responses)
            
        else:
            print("\n[Agent Finished Successfully]")
            print(response.text)
            break
            
    if iteration_count >= MAX_ITERATIONS:
        print("\n[Agent Aborted] Reached maximum iterations. The agent got stuck in a loop.")

if __name__ == "__main__":
    start_agent("todo.cpp")
    