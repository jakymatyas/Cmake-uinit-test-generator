from google import genai
from google.genai import types
from google.genai.errors import ClientError

import re
import time


def _send_with_retry(chat, message, max_retries=5):
    """Sends a message to the chat, retrying on 429 rate limit errors with backoff."""
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except ClientError as e:
            if e.status_code == 429:
                match = re.search(r'retry in ([\d.]+)s', str(e), re.IGNORECASE)
                wait = float(match.group(1)) + 1 if match else 15 * (attempt + 1)
                print(f"\n[Rate limited] Retrying in {wait:.0f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Max retries exceeded for rate limit.")

from tools import (
    list_directory_tree,
    read_file_content,
    write_file,
    edit_file,
    append_to_file,
    extract_cmake_blueprint,
    read_project_context,
    write_test_file,
    run_cmake_build,
    search_codebase,
    run_test_executable
)

SYSTEM_INSTRUCTION = """
You are an autonomous, senior C++ software engineer specialized in CMake, GoogleTest, and Conan.
Your goal is to write robust, meaningful Google Tests (gtest) for existing C++ code on Ubuntu.

## Project Conventions
- Code lives in `src/`, `include/`, and `utest/` directories.
- Test files are named `UT_<filename>.cpp` and placed in the `utest/` directory next to `src/`.
- The project uses CMake Presets targeting 'ubuntu-RelWithDebInfo'.
- The `write_test_file` tool automatically adds `add_subdirectory(utest)` to the parent CMakeLists.txt.

## Strict Workflow (follow this order — DO NOT SKIP ANY STEP)
1. RUN `list_directory_tree` to understand the full project layout. DO NOT SKIP THIS.
2. RUN `extract_cmake_blueprint` to discover all CMake targets available for linking. DO NOT SKIP THIS.
3. RUN `read_project_context` on the target .cpp file to get the source, header, and root CMakeLists. DO NOT SKIP THIS.
4. READ any additional files you need (base classes, dependencies, types, configs) using `read_file_content`.
   - Always read ALL headers included by the target file.
   - Read the CMakeLists.txt in the same directory as the target file.
   - Read any struct/class definitions used in the code so you understand the full API.
5. ONLY AFTER completing steps 1-4, WRITE the test using `write_test_file`:
   - Target names MUST start with `UT_` (e.g., `UT_d500_parser`).
   - Link against GTest::gtest_main, GTest::gmock, and the relevant library targets.
   - The tool handles placement and `add_subdirectory`.
6. COMPILE using `run_cmake_build` with the exact target name.
7. IF build fails: use `search_codebase`, `read_file_content` to fix issues in your TEST code, then rewrite with `write_test_file` and recompile.
   - Do NOT use `edit_file` to modify the project's existing source files or CMakeLists.txt.
   - Only use `edit_file` on files YOU created (utest/ directory).
   - If the same error persists after 2 attempts, stop and report the issue.
8. ONCE compiled: RUN the test using `run_test_executable`.
9. IF tests fail: fix the test, rewrite with `write_test_file`, recompile, re-run. Stop only on SUCCESS.

## Test Quality Rules (MANDATORY)
- NEVER write trivial tests. Every TEST must exercise real code and assert on real behavior.
- BANNED assertions: SUCCEED(), EXPECT_TRUE(true), EXPECT_FALSE(false), EXPECT_EQ(1,1), or any assertion
  that does not depend on the code under test. These are worthless and MUST NOT appear.
- NEVER generate comments in the test code. No inline comments, no block comments, no TODO comments.
  The test names and assertions must be self-documenting. Zero comments in the output .cpp file.
- NEVER guess at APIs. Read the actual header files to know the exact method signatures, types, and access levels.
- If a method is private, test it through the public API that exercises it.
- You MUST read ALL #include'd headers from the target .cpp file using `read_file_content` before writing any test.
  You need to understand every type, struct, enum, and class used in the code.
- Test edge cases: empty input, boundary values, overflow, error conditions.
- Use EXPECT_* (not ASSERT_*) for non-fatal checks. Use ASSERT_* only when continuing is meaningless.
- Keep tests focused: one logical behavior per TEST.
- Use descriptive test names: TEST(ParserTest, ReturnsEmptyFrameForZeroLengthInput).
- Do NOT add any comments to the generated C++ code. Not even one-liners. Let the code speak for itself.
- Use helper functions to create test data rather than inline setup in every test.

## What Good Tests Look Like
- Test that methods return correct results for known inputs with specific expected values.
- Test edge cases: empty input, null pointers, zero-length buffers, boundary values, overflow, wraparound.
- Test that state-modifying methods (reset, clear, init) actually change observable behavior.
  e.g., add data, reset, verify the object behaves as freshly constructed.
- Test error conditions: invalid input, out-of-range values, malformed data.
- Construct real input data with known values and verify outputs have correct computed results.
- NEVER write a test that doesn't call any method on the class under test.
"""


def _build_tool_map():
    """Returns a dict mapping tool name -> function for dispatch."""
    tools = [
        list_directory_tree,
        read_file_content,
        write_file,
        edit_file,
        append_to_file,
        extract_cmake_blueprint,
        read_project_context,
        write_test_file,
        run_cmake_build,
        search_codebase,
        run_test_executable,
    ]
    return {func.__name__: func for func in tools}


def start_agent(target_cpp_file: str):
    print(f"Starting agent for: {target_cpp_file}")
    client = genai.Client()

    tool_map = _build_tool_map()
    tool_functions = list(tool_map.values())

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tool_functions,
            temperature=0.2,
        )
    )

    prompt = f"Please generate and compile a unit test for {target_cpp_file}."
    response = _send_with_retry(chat, prompt)

    MAX_ITERATIONS = 20
    iteration_count = 0
    consecutive_same_tool = 0
    last_tool_name = None

    while iteration_count < MAX_ITERATIONS:
        iteration_count += 1

        if response.function_calls:
            function_responses = []
            current_tool_names = [tc.name for tc in response.function_calls]

            if len(current_tool_names) == 1 and current_tool_names[0] == last_tool_name:
                consecutive_same_tool += 1
            else:
                consecutive_same_tool = 0
            last_tool_name = current_tool_names[0] if len(current_tool_names) == 1 else None

            if consecutive_same_tool >= 3:
                print(f"\n[Loop detected] Agent called '{last_tool_name}' {consecutive_same_tool + 1} times in a row. Aborting.")
                break

            for tool_call in response.function_calls:
                print(f"\n[Agent Action {iteration_count}/{MAX_ITERATIONS}] Executing: {tool_call.name}")

                func = tool_map.get(tool_call.name)
                if func:
                    try:
                        result = func(**tool_call.args)
                    except Exception as e:
                        result = f"Tool execution crashed with error: {str(e)}"
                else:
                    result = f"Error: Unknown tool '{tool_call.name}'"

                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_call.name,
                        response={"result": result}
                    )
                )

            response = _send_with_retry(chat, function_responses)

        else:
            print("\n[Agent Finished Successfully]")
            print(response.text)
            break

    if iteration_count >= MAX_ITERATIONS:
        print("\n[Agent Aborted] Reached maximum iterations. The agent got stuck in a loop.")