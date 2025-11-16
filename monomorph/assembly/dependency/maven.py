import os
import xml.etree.ElementTree as ET
from typing import Any, Optional
import shutil

from .buildfile import BuildFile, PROTOBUF_VERSION, GRPC_VERSION, MAPSTRUCT_VERSION
from ...const import PROTO_PATH

# --- maven dependencies versions ---
OS_MAVEN_PLUGIN_VERSION = "1.7.1"
PROTOBUF_MAVEN_PLUGIN_VERSION = "0.6.1"
MAVEN_COMPILER_PLUGIN_VERSION = "3.13.0"

## Maven compiler plugin groupId and artifactId
MAVEN_COMPILER_PLUGIN_GROUP_ID = "org.apache.maven.plugins"
MAVEN_COMPILER_PLUGIN_ARTIFACT_ID = "maven-compiler-plugin"


# Build extension required for protobuf-maven-plugin classifier resolution
REQUIRED_MAVEN_EXTENSION = {
    "groupId": "kr.motd.maven",
    "artifactId": "os-maven-plugin",
    "version": OS_MAVEN_PLUGIN_VERSION,
}

# Build plugins required for protobuf compilation and gRPC code generation
REQUIRED_MAVEN_PLUGINS = [
    {
        "groupId": "org.xolstice.maven.plugins",
        "artifactId": "protobuf-maven-plugin",
        "version": PROTOBUF_MAVEN_PLUGIN_VERSION,
        "configuration": {
            "protocArtifact": f"com.google.protobuf:protoc:{PROTOBUF_VERSION}:exe:${{os.detected.classifier}}",
            "pluginId": "grpc-java",
            "pluginArtifact": f"io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}:exe:${{os.detected.classifier}}",
            "protoSourceRoot": PROTO_PATH,
        },
        "executions": [
            {"goals": ["compile", "compile-custom"]},
            # {"id": "compile", "goals": ["compile", "compile-custom"]},
            # {"id": "test-compile", "goals": ["test-compile", "test-compile-custom"]},
        ],
    },
    # {
    #     "groupId": "org.apache.maven.plugins",
    #     "artifactId": "maven-compiler-plugin",
    #     "version": MAVEN_COMPILER_PLUGIN_VERSION,
    #     "configuration": {
    #         "source": None,  # Placeholder
    #         "target": None,  # Placeholder
    #     },
    # }
]

SERVER_REQUIRED_MAVEN_ANNOTATION_PROCESSORS = [
    {
        "groupId": "org.mapstruct",
        "artifactId": "mapstruct-processor",
        "version": MAPSTRUCT_VERSION,
    },
]


class MavenPomFile(BuildFile):
    """Implementation of BuildFile for Maven pom.xml files."""

    MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
    NS_MAP = {'mvn': MAVEN_NAMESPACE}  # For findall

    def __init__(self, path: str, java_version: str, output_path: Optional[str] = None, mode: str = "client"):
        super().__init__(path, java_version, output_path, mode)
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        self._namespace = ""  # Determined during parse

    def _get_ns_tag(self, tag: str) -> str:
        """Prepends namespace to tag if namespace exists."""
        return f"{{{self._namespace}}}{tag}" if self._namespace else tag

    def _find_element(self, parent: ET.Element, tag: str, criteria: dict[str, str]) -> Optional[ET.Element]:
        """Finds a direct child element matching tag and criteria within the POM namespace."""
        tag_with_ns = self._get_ns_tag(tag)
        criteria_with_ns = {self._get_ns_tag(k): v for k, v in criteria.items()}

        for element in parent.findall(tag_with_ns):
            match = True
            for key_ns, value in criteria_with_ns.items():
                child = element.find(key_ns)
                if child is None or child.text != value:
                    match = False
                    break
            if match:
                return element
        return None

    def _ensure_element(self, parent: ET.Element, tag: str) -> ET.Element:
        """Finds or creates a direct child element within the POM namespace."""
        tag_with_ns = self._get_ns_tag(tag)
        element = parent.find(tag_with_ns)
        if element is None:
            # Insert in a somewhat standard order if possible
            insert_before_tags = []
            if tag == 'dependencies':
                insert_before_tags = ['build']
            elif tag == 'build':
                insert_before_tags = ['reporting', 'profiles']
            elif tag == 'plugins':
                insert_before_tags = ['pluginManagement', 'resources', 'testResources',
                                      'extensions']  # Added extensions here
            elif tag == 'extensions':
                # Extensions should typically come before plugins within build
                insert_before_tags = ['plugins', 'pluginManagement', 'resources', 'testResources']

            inserted = False
            if parent.tag == self._get_ns_tag('build'):  # Special ordering within build
                for before_tag in insert_before_tags:
                    before_el = parent.find(self._get_ns_tag(before_tag))
                    if before_el is not None:
                        idx = list(parent).index(before_el)
                        element = ET.Element(tag_with_ns)
                        parent.insert(idx, element)
                        inserted = True
                        break
            elif parent.tag == self._get_ns_tag('project'):  # Special ordering within project root
                for before_tag in insert_before_tags:
                    before_el = parent.find(self._get_ns_tag(before_tag))
                    if before_el is not None:
                        idx = list(parent).index(before_el)
                        element = ET.Element(tag_with_ns)
                        parent.insert(idx, element)
                        inserted = True
                        break

            if not inserted:  # Append if no suitable insertion point found or parent not recognized for specific ordering
                element = ET.SubElement(parent, tag_with_ns)

            self.logger.debug(f"  Created missing <{tag}> element.")
            self.is_modified = True  # Creating an element counts as modification
        return element

    def _add_sub_elements(self, parent: ET.Element, data: dict[str, Any]):
        """Adds sub-elements based on a dictionary, handling nested dicts/lists."""
        for key, value in data.items():
            if key in ["configuration", "executions", "scope"]:  # Special handling or handled separately
                continue
            el = ET.SubElement(parent, self._get_ns_tag(key))
            el.text = str(value)
        # Handle scope specifically if present
        if "scope" in data and data["scope"] is not None:
            el = ET.SubElement(parent, self._get_ns_tag("scope"))
            el.text = str(data["scope"])

    def _add_config_elements(self, parent: ET.Element, config_dict: dict):
        """Recursively adds configuration elements."""
        for key, value in config_dict.items():
            el = ET.SubElement(parent, self._get_ns_tag(key))
            if isinstance(value, dict):
                self._add_config_elements(el, value)
            elif value is not None:
                el.text = str(value)

    def _add_execution_elements(self, parent: ET.Element, executions_list: list[dict]):
        """Adds execution elements."""
        executions_el = self._ensure_element(parent, "executions")
        existing_ids = {ex.findtext(self._get_ns_tag("id"))
                        for ex in executions_el.findall(self._get_ns_tag("execution"))
                        if ex.find(self._get_ns_tag("id")) is not None}  # Check id exists before getting text
        for execution_dict in executions_list:
            exec_id = execution_dict.get("id")
            # Check if an execution with the same goals exists if no id is provided
            needs_adding = True
            if exec_id and exec_id in existing_ids:
                self.logger.debug(f"    Execution with id '{exec_id}' already exists, skipping.")
                needs_adding = False
            elif not exec_id:  # Check by goals if no ID
                req_goals = set(execution_dict.get("goals", []))
                if req_goals:
                    for existing_exec in executions_el.findall(self._get_ns_tag("execution")):
                        existing_goals_el = existing_exec.find(self._get_ns_tag("goals"))
                        if existing_goals_el is not None:
                            existing_goals = {g.text for g in existing_goals_el.findall(self._get_ns_tag("goal"))}
                            if existing_goals == req_goals:
                                self.logger.debug(
                                    f"    Execution with goals '{','.join(req_goals)}' already exists, skipping.")
                                needs_adding = False
                                break

            if needs_adding:
                execution_el = ET.SubElement(executions_el, self._get_ns_tag("execution"))
                if exec_id:
                    ET.SubElement(execution_el, self._get_ns_tag("id")).text = exec_id

                if "phase" in execution_dict:
                    ET.SubElement(execution_el, self._get_ns_tag("phase")).text = execution_dict["phase"]

                if "goals" in execution_dict:
                    goals_el = ET.SubElement(execution_el, self._get_ns_tag("goals"))
                    for goal in execution_dict["goals"]:
                        ET.SubElement(goals_el, self._get_ns_tag("goal")).text = goal

                if "configuration" in execution_dict:
                    config_el = ET.SubElement(execution_el, self._get_ns_tag("configuration"))
                    self._add_config_elements(config_el, execution_dict["configuration"])

                log_id = f"id '{exec_id}'" if exec_id else f"goals '{','.join(execution_dict.get('goals', []))}'"
                self.logger.debug(f"    Added execution with {log_id}.")
                self.is_modified = True

    def parse(self) -> None:
        """Loads and parses the pom.xml file."""
        try:
            # Register namespace for cleaner output, still need ns in findall etc.
            ET.register_namespace('', self.MAVEN_NAMESPACE)
            parser = ET.XMLParser(encoding="utf-8", target=ET.TreeBuilder(insert_comments=True))
            self.tree = ET.parse(self.path, parser)
            self.root = self.tree.getroot()

            # Determine namespace from root element
            if self.root.tag.startswith('{') and '}' in self.root.tag:
                self._namespace = self.root.tag[1:self.root.tag.index('}')]
                if self._namespace != self.MAVEN_NAMESPACE:
                    self.logger.warning(f"Unexpected POM namespace '{self._namespace}'. "
                                        f"Expected '{self.MAVEN_NAMESPACE}'.")
            else:
                # If no namespace in root tag, assume it's the default maven namespace
                # This can happen if the file was created without explicit ns declaration
                # but still uses the default namespace implicitly. Test with findall.
                if self.root.findall(f"{{{self.MAVEN_NAMESPACE}}}modelVersion"):
                    self._namespace = self.MAVEN_NAMESPACE
                    self.logger.debug(f"Detected implicit POM namespace '{self.MAVEN_NAMESPACE}'.")
                else:
                    self.logger.warning(
                        "POM file does not seem to have a namespace or doesn't match expected structure. Results may be unpredictable.")
                    self._namespace = ""  # Proceed without namespace

        except ET.ParseError as e:
            self.logger.error(f"Error parsing POM file {self.path}: {e}")
            raise e
        except FileNotFoundError:
            self.logger.error(f"File not found at {self.path}")
            raise

    def save(self, backup: bool = False) -> None:
        """Saves the modified POM file."""
        if self.tree is None or self.root is None:
            self.logger.error("POM file not parsed. Cannot save.")
            return
        if not self.is_modified:
            self.logger.debug("No changes detected. File not saved.")
            return
        if backup:
            self.create_backup()
        self.logger.info(f"Writing dependency changes to {self.output_path}...")
        try:
            # Use ET.indent for pretty printing (Python 3.9+)
            if hasattr(ET, 'indent'):
                ET.indent(self.tree, space="  ", level=0)
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            self.tree.write(self.output_path, encoding="utf-8", xml_declaration=True)
            self.logger.info("Save complete.")
        except Exception as e:
            self.logger.error(f"Error writing file {self.output_path}: {e}")
            raise e
        if backup and os.path.exists(self.output_path):
            self.delete_backup()

    def has_dependency(self, group_id: str, artifact_id: str) -> bool:
        """Checks if a dependency exists."""
        if self.root is None:
            return False
        dependencies = self.root.find(self._get_ns_tag("dependencies"))
        if dependencies is None:
            return False
        return self._find_element(dependencies, "dependency",
                                  {"groupId": group_id, "artifactId": artifact_id}) is not None

    def add_dependency(self, dep_info: dict[str, Any]) -> None:
        """Adds a dependency if it doesn't exist."""
        if self.root is None:
            return
        group_id = dep_info["groupId"]
        artifact_id = dep_info["artifactId"]
        scope = dep_info.get("scope", None)

        if not self.has_dependency(group_id, artifact_id):
            dependencies = self._ensure_element(self.root, "dependencies")
            dep = ET.SubElement(dependencies, self._get_ns_tag("dependency"))
            self._add_sub_elements(dep, dep_info)
            self.logger.debug(f"  Added dependency: {group_id}:{artifact_id}:{dep_info['version']}")
            self.is_modified = True
        else:
            self.logger.debug(f"  Dependency OK: {group_id}:{artifact_id}")
            # TODO: Update dependency version if needed

    def _find_build_plugin(self, group_id: str, artifact_id: str) -> Optional[ET.Element]:
        """Helper to find a specific plugin in the build section."""
        if self.root is None:
            return None
        build = self.root.find(self._get_ns_tag("build"))
        if build is None:
            return None
        plugins = build.find(self._get_ns_tag("plugins"))
        if plugins is None:
            return None
        return self._find_element(plugins, "plugin", {"groupId": group_id, "artifactId": artifact_id})

    def has_plugin(self, group_id: str, artifact_id: str) -> bool:
        """Checks if a build plugin exists."""
        return self._find_build_plugin(group_id, artifact_id) is not None

    def add_plugin(self, plugin_info: dict[str, Any]) -> None:
        """Adds a build plugin if it doesn't exist."""
        if self.root is None:
            return
        group_id = plugin_info["groupId"]
        artifact_id = plugin_info["artifactId"]

        if not self.has_plugin(group_id, artifact_id):
            build = self._ensure_element(self.root, "build")
            plugins = self._ensure_element(build, "plugins")
            plugin = ET.SubElement(plugins, self._get_ns_tag("plugin"))

            # Add basic plugin info (groupId, artifactId, version)
            simple_info = {k: v for k, v in plugin_info.items() if k in ["groupId", "artifactId", "version"] and v}
            self._add_sub_elements(plugin, simple_info)

            # Add configuration if present
            if plugin_info.get("configuration"):
                config = ET.SubElement(plugin, self._get_ns_tag("configuration"))
                self._add_config_elements(config, plugin_info["configuration"])

            # Add executions if present
            if plugin_info.get("executions"):
                self._add_execution_elements(plugin, plugin_info["executions"])

            self.logger.debug(f"  Added plugin: {group_id}:{artifact_id}:{plugin_info.get('version', 'N/A')}")
            self.is_modified = True
        else:
            self.logger.debug(f"  Plugin OK: {group_id}:{artifact_id}")
            existing_plugin = self._find_build_plugin(group_id, artifact_id)
            if existing_plugin is not None:
                config_data = plugin_info.get("configuration", None)
                exec_data = plugin_info.get("executions", None)

                # Check/Add configuration elements (simple merge - add if not exists)
                if config_data:
                    self._add_config_to_plugin(existing_plugin, config_data)

                # Check/Add executions
                if exec_data:
                    # Use the existing _add_execution_elements which handles checking
                    self._add_execution_elements(existing_plugin, exec_data)
            # --- END: Add execution/configuration update logic ---
            # TODO: Update plugin configuration if needed

    def _add_config_to_plugin(self, existing_plugin: ET.Element, config_data: dict) -> None:
            config_el = existing_plugin.find(self._get_ns_tag("configuration"))
            if config_el is None:
                config_el = ET.SubElement(existing_plugin, self._get_ns_tag("configuration"))
                self.logger.debug(
                    f"    Added missing <configuration> to existing plugin")
                self.is_modified = True
            # Add missing config keys (won't overwrite existing ones)
            current_keys = {el.tag.split('}')[-1] for el in config_el}  # Get existing keys without namespace
            added_key = False
            for key, value in config_data.items():
                if self._get_ns_tag(key) not in {el.tag for el in config_el}:  # Check full namespaced tag
                    self.logger.debug(f"      Adding missing config key '{key}'")
                    new_el = ET.SubElement(config_el, self._get_ns_tag(key))
                    if isinstance(value, dict):
                        self._add_config_elements(new_el, value)
                    elif value is not None:
                        new_el.text = str(value)
                    added_key = True
            if added_key:
                self.is_modified = True

    def add_plugins(self) -> None:
        """Adds build plugins for protobuf and gRPC if they don't exist or updates them."""
        for plugin_info in REQUIRED_MAVEN_PLUGINS:
            self.add_plugin(plugin_info)
        if self.mode in ["server", "both"]:
            # Add or update maven compiler plugin
            processors = SERVER_REQUIRED_MAVEN_ANNOTATION_PROCESSORS
            self.ensure_compiler_plugin_annotation_processors(processors)

    def has_extension(self, group_id: str, artifact_id: str) -> bool:
        """Checks if a build extension exists."""
        if self.root is None:
            return False
        build = self.root.find(self._get_ns_tag("build"))
        if build is None:
            return False
        extensions = build.find(self._get_ns_tag("extensions"))
        if extensions is None:
            return False
        return self._find_element(extensions, "extension", {"groupId": group_id, "artifactId": artifact_id}) is not None

    def add_extension(self) -> None:
        """Adds a build extension if it doesn't exist."""
        if self.root is None:
            return
        ext_info: dict[str, Any] = REQUIRED_MAVEN_EXTENSION
        group_id = ext_info["groupId"]
        artifact_id = ext_info["artifactId"]

        if not self.has_extension(group_id, artifact_id):
            build = self._ensure_element(self.root, "build")
            extensions = self._ensure_element(build, "extensions")
            ext = ET.SubElement(extensions, self._get_ns_tag("extension"))
            self._add_sub_elements(ext, ext_info)
            self.logger.debug(f"  Added extension: {group_id}:{artifact_id}:{ext_info['version']}")
            self.is_modified = True
        else:
            self.logger.debug(f"  Extension OK: {group_id}:{artifact_id}")
            # TODO: Update extension version if needed

    def ensure_compiler_plugin_annotation_processors(self, annotation_processors: list[dict[str, str]]) -> None:
        """
        Ensures the maven-compiler-plugin exists and has the specified annotation processors
        listed under <configuration><annotationProcessorPaths>. Adds the plugin or missing
        processors as needed.
        """
        if self.root is None:
            self.logger.error("POM not parsed. Cannot ensure annotation processors.")
            return
        if not annotation_processors:
            self.logger.debug("No annotation processors provided to ensure.")
            return

        self.logger.info("Ensuring maven-compiler-plugin and annotation processor paths...")

        # 1. Find or Add maven-compiler-plugin
        compiler_plugin_el = self._find_build_plugin(
            MAVEN_COMPILER_PLUGIN_GROUP_ID,
            MAVEN_COMPILER_PLUGIN_ARTIFACT_ID
        )

        if compiler_plugin_el is None:
            self.logger.debug(f"  Plugin '{MAVEN_COMPILER_PLUGIN_ARTIFACT_ID}' not found. Adding...")
            build_el = self._ensure_element(self.root, "build")
            plugins_el = self._ensure_element(build_el, "plugins")

            compiler_plugin_el = ET.SubElement(plugins_el, self._get_ns_tag("plugin"))
            ET.SubElement(compiler_plugin_el, self._get_ns_tag("groupId")).text = MAVEN_COMPILER_PLUGIN_GROUP_ID
            ET.SubElement(compiler_plugin_el, self._get_ns_tag("artifactId")).text = MAVEN_COMPILER_PLUGIN_ARTIFACT_ID
            # Add a default version when creating the plugin
            ET.SubElement(compiler_plugin_el, self._get_ns_tag("version")).text = MAVEN_COMPILER_PLUGIN_VERSION
            # Add basic config with source/target based on instance's java_version
            config_el = ET.SubElement(compiler_plugin_el, self._get_ns_tag("configuration"))
            ET.SubElement(config_el, self._get_ns_tag("source")).text = self.java_version
            ET.SubElement(config_el, self._get_ns_tag("target")).text = self.java_version
            self.logger.debug(f"    Added basic <configuration> with source/target {self.java_version}")
            self.is_modified = True
            # config_el is already defined and needed below
        else:
            self.logger.debug(f"  Plugin '{MAVEN_COMPILER_PLUGIN_ARTIFACT_ID}' found.")
            # Find or create config element if plugin exists but has no config
            config_el = compiler_plugin_el.find(self._get_ns_tag("configuration"))
            if config_el is None:
                config_el = ET.SubElement(compiler_plugin_el, self._get_ns_tag("configuration"))
                self.logger.debug(f"    Added missing <configuration> to existing {MAVEN_COMPILER_PLUGIN_ARTIFACT_ID}.")
                self.is_modified = True
                # Optionally ensure source/target exist here too, but keep minimal for now

        # At this point, compiler_plugin_el and config_el are guaranteed to exist.

        # 3. Find or Add <annotationProcessorPaths> within <configuration>
        processor_paths_el = config_el.find(self._get_ns_tag("annotationProcessorPaths"))
        if processor_paths_el is None:
            # Insert <annotationProcessorPaths> typically after source/target/compilerArgs etc.
            # For simplicity, just append it to configuration for now.
            processor_paths_el = ET.SubElement(config_el, self._get_ns_tag("annotationProcessorPaths"))
            self.logger.debug("      Added missing <annotationProcessorPaths> element.")
            self.is_modified = True

        # 4. Iterate through required processors and add if missing
        for proc_info in annotation_processors:
            group_id = proc_info.get("groupId")
            artifact_id = proc_info.get("artifactId")
            version = proc_info.get("version")

            if not group_id or not artifact_id or not version:
                self.logger.warning(f"Skipping invalid annotation processor definition (missing GAV): {proc_info}")
                continue

            # Check if a <path> with this groupId and artifactId already exists
            path_exists = self._find_element(
                processor_paths_el,
                "path",
                {"groupId": group_id, "artifactId": artifact_id}
            )

            if path_exists is None:
                self.logger.debug(f"        Adding annotation processor path: {group_id}:{artifact_id}:{version}")
                path_el = ET.SubElement(processor_paths_el, self._get_ns_tag("path"))
                ET.SubElement(path_el, self._get_ns_tag("groupId")).text = group_id
                ET.SubElement(path_el, self._get_ns_tag("artifactId")).text = artifact_id
                ET.SubElement(path_el, self._get_ns_tag("version")).text = version
                self.is_modified = True
            else:
                self.logger.debug(f"        Annotation processor path OK: {group_id}:{artifact_id}")
                # Optional: Check if the version matches and update if necessary
