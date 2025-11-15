import threading

import grpc
import subprocess
import os
import time
import contextlib
from typing import Union, Optional, Callable

from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

try:
    from .proto import importparser_pb2
    from .proto import importparser_pb2_grpc
except ImportError:
    raise ImportError("Could not import generated gRPC files (importparser_pb2, importparser_pb2_grpc). "
                      "Generate them using the appropriate protoc command.")
from .cli import CliImportParserClient


class GrpcRefactorClient(CliImportParserClient):
    """
    Implementation of the import parser client that interacts with the
    Java tool via its gRPC interface.

    Includes a context manager to start/stop the Java gRPC server process.
    """
    DEFAULT_SERVER_HOST = "localhost"
    DEFAULT_SERVER_PORT = 50051

    def __init__(
        self,
        directory_path: str,
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        startup_wait: Optional[int] = 1,
        startup_timeout: Optional[int] = 15,
    ):
        """
        Initializes the gRPC Refactor Client.

        Args:
            directory_path: Path to the root directory of the Java project/sources
                           (passed to gRPC calls).
            server_host: Hostname or IP address of the gRPC server. Defaults to env var IMPORT_PARSER_SERVER_PORT
                         or DEFAULT_SERVER_PORT.
            server_port: Port number of the gRPC server. Defaults to env var IMPORT_PARSER_SERVER_PORT
                         or DEFAULT_SERVER_PORT.
            startup_wait: Time to wait after starting the server process before checking health.
            startup_timeout: How long to wait after starting the server process before giving up.

        Raises:
            ValueError: If required JAR path is not configured or file/executable is not found.
        """
        # Initialize cli class
        super().__init__(directory_path=directory_path, timeout_seconds=None)

        # Get host from arg, then env var, then default
        _host_str = os.environ.get("REFACTOR_SERVER_HOST", self.DEFAULT_SERVER_HOST)
        self.server_host = server_host if server_host is not None else _host_str
        _port_int = int(os.environ.get("REFACTOR_SERVER_PORT", self.DEFAULT_SERVER_PORT))
        self.server_port = server_port if server_port is not None else _port_int
        self.server_address = f"{self.server_host}:{self.server_port}"
        self.startup_timeout = startup_timeout
        self.startup_wait = startup_wait

        self.server_process: Optional[subprocess.Popen] = None
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[importparser_pb2_grpc.ImportParserServiceStub] = None

        self._stop_event = threading.Event()
        self.stderr_thread: Optional[threading.Thread] = None

    def wait_for_server(self, interval: float = 1.0) -> bool:
        """Waits for the gRPC server to be healthy.

        Args:
            interval (float): Time interval (in seconds) between health checks.
            
        Returns:
            bool: True if the server is healthy, False otherwise.
        """
        health_client = health_pb2_grpc.HealthStub(self.channel)
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            try:
                request = health_pb2.HealthCheckRequest()
                response = health_client.Check(request, timeout=2)
                if response.status == health_pb2.HealthCheckResponse.SERVING:
                    self.logger.info("Server is healthy!")
                    return True
            except grpc.RpcError:
                self.logger.debug("Waiting for server to become healthy...")
            time.sleep(interval)
        return False

    def __enter__(self):
        """Starts the Java gRPC server process and connects the client."""
        self.logger.debug(f"Starting Java gRPC server process from JAR: {self.IMPORT_PARSER_JAR_PATH}")
        # Command to start the server JAR, passing the port
        server_command = self._build_command_base()
        server_command.append("serve")
        server_command.extend(["-p", str(self.server_port)])
        self.logger.debug(f"Server command: {' '.join(server_command)}")
        try:
            # Reset stop event for new entry
            self._stop_event.clear()
            # Start the server process without blocking
            # Capture stderr/stdout to prevent blocking and allow logging
            self.server_process = subprocess.Popen(
                server_command,
                # stdout=subprocess.PIPE,
                # stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            self.logger.debug(f"Server process started (PID: {self.server_process.pid}). ")

            # Wait for a short period to allow server to start
            if self.startup_wait:
                time.sleep(self.startup_wait)

            # Check if process exited unexpectedly during startup wait
            if self.server_process.poll() is not None:
                stderr_output = self._read_stream(self.server_process.stderr)
                stdout_output = self._read_stream(self.server_process.stdout)
                raise RuntimeError(f"Java gRPC server process exited prematurely "
                                   f"with code {self.server_process.returncode}. "
                                   f"Stderr:\n{stderr_output}\n"
                                   f"Stdout:\n{stdout_output}")

            self.logger.info(f"Connecting gRPC client to {self.server_address}...")
            # Use insecure channel for local testing, use secure channel for production
            self.channel = grpc.insecure_channel(self.server_address)
            # readiness check:
            if not self.wait_for_server():
                raise RuntimeError(f"Timeout ({self.startup_timeout}s) waiting for gRPC server to be "
                                   f"healthy at {self.server_address}")
            # try:
            #     grpc.channel_ready_future(self.channel).result(timeout=10)
            # except grpc.FutureTimeoutError:
            #     raise RuntimeError(f"Timeout waiting for gRPC channel to be ready at {self.server_address}")

            self.stub = importparser_pb2_grpc.ImportParserServiceStub(self.channel)
            self.logger.info("gRPC client connected.")
            # self.stderr_thread = threading.Thread(
            #     target=self._log_stream,
            #     args=self.server_process.stderr,
            #     daemon=True
            # )
            # self.stderr_thread.start()
            return self
        except Exception as e:
            self._cleanup()
            raise RuntimeError(f"Failed to initialize gRPC client and server: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stops the client connection and the Java gRPC server process."""
        self.logger.info("Shutting down gRPC client and server...")
        self._cleanup()
        self.logger.info("Shutdown complete.")
        return False

    def _cleanup(self):
        """Helper to close channel and terminate server process."""
        # Close gRPC channel first
        if self.channel:
            try:
                self.channel.close()
                self.logger.debug("gRPC channel closed.")
            except Exception as e:
                self.logger.warning(f"Error closing gRPC channel: {e}")
        self.channel = None
        self.stub = None

        # Signal logging threads to stop
        self._stop_event.set()
        # if self.stderr_thread.is_alive():
        #     try:
        #         # Add a timeout to prevent hanging indefinitely if a thread gets stuck
        #         self.stderr_thread.join(timeout=2.0)
        #         if self.stderr_thread.is_alive():
        #             self.logger.warning(f"Logging thread importparser did not finish within timeout.")
        #     except Exception as e:
        #         self.logger.warning(f"Error joining logging thread importparser: {e}")

        # Terminate server process
        if self.server_process and self.server_process.poll() is None:
            self.logger.debug(f"Terminating server process (PID: {self.server_process.pid})...")
            try:
                self.server_process.terminate()
                try:
                    # Wait for a short period for graceful shutdown
                    stdout, stderr = self.server_process.communicate(timeout=10)
                    self.logger.debug(f"Server process terminated with code: {self.server_process.returncode}")
                    if self.server_process.returncode not in (None, 0, 143):  # SIGTERM obeyed = 143
                        if stdout:
                            self.logger.debug(f"Server stdout on exit:\n{stdout.strip()}")
                        if stderr:
                            self.logger.debug(f"Server stderr on exit:\n{stderr.strip()}")
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"Server process (PID: {self.server_process.pid}) did not terminate gracefully "
                                        f"within timeout. Killing...")
                    self.server_process.kill()
                    stdout, stderr = self.server_process.communicate()
                    self.logger.warning(f"Server process killed (code: {self.server_process.returncode})")
                    if self.server_process.returncode not in (None, 0, 137):  # SIGKILL obeyed = 137
                        if stdout:
                            self.logger.debug(f"Server stdout on kill:\n{stdout.strip()}")
                        if stderr:
                            self.logger.debug(f"Server stderr on kill:\n{stderr.strip()}")
            except Exception as e:
                self.logger.error(f"Error terminating server process (PID: {self.server_process.pid}): {e}",
                                  exc_info=True)
        self.server_process = None

    def _log_stream(self, stream):
        """Reads lines from a stream and logs them until the stream closes or stop event is set."""
        try:
            for line in iter(stream.readline, ''):
                if self._stop_event.is_set():
                    break
                if line:
                    self.logger.debug(f"[importparser-java] {line.strip()}")
            self.logger.debug(f"logging for [mportparser-java finished.")
        except Exception as e:
            # Log exceptions occurring within the logging thread
            self.logger.error(f"Error in logging thread for importparser-java: {e}", exc_info=True)
        finally:
            try:
                stream.close()
            except Exception:
                pass  # Ignore errors during close

    def _read_stream(self, stream) -> str:
        """Non-blockingly read available data from a stream (PIPE)."""
        output = ""
        if not stream:
            return output
        try:
            # This is a simplified read, might block if data is large
            # For truly non-blocking, need threads or asyncio
            stream.flush()  # Not typically needed for read pipes
            # A simple approach for startup errors is just to read what's available
            output = stream.read()
        except Exception as e:
            self.logger.warning(f"Error reading stream: {e}")
        return output.strip() if output else ""

    def _ensure_connected(self):
        """Raises RuntimeError if the client is not connected (not within 'with' block)."""
        if not self.stub or not self.channel:
            raise RuntimeError("gRPC client is not connected. Use within a 'with' block.")

    def _parse_status(self, result: importparser_pb2.RefactorSingleResult, target_qualified_name: str):
        if result.status:
            raise RuntimeError(f"gRPC server returned error {result.status} for '{target_qualified_name}': "
                               f"{result.error_message}")
        else:
            self.logger.debug(f"gRPC 'RefactorSingle' successful for '{target_qualified_name}'.")

    def refactor_single(
        self,
        target_qualified_name: str,
        old_qualified_name: str,
        new_qualified_name: str,
        timeout_seconds: int = 60
    ) -> str:
        self._ensure_connected()
        if not all([target_qualified_name, old_qualified_name, new_qualified_name]):
            raise ValueError("All arguments for refactor_single must be non-empty.")

        request = importparser_pb2.RefactorSingleRequest(
            directory_path=self.directory_path,
            target_qualified_name=target_qualified_name,
            old_qualified_name=old_qualified_name,
            new_qualified_name=new_qualified_name
        )
        self.logger.info(f"Sending gRPC 'RefactorSingle' request for '{target_qualified_name}'")
        try:
            result: importparser_pb2.RefactorSingleResult = self.stub.RefactorSingle(request, timeout=timeout_seconds)
            # self._parse_status(result, target_qualified_name)
            return result.modified_source
        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC call failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected client error: {e}")

    def refactor_batch_target(
        self,
        target_qualified_name: str,
        replacements: Union[dict[str, str], list[tuple[str, str]]],
        timeout_seconds: int = 60
    ) -> Optional[str]:
        self._ensure_connected()
        if not target_qualified_name:
            raise ValueError("target_qualified_name must be non-empty.")
        if not replacements:
            self.logger.warning("replacements map is empty.")
            return None

        # Convert replacements to dict if needed
        if isinstance(replacements, list) and all(isinstance(item, tuple) and len(item) == 2 for item in replacements):
            replacements_dict = dict(replacements)
        elif isinstance(replacements, dict):
            replacements_dict = dict(replacements)
        else:
            raise TypeError("Replacements must be a mapping (dict) or a list of tuples.")
        if not replacements_dict:
            raise ValueError("Replacements cannot be empty after conversion.")
        replacements_map = importparser_pb2.ReplacementMap(replacements=replacements_dict)
        request = importparser_pb2.RefactorBatchTargetRequest(
            directory_path=self.directory_path,
            target_qualified_name=target_qualified_name,
            replacement_map=replacements_map
        )
        self.logger.info(f"Sending gRPC 'RefactorBatchTarget' request for '{target_qualified_name}'")
        try:
            result = self.stub.RefactorBatchTarget(request, timeout=timeout_seconds)
            # self._parse_status(result, target_qualified_name)
            return result.modified_source
        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC call failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected client error: {e}")

    def refactor_batch_all(
        self,
        replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]],
        timeout_seconds: int = 180
    ) -> dict[str, Optional[str]]:
        """
        Implements batch_all by internally collecting results from the stream.
        For true streaming processing, use refactor_batch_all_stream.
        """
        self._ensure_connected()
        self.logger.warning("Executing 'refactor_batch_all' by collecting stream results. "
                            "Use 'refactor_batch_all_stream' for true streaming processing.")

        results_dict: dict[str, Optional[str]] = {}
        errors_occurred = False

        # Define a simple callback to populate the dictionary
        def _collect_result(target_name: str, source_code: Optional[str], error_msg: Optional[str]):
            nonlocal errors_occurred
            if error_msg:
                self.logger.warning(f"Streamed error for target '{target_name}': {error_msg}")
                errors_occurred = True
            results_dict[target_name] = source_code

        try:
            # Call the streaming method with the collecting callback
            self.refactor_batch_all_stream(
                replacements_per_target=replacements_per_target,
                callback=_collect_result,
                timeout_seconds=timeout_seconds,
            )

            if errors_occurred:
                self.logger.warning("One or more targets encountered errors during 'refactor_batch_all'.")
            return results_dict
        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC call failed: {e}") from e
        except Exception as e:
            raise type(e)(f"Unexpected client error: {e}")

    def refactor_batch_all_stream(
        self,
        replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]],
        callback: Callable[[str, Optional[str], Optional[str]], None],
        timeout_seconds: int = 180,
    ) -> None:
        """
        Refactors multiple names across multiple targets, streaming results via callback.

        Args:
            replacements_per_target: Nested dictionary of replacements.
            callback: Function to call with (target_name, modified_source, error_msg) for each successful result.
            timeout_seconds: Max time for the entire streaming operation.

        Returns:
            A dictionary containing the final results {target_name: source_or_None}.
        """
        self._ensure_connected()
        if not isinstance(replacements_per_target, dict):
            raise TypeError("replacements_per_target must be a dictionary.")
        if not replacements_per_target:
            self.logger.warning("Replacements_per_target map is empty in stream call.")
            return
        if not callable(callback):
            raise TypeError("Provided 'callback' must be callable.")

        proto_replacements = {}
        for target, reps in replacements_per_target.items():
            if isinstance(reps, dict):
                proto_replacements[target] = importparser_pb2.ReplacementMap(replacements=reps)
            elif isinstance(reps, list):
                # Convert list of tuples to dict
                replacements_dict = dict(reps)
                proto_replacements[target] = importparser_pb2.ReplacementMap(replacements=replacements_dict)
            else:
                raise TypeError(f"Value for target '{target}' must be a dictionary/mapping.")

        request = importparser_pb2.RefactorAllRequest(
            directory_path=self.directory_path,
            replacements_per_target=proto_replacements
        )

        self.logger.info(f"Sending gRPC 'RefactorAllTargets' streaming request...")
        try:
            # Call the streaming RPC
            stream_results = self.stub.RefactorAllTargets(request, timeout=timeout_seconds)
            # Iterate through the stream of results from the server
            for result in stream_results:
                target_name = result.target_qualified_name
                single_result: importparser_pb2.RefactorSingleResult = result.result
                # self._parse_status(single_result, target_name)
                callback(target_name, single_result.modified_source, single_result.error_message)
            self.logger.info("gRPC 'RefactorAllTargets' stream finished.")
        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC call failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected client error: {e}")
