import unittest
import tempfile
import pathlib
import os
import subprocess
from typing import Dict, Optional

import grpc

# Adjust if necessary
from monomorph.assembly.imports.grpc import GrpcRefactorClient
from .import_test_examples import *


# Check for Java and JAR availability
SKIP_TESTS = False
JAVA_EXEC = "java"
JAR_PATH = GrpcRefactorClient.IMPORT_PARSER_JAR_PATH
try:
    # Check JAVA_EXEC first
    _java_exec_path = os.environ.get("JAVA_EXEC_PATH")
    if _java_exec_path:
        JAVA_EXEC = _java_exec_path
    # Run java -version to check runtime presence and basic functionality
    subprocess.run([JAVA_EXEC, "-version"], check=True, capture_output=True, timeout=10)
    # Check IMPORT_PARSER_JAR_PATH
    if not GrpcRefactorClient.IMPORT_PARSER_JAR_PATH.exists():
        raise ValueError("GrpcRefactorClient cannot find IMPORT_PARSER_JAR_PATH internally.")
except (ValueError, FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
    SKIP_TESTS = True
except Exception as e:
     SKIP_TESTS = True


@unittest.skipIf(SKIP_TESTS, "Skipping gRPC integration tests: Java runtime or parser JAR not configured/found.")
class TestGrpcRefactorClientIntegration(unittest.TestCase):

    # Define constants for FQNs used in tests
    TARGET_PROCESSOR = "com.app.Processor"
    TARGET_USER = "com.app.User"
    TARGET_ADMIN = "com.app.Admin"
    TARGET_NONEXISTENT = "com.nonexistent.Service"

    OLD_UTIL = "com.old.Util"
    NEW_UTIL = "com.newpkg.Utility"
    OLD_DATA = "com.old.Data"
    NEW_DATA = "org.changed.pkg.Info"
    OLD_TARGETCLASS = "com.old.TargetClass"
    NEW_TARGETCLASS = "com.newpkg.Target"
    OLD_CONFIG = "com.old.Config"
    NEW_CONFIG = "com.shared.Settings"

    def _normalize(self, code: Optional[str]) -> str:
        """Normalize whitespace and line endings for comparison."""
        if code is None:
            return ""
        # Replace Windows line endings, remove leading/trailing whitespace per line,
        # filter out empty lines, and join with single newlines.
        lines = code.replace('\r\n', '\n').split('\n')
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        normalized = "\n".join(non_empty_lines)
        return normalized.strip()

    def _write_files(self, root_dir: pathlib.Path, files_map: Dict[str, str]):
        """Helper to write multiple source files."""
        for relative_path, content in files_map.items():
            full_path = root_dir / relative_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')

    # --- Tests for refactor_single ---

    def test_refactor_single_success(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/Util.java": SOURCE_OLD_UTIL,
                "com/old/Data.java": SOURCE_OLD_DATA,
                "com/app/Processor.java": SOURCE_PROCESSOR_USES_UTIL_DATA
            })

            try:
                # Use context manager to start/stop server and connect
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    actual_output = client.refactor_single(
                        target_qualified_name=self.TARGET_PROCESSOR,
                        old_qualified_name=self.OLD_UTIL,
                        new_qualified_name=self.NEW_UTIL
                    )

                self.assertIsNotNone(actual_output)
                self.assertEqual(
                    self._normalize(EXPECTED_PROCESSOR_SINGLE_UTIL_REPLACED),
                    self._normalize(actual_output)
                )
                self.assertIn(f"import {self.NEW_UTIL};", actual_output)
                self.assertNotIn(f"import {self.OLD_UTIL};", actual_output)
                self.assertIn(f"import {self.OLD_DATA};", actual_output) # Ensure other import remains

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_single_target_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/Util.java": SOURCE_OLD_UTIL,
            })

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    # Target doesn't exist
                    actual_output = client.refactor_single(
                        target_qualified_name=self.TARGET_NONEXISTENT,
                        old_qualified_name=self.OLD_UTIL,
                        new_qualified_name=self.NEW_UTIL
                    )
                # Server returns null/empty source if target not found
                # The Python client currently returns the modified_source directly
                self.assertEqual("", actual_output, "Expected empty string when target not found.")
                # TODO: Ideally, check result.status or error_message when client parses them

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_single_invalid_args(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                with self.assertRaisesRegex(ValueError, "All arguments.*must be non-empty"):
                    client.refactor_single("", self.OLD_UTIL, self.NEW_UTIL)
                with self.assertRaisesRegex(ValueError, "All arguments.*must be non-empty"):
                    client.refactor_single(self.TARGET_PROCESSOR, "", self.NEW_UTIL)
                with self.assertRaisesRegex(ValueError, "All arguments.*must be non-empty"):
                    client.refactor_single(self.TARGET_PROCESSOR, self.OLD_UTIL, "")

    # --- Tests for refactor_batch_target ---

    def test_refactor_batch_target_success(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/Util.java": SOURCE_OLD_UTIL,
                "com/old/Data.java": SOURCE_OLD_DATA,
                "com/app/Processor.java": SOURCE_PROCESSOR_USES_UTIL_DATA
            })

            replacements = {
                self.OLD_UTIL: self.NEW_UTIL,
                self.OLD_DATA: self.NEW_DATA
            }

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    actual_output = client.refactor_batch_target(
                        target_qualified_name=self.TARGET_PROCESSOR,
                        replacements=replacements
                    )

                self.assertIsNotNone(actual_output)
                self.assertEqual(
                    self._normalize(EXPECTED_PROCESSOR_BATCH_REPLACED),
                    self._normalize(actual_output)
                )
                self.assertIn(f"import {self.NEW_UTIL};", actual_output)
                self.assertIn(f"import {self.NEW_DATA};", actual_output)
                self.assertNotIn(f"import {self.OLD_UTIL};", actual_output)
                self.assertNotIn(f"import {self.OLD_DATA};", actual_output)

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_target_empty_replacements(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            source_content = SOURCE_PROCESSOR_USES_UTIL_DATA
            self._write_files(temp_dir, {
                "com/old/Util.java": SOURCE_OLD_UTIL,
                "com/old/Data.java": SOURCE_OLD_DATA,
                "com/app/Processor.java": source_content
            })

            replacements = {} # Empty dict

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    actual_output = client.refactor_batch_target(
                        target_qualified_name=self.TARGET_PROCESSOR,
                        replacements=replacements
                    )

                self.assertIsNone(actual_output, "Expected None when replacements are empty.")
            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_target_target_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {"com/old/Util.java": SOURCE_OLD_UTIL})
            replacements = {self.OLD_UTIL: self.NEW_UTIL}

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    actual_output = client.refactor_batch_target(
                        target_qualified_name=self.TARGET_NONEXISTENT,
                        replacements=replacements
                    )
                # Expect empty string as target won't be found by server
                self.assertEqual("", actual_output, "Expected empty string when target not found.")
                # TODO: Check status/error if client parsed them

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_target_invalid_args(self):
        repl = {self.OLD_UTIL: self.NEW_UTIL}
        with tempfile.TemporaryDirectory() as temp_dir_str:
            with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                with self.assertRaisesRegex(ValueError, "target_qualified_name.*non-empty"):
                    client.refactor_batch_target("", repl)
                # Empty replacements dict is now handled in a separate test, checking expected output.
                # Let's test None replacements
                result = client.refactor_batch_target(self.TARGET_PROCESSOR, None) # type: ignore
                self.assertIsNone(result, "Expected None when replacements are None.")
                # Invalid replacement types
                with self.assertRaises(TypeError):
                    client.refactor_batch_target(self.TARGET_PROCESSOR, ["a", "b"]) # type: ignore
                # Invalid content in map (tested by Java server, client might not validate this deep)
                # For client-side, check basic structure. Server handles content errors.

    # --- Tests for refactor_batch_all (and _stream implicitly) ---

    def test_refactor_batch_all_success(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/TargetClass.java": SOURCE_OLD_TARGETCLASS,
                "com/old/Config.java": SOURCE_OLD_CONFIG,
                "com/app/User.java": SOURCE_USER_USES_TARGET_CONFIG,
                "com/app/Admin.java": SOURCE_ADMIN_USES_CONFIG
            })

            replacements_per_target = {
                self.TARGET_USER: {
                    self.OLD_TARGETCLASS: self.NEW_TARGETCLASS,
                    self.OLD_CONFIG: self.NEW_CONFIG
                },
                self.TARGET_ADMIN: {
                    self.OLD_CONFIG: self.NEW_CONFIG
                    # No TargetClass replacement for Admin
                }
            }

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    # Test the collecting wrapper method first
                    results_dict = client.refactor_batch_all(
                        replacements_per_target=replacements_per_target
                    )

                self.assertIsNotNone(results_dict)
                self.assertEqual(2, len(results_dict), "Should have results for 2 targets")
                self.assertIn(self.TARGET_USER, results_dict)
                self.assertIn(self.TARGET_ADMIN, results_dict)

                self.assertEqual(
                    self._normalize(EXPECTED_USER_REPLACED),
                    self._normalize(results_dict.get(self.TARGET_USER)),
                    "User source mismatch"
                )
                self.assertEqual(
                    self._normalize(EXPECTED_ADMIN_REPLACED),
                    self._normalize(results_dict.get(self.TARGET_ADMIN)),
                    "Admin source mismatch"
                )

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")


    def test_refactor_batch_all_stream_success(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/TargetClass.java": SOURCE_OLD_TARGETCLASS,
                "com/old/Config.java": SOURCE_OLD_CONFIG,
                "com/app/User.java": SOURCE_USER_USES_TARGET_CONFIG,
                "com/app/Admin.java": SOURCE_ADMIN_USES_CONFIG
            })

            replacements_per_target = {
                self.TARGET_USER: [ # Test with list of tuples
                    (self.OLD_TARGETCLASS, self.NEW_TARGETCLASS),
                    (self.OLD_CONFIG, self.NEW_CONFIG)
                ],
                self.TARGET_ADMIN: { # Test with dict
                    self.OLD_CONFIG: self.NEW_CONFIG
                }
            }

            # Use a dict to collect results from the callback
            collected_results: Dict[str, Optional[str]] = {}
            collected_errors: Dict[str, Optional[str]] = {}

            def _collect_callback(target_name: str, source_code: Optional[str], error_msg: Optional[str]):
                nonlocal collected_results, collected_errors
                collected_results[target_name] = source_code
                if error_msg:
                    collected_errors[target_name] = error_msg

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    # Test the streaming method directly
                    client.refactor_batch_all_stream(
                        replacements_per_target=replacements_per_target,
                        callback=_collect_callback
                    )

                self.assertEqual(0, len(collected_errors), f"No errors expected, but got: {collected_errors}")
                self.assertEqual(2, len(collected_results), "Should have collected results for 2 targets")
                self.assertIn(self.TARGET_USER, collected_results)
                self.assertIn(self.TARGET_ADMIN, collected_results)

                self.assertEqual(
                    self._normalize(EXPECTED_USER_REPLACED),
                    self._normalize(collected_results.get(self.TARGET_USER)),
                    "User source mismatch (stream)"
                )
                self.assertEqual(
                    self._normalize(EXPECTED_ADMIN_REPLACED),
                    self._normalize(collected_results.get(self.TARGET_ADMIN)),
                    "Admin source mismatch (stream)"
                )

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_all_partial_target_match(self):
         with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            self._write_files(temp_dir, {
                "com/old/TargetClass.java": SOURCE_OLD_TARGETCLASS,
                "com/old/Config.java": SOURCE_OLD_CONFIG,
                "com/app/User.java": SOURCE_USER_USES_TARGET_CONFIG
                # Admin.java is missing
            })

            replacements_per_target = {
                self.TARGET_USER: {
                    self.OLD_TARGETCLASS: self.NEW_TARGETCLASS,
                    self.OLD_CONFIG: self.NEW_CONFIG
                },
                self.TARGET_NONEXISTENT: { # Target file doesn't exist
                    self.OLD_CONFIG: self.NEW_CONFIG
                }
            }

            collected_results: Dict[str, Optional[str]] = {}
            collected_errors: Dict[str, Optional[str]] = {}
            def _collect_callback(target_name: str, source_code: Optional[str], error_msg: Optional[str]):
                collected_results[target_name] = source_code
                if error_msg: collected_errors[target_name] = error_msg

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    client.refactor_batch_all_stream(
                        replacements_per_target=replacements_per_target,
                        callback=_collect_callback
                    )

                self.assertEqual(2, len(collected_results), "Should receive results/status for all requested targets")
                self.assertIn(self.TARGET_USER, collected_results)
                self.assertIn(self.TARGET_NONEXISTENT, collected_results)

                # Check User output (should be modified)
                self.assertEqual(
                    self._normalize(EXPECTED_USER_REPLACED),
                    self._normalize(collected_results.get(self.TARGET_USER)),
                    "User source mismatch (partial match test)"
                )
                # Check NonExistent output (should be empty/None with error)
                self.assertIn(self.TARGET_NONEXISTENT, collected_errors, "Non-existent target should have generated an error message")
                self.assertTrue(collected_results.get(self.TARGET_NONEXISTENT) is None or collected_results.get(self.TARGET_NONEXISTENT) == "",
                                "Source for non-existent target should be None or empty")

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")


    def test_refactor_batch_all_empty_inner_map(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            user_source = SOURCE_USER_USES_TARGET_CONFIG
            self._write_files(temp_dir, {
                "com/old/TargetClass.java": SOURCE_OLD_TARGETCLASS,
                "com/old/Config.java": SOURCE_OLD_CONFIG,
                "com/app/User.java": user_source,
                "com/app/Admin.java": SOURCE_ADMIN_USES_CONFIG
            })

            replacements_per_target = {
                self.TARGET_USER: {}, # Empty replacements for User
                self.TARGET_ADMIN: {
                    self.OLD_CONFIG: self.NEW_CONFIG
                }
            }

            collected_results: Dict[str, Optional[str]] = {}
            collected_errors: Dict[str, Optional[str]] = {}
            def _collect_callback(target_name: str, source_code: Optional[str], error_msg: Optional[str]):
                collected_results[target_name] = source_code
                if error_msg: collected_errors[target_name] = error_msg

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    client.refactor_batch_all_stream(
                        replacements_per_target=replacements_per_target,
                        callback=_collect_callback
                    )

                self.assertEqual(2, len(collected_results), "Should receive results for both targets")
                self.assertIn(self.TARGET_USER, collected_results)
                self.assertIn(self.TARGET_ADMIN, collected_results)

                # Check User: Java impl returns null -> gRPC likely empty source
                # Check if an error message indicates 'no replacements' or similar
                self.assertTrue(collected_results.get(self.TARGET_USER) is None or collected_results.get(self.TARGET_USER) == "",
                                "User source should be None or empty when inner map is empty")
                # Optionally check collected_errors[self.TARGET_USER] if server sends one

                # Check Admin (should be modified)
                self.assertEqual(
                    self._normalize(EXPECTED_ADMIN_REPLACED),
                    self._normalize(collected_results.get(self.TARGET_ADMIN)),
                    "Admin source mismatch (empty inner map test)"
                )
                self.assertNotIn(self.TARGET_ADMIN, collected_errors)


            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_all_empty_outer_map(self):
         with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            # Write some files, though they won't be processed
            self._write_files(temp_dir, {"com/app/User.java": SOURCE_USER_USES_TARGET_CONFIG})

            replacements_per_target = {} # Empty outer map

            collected_results: Dict[str, Optional[str]] = {}
            def _collect_callback(target_name: str, source_code: Optional[str], error_msg: Optional[str]):
                collected_results[target_name] = source_code # Should not be called

            try:
                with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                    # Test stream method
                    client.refactor_batch_all_stream(
                        replacements_per_target=replacements_per_target,
                        callback=_collect_callback
                    )
                    # Test collecting method
                    results_dict = client.refactor_batch_all(
                        replacements_per_target=replacements_per_target
                    )

                self.assertEqual(0, len(collected_results), "Callback should not have been called for empty outer map")
                self.assertEqual({}, results_dict, "Collecting method should return empty dict for empty outer map")

            except grpc.RpcError as e:
                self.fail(f"gRPC call failed unexpectedly: {e}")
            except RuntimeError as e:
                self.fail(f"Client setup or execution failed: {e}")

    def test_refactor_batch_all_invalid_args(self):
        with self.assertRaises(FileNotFoundError):
            GrpcRefactorClient(directory_path="dummy_path")
        with tempfile.TemporaryDirectory() as temp_dir_str:
            valid_inner = {self.OLD_UTIL: self.NEW_UTIL}

            with GrpcRefactorClient(directory_path=temp_dir_str) as client:
                # Client-side validation
                with self.assertRaises(TypeError): # Outer must be dict
                    client.refactor_batch_all_stream([], lambda a,b,c: None) # type: ignore
                with self.assertRaises(TypeError): # Inner must be dict or list[tuple]
                    client.refactor_batch_all_stream({self.TARGET_USER: "invalid"}, lambda a,b,c: None) # type: ignore
                with self.assertRaises(TypeError): # Callback must be callable
                    client.refactor_batch_all_stream({self.TARGET_USER: valid_inner}, None) # type: ignore

                # Test collecting wrapper validation
                with self.assertRaises(TypeError):
                    client.refactor_batch_all([]) # type: ignore
                with self.assertRaises(TypeError):
                    client.refactor_batch_all({self.TARGET_USER: "invalid"})

