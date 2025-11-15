import unittest
import os
import shutil
import tempfile
import logging

from monomorph.execution.dependency.buildfile import GRPC_VERSION, PROTOBUF_VERSION, ANNOTATION_API_VERSION
from monomorph.execution.dependency.gradle import (GradleBuildFile, GRADLE_PROTOBUF_PLUGIN_VERSION)


class TestGradleBuildFileRegex(unittest.TestCase):

    def setUp(self):
        """Create a temporary directory for test files."""
        self.test_dir = tempfile.mkdtemp()
        # Suppress logging during tests unless debugging
        logging.disable(logging.CRITICAL)
        self.maxDiff = None  # Show full diff on assertion failure

    def tearDown(self):
        """Remove the temporary directory after tests."""
        shutil.rmtree(self.test_dir)
        logging.disable(logging.NOTSET)

    def _create_dummy_file(self, filename: str, content: str) -> str:
        """Helper to create a file with given content in the temp dir."""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def _read_file_content(self, filepath: str) -> str:
        """Helper to read file content."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    # --- Test Cases ---

    def test_parse_file_not_found(self):
        """Test parsing a non-existent file."""
        non_existent_file = os.path.join(self.test_dir, "non_existent.gradle")
        gradle_file = GradleBuildFile(non_existent_file, "11")
        with self.assertRaises(FileNotFoundError):
            gradle_file.parse()

    def test_has_dependency_found(self):
        """Test finding an existing dependency."""
        content = """
dependencies {
    implementation 'io.grpc:grpc-stub:1.62.2' // Existing
}
"""
        filepath = self._create_dummy_file("build_found.gradle", content)
        gradle_file = GradleBuildFile(filepath, "11")
        gradle_file.parse()
        self.assertTrue(gradle_file.has_dependency("io.grpc", "grpc-stub"))

    def test_has_dependency_not_found(self):
        """Test not finding a dependency in existing block."""
        content = """
dependencies {
    implementation 'some.other:dependency:1.0'
}
"""
        filepath = self._create_dummy_file("build_notfound.gradle", content)
        gradle_file = GradleBuildFile(filepath, "11")
        gradle_file.parse()
        self.assertFalse(gradle_file.has_dependency("io.grpc", "grpc-stub"))

    def test_has_dependency_block_missing(self):
        """Test has_dependency when the dependencies block is missing."""
        content = """
plugins { id 'java' }
"""
        filepath = self._create_dummy_file("build_noblock.gradle", content)
        gradle_file = GradleBuildFile(filepath, "11")
        gradle_file.parse()
        self.assertFalse(gradle_file.has_dependency("io.grpc", "grpc-stub"))

    def test_add_dependency_new_block(self):
        """Test adding a dependency when the block is missing."""
        content = """
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}
"""
        filepath = self._create_dummy_file("build_add_dep_noblock.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_dep_noblock_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        dep_info = {"groupId": "io.grpc", "artifactId": "grpc-core", "version": "1.62.2"}
        gradle_file.add_dependency(dep_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        expected_content_part = """
dependencies {
    implementation 'io.grpc:grpc-core:1.62.2'
}
"""
        actual_content = self._read_file_content(output_path)
        # Check if the block and dependency are present (allow flexibility in exact position)
        self.assertIn("dependencies {", actual_content)
        self.assertIn("implementation 'io.grpc:grpc-core:1.62.2'", actual_content)
        self.assertTrue(actual_content.strip().endswith("}"))  # Check block closes

    def test_add_dependency_existing_empty_block(self):
        """Test adding a dependency to an existing empty block."""
        content = """
dependencies {
}
"""
        filepath = self._create_dummy_file("build_add_dep_empty.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_dep_empty_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        dep_info = {"groupId": "io.grpc", "artifactId": "grpc-netty", "version": "1.62.2"}
        gradle_file.add_dependency(dep_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        expected_content = """
dependencies {
    implementation 'io.grpc:grpc-netty:1.62.2'
}
"""
        actual_content = self._read_file_content(output_path)
        # Use assertEqual for precise check when possible
        self.assertEqual(expected_content.strip(), actual_content.strip())

    def test_add_dependency_existing_block_with_content(self):
        """Test adding a dependency to a block with existing content."""
        content = """
dependencies {
    // A comment
    implementation 'com.google.guava:guava:30.0-jre'

} // Closing brace with comment
"""
        filepath = self._create_dummy_file("build_add_dep_content.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_dep_content_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        dep_info = {"groupId": "io.grpc", "artifactId": "grpc-protobuf", "version": GRPC_VERSION,
                    "scope": "compileOnly"}
        gradle_file.add_dependency(dep_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        # Check insertion before the closing brace
        expected_new_line = f"    compileOnly 'io.grpc:grpc-protobuf:{GRPC_VERSION}'"
        actual_content = self._read_file_content(output_path)
        self.assertIn(expected_new_line, actual_content)
        # Basic check it's roughly in the right place
        self.assertTrue(actual_content.index(expected_new_line) < actual_content.rindex("} // Closing brace"))

    def test_multi_dependency_blocks(self):
        """Test adding a dependency to a buildfile where there are multiple dependencies blocks."""
        content = """
buildscript {
  dependencies {
    classpath "com.github.spacialcircumstances:gradle-cucumber-reporting:0.1.23"
  }
}
        
dependencies {
    // A comment
    implementation 'com.google.guava:guava:30.0-jre'

} // Closing brace with comment
"""
        expected_content_template = """
buildscript {{
  dependencies {{
    classpath "com.github.spacialcircumstances:gradle-cucumber-reporting:0.1.23"
  }}
}}
        
dependencies {{
    // A comment
    implementation 'com.google.guava:guava:30.0-jre'
    compileOnly 'io.grpc:grpc-protobuf:{GRPC_VERSION}'

}} // Closing brace with comment
"""
        filepath = self._create_dummy_file("build_add_dep_content.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_dep_content_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        dep_info = {"groupId": "io.grpc", "artifactId": "grpc-protobuf", "version": GRPC_VERSION,
                    "scope": "compileOnly"}
        gradle_file.add_dependency(dep_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        # Check insertion before the closing brace
        expected_new_line = f"    compileOnly 'io.grpc:grpc-protobuf:{GRPC_VERSION}'"
        actual_content = self._read_file_content(output_path)
        self.assertIn(expected_new_line, actual_content)
        # Basic check it's roughly in the right place
        self.assertTrue(actual_content.index(expected_new_line) < actual_content.rindex("} // Closing brace"))
        # Compare the full content to ensure no changes outside the new dependency
        cleaned_content = "\n".join([line.strip() for line in actual_content.splitlines() if line.strip()])
        expected_content = "\n".join([
            line.strip() for line in expected_content_template.format(GRPC_VERSION=GRPC_VERSION).splitlines()
            if line.strip()])
        self.assertEqual(expected_content, cleaned_content)

    def test_add_dependency_already_exists(self):
        """Test adding a dependency that already exists."""
        content = """
dependencies {
    implementation 'io.grpc:grpc-stub:1.62.2'
}
"""
        filepath = self._create_dummy_file("build_add_dep_exists.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_dep_exists_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        dep_info = {"groupId": "io.grpc", "artifactId": "grpc-stub", "version": "1.62.2"}
        gradle_file.add_dependency(dep_info)

        self.assertFalse(gradle_file.is_modified)
        gradle_file.save()  # Should do nothing

        # Verify the output file wasn't created or is same as input
        self.assertFalse(os.path.exists(output_path))

    def test_has_plugin_found(self):
        """Test finding an existing plugin."""
        content = """
plugins {
    id 'java'
    id 'com.google.protobuf' version '0.9.4' // Target
}
"""
        filepath = self._create_dummy_file("build_plugin_found.gradle", content)
        gradle_file = GradleBuildFile(filepath, "11")
        gradle_file.parse()
        self.assertTrue(gradle_file.has_plugin("com.google.protobuf"))

    def test_has_plugin_not_found(self):
        """Test not finding a plugin."""
        content = """
plugins {
    id 'application'
}
"""
        filepath = self._create_dummy_file("build_plugin_notfound.gradle", content)
        gradle_file = GradleBuildFile(filepath, "11")
        gradle_file.parse()
        self.assertFalse(gradle_file.has_plugin("com.google.protobuf"))

    def test_add_plugin_new_block(self):
        """Test adding a plugin when the plugins block is missing."""
        content = """
// No plugins block here
repositories { mavenCentral() }
"""
        filepath = self._create_dummy_file("build_add_plugin_noblock.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_plugin_noblock_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        plugin_info = {"id": "com.google.protobuf", "version": "0.9.4"}
        gradle_file.add_plugin(plugin_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        expected_start = """
plugins {
    id 'com.google.protobuf' version '0.9.4'
}

// No plugins block here
"""
        actual_content = self._read_file_content(output_path)
        # Check start of file for the new block
        self.assertTrue(actual_content.strip().startswith("plugins {"))
        self.assertIn("id 'com.google.protobuf' version '0.9.4'", actual_content)

    def test_add_plugin_existing_empty_block(self):
        """Test adding a plugin to an existing empty plugins block."""
        content = """plugins {
    
}
"""
        filepath = self._create_dummy_file("build_add_plugin_empty.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_plugin_empty_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        plugin_info = {"id": "java"}  # No version
        gradle_file.add_plugin(plugin_info)

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        expected_content = """
plugins {
    
    id 'java'
}
"""
        self.assertEqual(expected_content.strip(), self._read_file_content(output_path).strip())

    def test_add_plugin_already_exists(self):
        """Test adding a plugin that already exists."""
        content = """
plugins {
    id 'java'
}
"""
        filepath = self._create_dummy_file("build_add_plugin_exists.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_plugin_exists_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        plugin_info = {"id": "java"}
        gradle_file.add_plugin(plugin_info)

        self.assertFalse(gradle_file.is_modified)
        gradle_file.save()
        self.assertFalse(os.path.exists(output_path))

    def test_add_protobuf_block_plugin_exists_block_missing(self):
        """Test adding protobuf block when plugin exists but block doesn't."""
        content = f"""
plugins {{
    id 'com.google.protobuf' version '{GRADLE_PROTOBUF_PLUGIN_VERSION}'
}}

dependencies {{}}
"""
        filepath = self._create_dummy_file("build_add_proto_block.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_proto_block_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        gradle_file.add_protobuf_block()  # Call the method

        self.assertTrue(gradle_file.is_modified)
        gradle_file.save()

        actual_content = self._read_file_content(output_path)
        self.assertIn("protobuf {", actual_content)
        self.assertIn(f"protoc {{ artifact = 'com.google.protobuf:protoc:{PROTOBUF_VERSION}' }}", actual_content)
        self.assertIn(f"artifact = 'io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}'", actual_content)
        self.assertIn("generateProtoTasks {", actual_content)
        # Check it's inserted after plugins block
        self.assertTrue(actual_content.find("protobuf {") > actual_content.find("plugins {"))

    def test_add_protobuf_block_already_exists(self):
        """Test adding protobuf block when it already exists."""
        content = f"""
plugins {{
    id 'com.google.protobuf' version '{GRADLE_PROTOBUF_PLUGIN_VERSION}'
}}

protobuf {{
    // Some existing config
}}

dependencies {{}}
"""
        filepath = self._create_dummy_file("build_add_proto_block_exists.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_proto_block_exists_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        with self.assertRaises(NotImplementedError):
            gradle_file.add_protobuf_block()  # Call the method

        self.assertFalse(gradle_file.is_modified)
        # gradle_file.save()
        # self.assertFalse(os.path.exists(output_path))

    def test_add_protobuf_block_plugin_missing(self):
        """Test adding protobuf block when the required plugin is missing."""
        content = """
plugins {
    id 'java'
}
"""
        filepath = self._create_dummy_file("build_add_proto_block_noplugin.gradle", content)
        output_path = os.path.join(self.test_dir, "build_add_proto_block_noplugin_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()

        with self.assertRaises(RuntimeError):
            gradle_file.add_protobuf_block()  # Call the method

        # self.assertFalse(gradle_file.is_modified)
        # gradle_file.save()
        # self.assertFalse(os.path.exists(output_path) or self._read_file_content(output_path) == content)

    def test_save_no_changes(self):
        """Test save when no modifications were made."""
        content = "plugins { id 'java' }"
        filepath = self._create_dummy_file("build_save_nochange.gradle", content)
        output_path = os.path.join(self.test_dir, "build_save_nochange_out.gradle")
        gradle_file = GradleBuildFile(filepath, "11", output_path=output_path)
        gradle_file.parse()
        # No modifications
        gradle_file.save()
        self.assertFalse(gradle_file.is_modified)
        self.assertFalse(os.path.exists(output_path))  # Output file shouldn't be created
