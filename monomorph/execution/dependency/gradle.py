from typing import Any, Optional
import re

from .buildfile import BuildFile, PROTOBUF_VERSION, GRPC_VERSION, MAPSTRUCT_VERSION

# --- Gradle specific constants ---
GRADLE_PROTOBUF_PLUGIN_VERSION = "0.9.4"
# GRADLE_OSDETECTOR_PLUGIN_VERSION = "1.7.3"


# --- Gradle specific plugins ---
REQUIRED_GRADLE_PLUGINS = [
     # {
     #    "id": "com.google.osdetector",
     #    "version": GRADLE_OSDETECTOR_PLUGIN_VERSION
     # },
     {
         "id": "com.google.protobuf",
         "version": GRADLE_PROTOBUF_PLUGIN_VERSION
     }
]

# --- Gradle specific dependencies ---
REQUIRED_GRADLE_PLUGINS_SERVER_DEPENDENCIES = [
    # MapStruct specific dependency for gradle (the processor)
    {"groupId": "org.mapstruct",
     "artifactId": "mapstruct-processor",
     "version": MAPSTRUCT_VERSION,
        "scope": "annotationProcessor"
     }
]


class GradleBuildFile(BuildFile):
    """Implementation of BuildFile for Gradle build.gradle files (Groovy)."""

    def __init__(self, path: str, java_version: str, output_path: Optional[str] = None, mode: str = "client"):
        super().__init__(path, java_version, output_path, mode)
        self._content: list[str] = []  # Store lines of the file

    def parse(self) -> None:
        """Loads the build.gradle file content."""
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self._content = f.readlines()
            self.logger.debug(f"Successfully parsed {self.path}")
        except FileNotFoundError:
            self.logger.error(f"File not found at {self.path}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading file {self.path}: {e}")
            raise

    def save(self, backup: bool = False) -> None:
        """Saves the modified build.gradle content."""
        if not self._content:
            self.logger.error("Gradle file not parsed. Cannot save.")
            return
        if not self.is_modified:
            self.logger.debug("No changes detected. File not saved.")
            return
        if backup:
            self.create_backup()
        self.logger.info(f"Writing changes to {self.output_path}...")
        try:
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.writelines(self._content)
            self.logger.info("Save complete.")
        except Exception as e:
            self.logger.error(f"Error writing file {self.output_path}: {e}")
            raise
        self.delete_backup()

    def _find_first_block_lines(self, block_name: str) -> Optional[tuple[int, int]]:
        """Find start and end line indices of the first occurrence of a top-level block."""
        start_line = -1
        brace_level = 0
        block_pattern = re.compile(r"^\s*" + re.escape(block_name) + r"\s*\{")

        for i, line in enumerate(self._content):
            if start_line == -1 and block_pattern.search(line):
                start_line = i
                brace_level += line.count('{')
                brace_level -= line.count('}')
                if brace_level <= 0 and '{' in line:  # Handle block on single line
                    return start_line, start_line
            elif start_line != -1:
                brace_level += line.count('{')
                brace_level -= line.count('}')
                if brace_level <= 0:
                    return start_line, i
        return None  # Block not found or incomplete

    def _find_all_block_occurrences(self, block_name: str) -> list[dict[str, int]]:
        """Finds all occurrences of a named block, returning their start, end, and nesting level."""
        occurrences = []
        block_pattern = re.compile(r"^\s*" + re.escape(block_name) + r"\s*\{")
        i = 0
        current_level = 0
        while i < len(self._content):
            line = self._content[i]

            # Check for block start *before* updating level for the current line
            if block_pattern.search(line):
                start_line = i
                level = current_level

                # Find the end of this block by counting braces
                block_brace_level = 0
                end_line = -1
                for j in range(start_line, len(self._content)):
                    block_brace_level += self._content[j].count('{')
                    block_brace_level -= self._content[j].count('}')
                    if block_brace_level <= 0:
                        end_line = j
                        break

                if end_line != -1:
                    occurrences.append({'start': start_line, 'end': end_line, 'level': level})
                    # Update current_level based on the content of the block we just processed.
                    for k in range(i, end_line + 1):
                        current_level += self._content[k].count('{') - self._content[k].count('}')
                    i = end_line + 1
                    continue

            # Update level for the current line and move to the next
            current_level += line.count('{') - line.count('}')
            i += 1
        return occurrences

    def _find_best_dependencies_block(self) -> Optional[tuple[int, int]]:
        """
        Finds the best 'dependencies' block to inject into.

        It prioritizes toplevel blocks (level 0). If none are found, it selects
        the highest-level (least nested) block available and logs a warning.
        """
        all_deps_blocks = self._find_all_block_occurrences("dependencies")
        if not all_deps_blocks:
            return None

        # Prefer toplevel blocks (nesting level 0)
        toplevel_blocks = [b for b in all_deps_blocks if b['level'] == 0]
        if toplevel_blocks:
            best_block = toplevel_blocks[0]
            self.logger.debug(f"Found toplevel 'dependencies' block at lines {best_block['start']}-{best_block['end']}.")
            return best_block['start'], best_block['end']

        # If no toplevel blocks, find the one with the minimum nesting and log a warning.
        self.logger.warning(
            "No toplevel 'dependencies' block found. Injecting into the highest-level "
            "(least nested) block available. Please verify this is the correct location "
            "(e.g., not in 'buildscript')."
        )
        best_block = min(all_deps_blocks, key=lambda b: b['level'])
        self.logger.debug(f"Selected nested 'dependencies' block at lines {best_block['start']}-{best_block['end']} with level {best_block['level']}.")
        return best_block['start'], best_block['end']

    def _find_insertion_point(self, block_name: str) -> Optional[tuple[int, str]]:
        """Finds a line index and indentation to insert into a block."""
        if block_name == "dependencies":
            block_indices = self._find_best_dependencies_block()
        else:
            block_indices = self._find_first_block_lines(block_name)

        if not block_indices:
            # TODO: Optionally add the block if it doesn't exist
            self.logger.warning(f"Block '{block_name}' not found in {self.path}. Cannot insert.")
            return None

        start_idx, end_idx = block_indices
        # Find indentation: use indentation of the first non-empty line after '{'
        # or default to 4 spaces if the block is empty.
        indentation = "    "  # Default
        for i in range(start_idx + 1, end_idx + 1):
            line = self._content[i].rstrip()
            match = re.match(r"^(\s+)", line)
            if line.strip() and not line.strip().startswith('}'):  # Found content line
                if match:
                    indentation = match.group(1)
                else:  # Content starts at column 0 within block? Use default.
                    pass
                break
            elif '}' in line:  # Reached end brace without finding content
                # Get indentation from the line *before* the closing brace if possible
                if i > start_idx:
                    prev_line = self._content[i-1]
                    prev_match = re.match(r"^([ \t]+)", prev_line)
                    if prev_match:
                        indentation = prev_match.group(1)
                break

        # Insertion point: typically before the closing brace
        insertion_index = end_idx
        if end_idx == start_idx + 1:  # Block is empty
            indentation = "    "  # Default
        return insertion_index, indentation

    def has_dependency(self, group_id: str, artifact_id: str) -> bool:
        """Checks if a specific dependency coordinates exist in the best-candidate dependencies block."""
        block_indices = self._find_best_dependencies_block()
        if not block_indices:
            return False

        start_idx, end_idx = block_indices
        # Pattern: scope 'group:artifact:version' or scope group: 'artifact', version: 'ver' etc.
        # Simple check for 'group:artifact' string
        dep_pattern = re.compile(r"['\"]" + re.escape(group_id) + r":" + re.escape(artifact_id) + r"[:'\"]")

        for i in range(start_idx, end_idx + 1):
            if dep_pattern.search(self._content[i]):
                return True
        return False

    def add_new_block(self, block_name: str) -> Optional[tuple[int, str]]:
        """Adds a new block at the start of the build file but after plugins block."""
        if block_name == "plugins":
            insertion_index = 0
        else:
            insertion_info = self._find_insertion_point("plugins")
            insertion_index = insertion_info[0] + 1 if insertion_info else 0
        self._content.insert(insertion_index, f"{block_name} {{\n")
        self._content.insert(insertion_index + 1, "}\n\n")  # Add extra newline
        self.is_modified = True
        return insertion_index + 1, "    "

    def add_dependency(self, dep_info: dict[str, Any]) -> None:
        """Adds a dependency line to the dependencies block if it doesn't exist."""
        group_id = dep_info["groupId"]
        artifact_id = dep_info["artifactId"]
        version = dep_info["version"]
        # Map Maven scopes to common Gradle scopes
        scope = dep_info.get("scope", "implementation")  # Default to implementation
        if scope == "provided":
            scope = "compileOnly"
        elif scope == "test":
            scope = "testImplementation"
        elif scope == "runtime":
            scope = "runtimeOnly"
        elif scope == "annotationProcessor":
            scope = "annotationProcessor"

        if not self.has_dependency(group_id, artifact_id):
            insertion_info = self._find_insertion_point("dependencies")
            if not insertion_info:
                self.logger.warning(f"Cannot add dependency {group_id}:{artifact_id} - 'dependencies' block not found. Creating a new one.")
                insertion_info = self.add_new_block("dependencies")
                if not insertion_info: # Should not happen with add_new_block logic
                    self.logger.error("Failed to create and find insertion point for 'dependencies' block.")
                    return

            insertion_index, indent = insertion_info
            dep_line = f"{indent}{scope} '{group_id}:{artifact_id}:{version}'\n"
            self._content.insert(insertion_index, dep_line)
            self.is_modified = True
            self.logger.debug(f"  Added Gradle dependency: {scope} '{group_id}:{artifact_id}:{version}'")
        else:
            self.logger.debug(f"  Gradle dependency OK: {group_id}:{artifact_id}")
            # TODO: Update dependency version if needed

    def has_plugin(self, plugin_id: str, artifact_id: Optional[str] = None) -> bool:
        """Checks if a plugin ID is present in the plugins block."""
        block_indices = self._find_first_block_lines("plugins")
        if not block_indices:
            return False

        start_idx, end_idx = block_indices
        # Pattern: id 'plugin.id' or id("plugin.id")
        plugin_pattern = re.compile(r"id\s*\(?\s*['\"]" + re.escape(plugin_id) + r"['\"]\s*\)?")

        for i in range(start_idx + 1, end_idx + 1):
            if plugin_pattern.search(self._content[i]):
                return True
        return False

    def add_plugin(self, plugin_info: dict[str, Any]) -> None:
        """Adds a plugin line to the plugins block if it doesn't exist."""
        plugin_id = plugin_info.get("id")
        version = plugin_info.get("version")

        if not plugin_id:
            self.logger.error("Gradle plugin info requires 'id'.")
            return

        if not self.has_plugin(plugin_id):
            insertion_info = self._find_insertion_point("plugins")
            if not insertion_info:
                # If 'plugins' block is missing, it MUST be at the top of the file.
                # Adding it elsewhere is invalid Groovy syntax.
                # We'll attempt to add it at the beginning.
                self.logger.warning("Block 'plugins' not found. Attempting to add at the beginning.")
                insertion_info = self.add_new_block("plugins")
            insertion_index, indent = insertion_info
            plugin_line = f"{indent}id '{plugin_id}'"
            if version:
                plugin_line += f" version '{version}'"
            plugin_line += "\n"
            self._content.insert(insertion_index, plugin_line)
            self.is_modified = True
            version_str = f" version '{version}'" if version else ""
            self.logger.debug(f"  Added Gradle plugin: id '{plugin_id}'{version_str}")
        else:
            self.logger.debug(f"  Gradle plugin OK: id '{plugin_id}'")
            # TODO: Update plugin version if needed

    def add_plugins(self) -> None:
        """Adds build plugins for protobuf and gRPC if they don't exist."""
        for plugin_info in REQUIRED_GRADLE_PLUGINS:
            self.add_plugin(plugin_info)
        self.add_protobuf_block()

    # --- Extensions are generally handled as plugins in Gradle ---
    def has_extension(self, group_id: str, artifact_id: str) -> bool:
        pass

    def add_extension(self) -> None:
        pass

    def add_protobuf_block(self):
        """Adds the protobuf {} configuration block if the plugin is present but config is missing."""
        if not self.has_plugin("com.google.protobuf"):
            raise RuntimeError("Protobuf plugin not found. Cannot add protobuf configuration block.")
        if self._find_first_block_lines("protobuf"):
            # TODO: Could add logic here to check/update contents
            raise NotImplementedError("Updating protobuf block not implemented yet.")

        self.logger.debug("Adding protobuf configuration block...")
        plugins_indices = self._find_first_block_lines("plugins")
        insertion_index = plugins_indices[1] + 1 if plugins_indices else 0
        config_lines = [
            f"protobuf {{\n",
            f"    protoc {{ artifact = 'com.google.protobuf:protoc:{PROTOBUF_VERSION}' }}\n",
            f"    plugins {{\n",
            f"        grpc {{\n",
            f"            artifact = 'io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}'\n",
            f"        }}\n",
            f"    }}\n",
            f"    generateProtoTasks {{\n",
            f"        all()*.plugins {{\n",
            f"            grpc {{}}\n",
            f"        }}\n",
            f"    }}\n",
            f"}}\n\n"
        ]

        # Insert lines respecting original content order
        self._content = self._content[:insertion_index] + config_lines + self._content[insertion_index:]
        self.is_modified = True
        self.logger.debug("  Added protobuf configuration block.")

    def _include_children_dependencies(self, dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.mode in ["server", "both"]:
            dependencies.extend(REQUIRED_GRADLE_PLUGINS_SERVER_DEPENDENCIES)
        return dependencies
