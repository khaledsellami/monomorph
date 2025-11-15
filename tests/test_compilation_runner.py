import os
import unittest
import tempfile
import pathlib
import shutil
from unittest.mock import patch, MagicMock

import docker
import dotenv

from monomorph.validation.compilation import CompilationRunner


# --- Helper function to check for Docker availability ---
def is_docker_running():
    """Checks if the Docker daemon is responsive."""
    try:
        dotenv.load_dotenv()
        CUSTOM_DOCKER_SOCKET = os.getenv("CUSTOM_DOCKER_SOCKET")
        client = docker.DockerClient(base_url=CUSTOM_DOCKER_SOCKET)
        return client.ping()
    except Exception:
        return False


# --- Test Data: Minimal valid project files ---

MAVEN_SUCCESS_POM = """
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>test-app</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
    </properties>
</project>
"""

GRADLE_SUCCESS_BUILD = """
plugins {
    id 'java'
}
group = 'com.example'
version = '1.0.0'
java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
"""

JAVA_SUCCESS_CLASS = """
package com.example;
public class App {
    public static void main(String[] args) {
        System.out.println("Hello World!");
    }
}
"""

JAVA_FAILURE_CLASS = """
package com.example;
public class App {
    public static void main(String[] args) {
        System.out.println("Hello World!") // Missing semicolon
    }
}
"""

ORIGINAL_DOCKERFILE = "FROM maven:3.9-eclipse-temurin-11-focal"


class TestCompilationRunner(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for each test."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up the temporary directory after each test."""
        shutil.rmtree(self.test_dir)

    def _create_project_structure(self, base_path, files):
        """Helper to create files and directories for a test project."""
        for file_path, content in files.items():
            full_path = pathlib.Path(base_path) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

    # --- Initialization and Validation Tests ---

    def test_init_success(self):
        """Test successful initialization with valid paths."""
        project_path = pathlib.Path(self.test_dir) / "project"
        project_path.mkdir()
        dockerfile_path = pathlib.Path(self.test_dir) / "DockerfileMR"
        dockerfile_path.write_text(ORIGINAL_DOCKERFILE)

        try:
            node = CompilationRunner(str(project_path), str(dockerfile_path))
            self.assertIsNotNone(node)
        except RuntimeError as e:
            self.fail(f"Initialization failed unexpectedly: {e}")

    def test_init_invalid_project_path(self):
        """Test initialization fails with a non-existent project path."""
        dockerfile_path = pathlib.Path(self.test_dir) / "DockerfileMR"
        dockerfile_path.touch()
        with self.assertRaisesRegex(ValueError, "Project path does not exist"):
            CompilationRunner("/non/existent/path", str(dockerfile_path))

    def test_init_invalid_dockerfile_path(self):
        """Test initialization fails with a non-existent Dockerfile path."""
        project_path = pathlib.Path(self.test_dir)
        with self.assertRaisesRegex(ValueError, "Original Dockerfile path does not exist"):
            CompilationRunner(str(project_path), "/non/existent/Dockerfile")

    @patch('docker.DockerClient')
    def test_init_docker_not_running(self, mock_from_env):
        """Test initialization fails gracefully if Docker daemon is not running."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = docker.errors.APIError("Docker not running")
        mock_from_env.return_value = mock_client

        project_path = pathlib.Path(self.test_dir)
        project_path.mkdir(exist_ok=True)
        dockerfile_path = pathlib.Path(self.test_dir) / "DockerfileMR"
        dockerfile_path.touch()

        with self.assertRaisesRegex(RuntimeError, "Could not connect to Docker daemon"):
            CompilationRunner(str(project_path), str(dockerfile_path))

    # --- Internal Logic Tests ---

    def test_extract_base_image(self):
        """Test that the FROM line is correctly extracted from a Dockerfile."""
        dockerfile_path = pathlib.Path(self.test_dir) / "DockerfileMR"
        dockerfile_path.write_text("ARG version=11\n# Some comment\nFROM maven:3.9-jdk-11\nCOPY . .")
        node = CompilationRunner(self.test_dir, str(dockerfile_path))
        base_image = node._extract_base_image()
        self.assertEqual(base_image, "FROM maven:3.9-jdk-11")

    def test_extract_base_image_not_found(self):
        """Test that an error is raised if no FROM line is found."""
        dockerfile_path = pathlib.Path(self.test_dir) / "DockerfileMR"
        dockerfile_path.write_text("COPY . .")
        node = CompilationRunner(self.test_dir, str(dockerfile_path))
        with self.assertRaisesRegex(ValueError, "Could not find a 'FROM' instruction"):
            node._extract_base_image()

    # --- Full Integration Tests ---

    @unittest.skipUnless(is_docker_running(), "Docker daemon is not running")
    def test_compile_project_maven_success(self):
        """Test a full, successful compilation of a Maven project."""
        project_path = pathlib.Path(self.test_dir)
        files = {
            "pom.xml": MAVEN_SUCCESS_POM,
            "src/main/java/com/example/App.java": JAVA_SUCCESS_CLASS,
            "DockerfileMR": ORIGINAL_DOCKERFILE,
        }
        self._create_project_structure(project_path, files)

        node = CompilationRunner(str(project_path), str(project_path / "DockerfileMR"), build_system="maven")
        success, logs = node.compile_project()

        self.assertTrue(success)
        self.assertIn("BUILD SUCCESS", logs)

    @unittest.skipUnless(is_docker_running(), "Docker daemon is not running")
    def test_compile_project_maven_failure(self):
        """Test a full, failing compilation of a Maven project."""
        project_path = pathlib.Path(self.test_dir)
        files = {
            "pom.xml": MAVEN_SUCCESS_POM,
            "src/main/java/com/example/App.java": JAVA_FAILURE_CLASS,  # Has syntax error
            "DockerfileMR": ORIGINAL_DOCKERFILE,
        }
        self._create_project_structure(project_path, files)

        node = CompilationRunner(str(project_path), str(project_path / "DockerfileMR"), build_system="maven")
        success, logs = node.compile_project()

        self.assertFalse(success)
        self.assertIn("BUILD FAILURE", logs)
        self.assertIn("Compilation failed", logs)  # Check for specific compiler output
        self.assertIn("';' expected", logs)

    @unittest.skipUnless(is_docker_running(), "Docker daemon is not running")
    def test_compile_project_gradle_success(self):
        """Test a full, successful compilation of a Gradle project."""
        project_path = pathlib.Path(self.test_dir)
        files = {
            "build.gradle": GRADLE_SUCCESS_BUILD,
            "src/main/java/com/example/App.java": JAVA_SUCCESS_CLASS,
            "DockerfileMR": "FROM gradle:8.5-jdk11-focal",  # Use a Gradle base image
        }
        self._create_project_structure(project_path, files)

        node = CompilationRunner(str(project_path), str(project_path / "DockerfileMR"), build_system="gradle")
        success, logs = node.compile_project()

        self.assertTrue(success)
        self.assertIn("BUILD SUCCESSFUL", logs)


if __name__ == '__main__':
    unittest.main()