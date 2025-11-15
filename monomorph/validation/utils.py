import os
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from .raaid import _is_binary_fallback

from .const import DEFAULT_DOCKER_WORKDIR
from ..execution.helpers import HelperManager
from ..execution.microservice import MicroserviceDirectory


logger = logging.getLogger("monomorph")


def parse_docker_path(
        file_path: str,
        actual_root: str,
        workdir_mappings: Optional[dict[str, str]] = None
) -> str:
    """
    Parse and normalize file paths extracted from Docker logs.

    This function handles paths that may:
    - Start with a Docker workdir (e.g., /app/rest/of/path)
    - Be relative paths (e.g., ./rest/of/path or rest/of/path)
    - Be absolute paths that need workdir replacement

    Args:
        file_path (str): The file path to parse (from Docker logs)
        actual_root (str): The actual root directory to use as replacement
        workdir_mappings (Dict[str, str], optional): Mapping of workdir prefixes to their replacements.
            If None, uses default_workdir -> actual_root mapping.

    Returns:
        str: Normalized path with correct root

    Examples:
        >>> parse_docker_path("/app/src/main.py", "/home/user/project")
        "/home/user/project/src/main.py"

        >>> parse_docker_path("./src/main.py", "/home/user/project")
        "/home/user/project/src/main.py"

        >>> parse_docker_path("src/main.py", "/home/user/project")
        "/home/user/project/src/main.py"
    """
    if not file_path:
        return actual_root
    # Normalize the input path
    normalized_path = os.path.normpath(file_path)
    # Set up workdir mappings
    if workdir_mappings is None:
        workdir_mappings = {DEFAULT_DOCKER_WORKDIR: actual_root}
    # Handle absolute paths with workdir prefixes
    for workdir, root_replacement in workdir_mappings.items():
        if normalized_path.startswith(workdir):
            # Remove the workdir prefix and join with actual root
            relative_part = normalized_path[len(workdir):].lstrip(os.sep)
            if relative_part:
                return os.path.join(root_replacement, relative_part)
            else:
                return root_replacement
    # Handle relative paths
    if normalized_path.startswith('./'):
        # Remove ./ prefix and join with actual root
        relative_part = normalized_path[2:]
        return os.path.join(actual_root, relative_part)
    elif normalized_path.startswith('../'):
        # Handle parent directory references - might need special handling
        # For now, treat as relative to actual_root
        return os.path.join(actual_root, normalized_path)
    elif not os.path.isabs(normalized_path):
        # Relative path without ./ prefix
        return os.path.join(actual_root, normalized_path)
    # If it's an absolute path that doesn't match any workdir, return as-is
    # (might be a system path that shouldn't be modified)
    return normalized_path


def compile_generated_classes_files(microservice: MicroserviceDirectory, helper_manager: HelperManager,
                                    language: str = "java") -> tuple[list[str], dict[str, Path], dict[str, tuple[str, str]]]:
    generated_files = []
    generated_classes = {}
    refactoring_details = {}
    if microservice.new_server:
        for sc, service_details in microservice.new_server.items():
            generated_files.append(service_details["path"])
            generated_classes[service_details["full_name"]] = Path(service_details["path"])
            relative_path = os.path.relpath(service_details["path"], microservice.directory_path)
            refactoring_details[relative_path] = (service_details["prompt"], service_details["explanation"])
    if microservice._new_proto:
        for proto, proto_details in microservice._new_proto.items():
            generated_files.append(proto_details["path"])
            relative_path = os.path.relpath(proto_details["path"], microservice.directory_path)
            refactoring_details[relative_path] = (proto_details["prompt"], proto_details["explanation"])
    if microservice._new_client:
        for client, client_details in microservice._new_client.items():
            generated_files.append(client_details["path"])
            generated_classes[client_details["full_name"]] = Path(client_details["path"])
            relative_path = os.path.relpath(client_details["path"], microservice.directory_path)
            refactoring_details[relative_path] = (client_details["prompt"], client_details["explanation"])
    if microservice._new_other:
        for other, other_details in microservice._new_other.items():
            generated_files.append(other_details["mapper_path"])
            generated_classes[other_details["mapper_full_name"]] = Path(other_details["mapper_path"])
            relative_path = os.path.relpath(other_details["mapper_path"], microservice.directory_path)
            refactoring_details[relative_path] = ("", other_details["explanation"])
    if microservice._included_helpers:
        for helper, path in microservice._included_helpers.items():
            generated_files.append(path)
            relative_path = os.path.relpath(path, microservice.directory_path)
            refactoring_details[relative_path] = ("", helper_manager.helper_mapping[helper]["description"])
            if path.endswith(language):
                # If the helper is a class file, add it to generated_classes
                helper_class = helper_manager.get_as_class(helper)
                if helper_class.full_name is not None:
                    generated_classes[helper_class.full_name] = Path(path)
    if microservice._generated_helpers:
        for name, helper_details in microservice._generated_helpers.items():
            path, helper = helper_details[0], helper_details[1]
            relative_path = os.path.relpath(path, microservice.directory_path)
            refactoring_details[relative_path] = ("", helper_manager.helper_mapping[helper]["description"])
            generated_files.append(path)
            package_name = helper_manager.helper_mapping[helper]["package"]
            full_name = f"{package_name}.{name}"
            generated_classes[full_name] = Path(path)
    for key, details in [("grpc", microservice._entrypoint_grpc_details),
                         ("combined", microservice._combined_main_details)]:
        if details:
            path = details["path"]
            generated_files.append(path)
            class_name = details["full_name"]
            generated_classes[class_name] = Path(path)
            relative_path = os.path.relpath(path, microservice.directory_path)
            refactoring_details[relative_path] = ("", details["explanation"])
    return generated_files, generated_classes, refactoring_details


def is_binary_file(filepath: str) -> bool:
    """
    Determine if a file is binary or text based on its content and structure.
    Warning: This function might return incorrect results for files with uncommon extensions or formats and that are
    not within the current file system (e.g., files in a Docker container or remote file systems).

    Args:
        filepath (str): The path to the file to be checked.

    Returns:
        bool: True if the file is binary, False if it is text.
    """
    extensions_not_in_raaid = [".log", ".csv", "tsv", ".proto", ".pb", ".jsonl", ".class", ".gradle", ".build"]
    file_root, file_ext = os.path.splitext(filepath)
    filename_without_extension = os.path.basename(file_root)
    if file_ext in extensions_not_in_raaid:
        return False
    if "Dockerfile" in filename_without_extension:
        # If the file has a Dockerfile name, we assume it is text
        return False
    try:
        return _is_binary_fallback(filepath)
    except FileNotFoundError:
        # If the file does not exist, we assume it is binary
        return True


def get_markdown_language(file_path: str) -> str:
    """
    Determine the markdown code block language identifier based on file extension.

    Args:
        file_path (str): Path to the file

    Returns:
        str: Language identifier for markdown code blocks, or empty string if unknown
    """

    # Extension to language mapping
    extension_map = {
        # Python
        '.py': 'python',
        '.pyw': 'python',
        '.pyi': 'python',
        # JavaScript/TypeScript
        '.js': 'javascript',
        '.jsx': 'jsx',
        '.ts': 'typescript',
        '.tsx': 'tsx',
        '.mjs': 'javascript',
        '.cjs': 'javascript',
        # Web technologies
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        # C/C++
        '.c': 'c',
        '.h': 'c',
        '.cpp': 'cpp',
        '.cxx': 'cpp',
        '.cc': 'cpp',
        '.hpp': 'cpp',
        '.hxx': 'cpp',
        # Java
        '.java': 'java',
        '.class': 'java',
        # C#
        '.cs': 'csharp',
        '.csx': 'csharp',
        # Shell/Bash
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.fish': 'fish',
        '.ps1': 'powershell',
        '.psm1': 'powershell',
        # Ruby
        '.rb': 'ruby',
        '.rbw': 'ruby',
        # PHP
        '.php': 'php',
        '.php3': 'php',
        '.php4': 'php',
        '.php5': 'php',
        '.phtml': 'php',
        # Go
        '.go': 'go',
        # Rust
        '.rs': 'rust',
        # Swift
        '.swift': 'swift',
        # Kotlin
        '.kt': 'kotlin',
        '.kts': 'kotlin',
        # Scala
        '.scala': 'scala',
        '.sc': 'scala',
        # R
        '.r': 'r',
        '.R': 'r',
        # SQL
        '.sql': 'sql',
        # YAML
        '.yaml': 'yaml',
        '.yml': 'yaml',
        # JSON
        '.json': 'json',
        '.jsonl': 'json',
        # XML
        '.xml': 'xml',
        '.xsl': 'xml',
        '.xsd': 'xml',
        # Markdown
        '.md': 'markdown',
        '.markdown': 'markdown',
        '.mdown': 'markdown',
        '.mkd': 'markdown',
        # Configuration files
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'ini',
        # Docker
        '.dockerfile': 'dockerfile',
        # Vim
        '.vim': 'vim',
        '.vimrc': 'vim',
        # Lua
        '.lua': 'lua',
        # Perl
        '.pl': 'perl',
        '.pm': 'perl',
        # Haskell
        '.hs': 'haskell',
        '.lhs': 'haskell',
        # Erlang/Elixir
        '.erl': 'erlang',
        '.ex': 'elixir',
        '.exs': 'elixir',
        # Clojure
        '.clj': 'clojure',
        '.cljs': 'clojure',
        '.cljc': 'clojure',
        # F#
        '.fs': 'fsharp',
        '.fsx': 'fsharp',
        # OCaml
        '.ml': 'ocaml',
        '.mli': 'ocaml',
        # Dart
        '.dart': 'dart',
        # Assembly
        '.asm': 'assembly',
        '.s': 'assembly',
        # Makefile
        '.makefile': 'makefile',
        # Plain text
        '.txt': 'text',
        '.log': 'text',
        # LaTeX
        '.tex': 'latex',
        '.cls': 'latex',
        '.sty': 'latex',
    }
    # Get the file extension
    ext = Path(file_path).suffix.lower()
    # Handle special cases for files without extensions
    filename = Path(file_path).name.lower()
    # Special filename mappings
    special_files = {
        'makefile': 'makefile',
        'dockerfile': 'dockerfile',
        'rakefile': 'ruby',
        'gemfile': 'ruby',
        'vagrantfile': 'ruby',
        'cmakelists.txt': 'cmake',
        '.gitignore': 'gitignore',
        '.bashrc': 'bash',
        '.zshrc': 'zsh',
        '.vimrc': 'vim',
    }
    # Check special filenames first
    if filename in special_files:
        return special_files[filename]
    # Check extension mapping
    return extension_map.get(ext, '')


def format_file_for_markdown(file_path: str, content: str) -> str:
    """
    Format file content for markdown with appropriate language syntax highlighting.

    Args:
        file_path (str): Path to the file
        content (str): File content

    Returns:
        str: Formatted markdown string
    """
    language = get_markdown_language(file_path)
#     markdown_content = f"""file path: {file_path}
# ```{language}
# {content}
# ```"""
    markdown_content = f"""--- START OF FILE {file_path} ---
{content}
--- END OF FILE {file_path} ---"""
    return markdown_content


def parse_find_details(find_details: list[str]) -> dict[str, dict]:
    """
    Parse the file and directory details fron a find -printf \'%p|%s|%T@|%m|%y\\n\' command output.
    Args:
        find_details (list[str]): The find details string for each file/directory.

    Returns:
        the file and directory details as a dictionary.
    """
    data = {}
    for line in find_details:
        parts = line.split('|')
        if len(parts) >= 5:
            path, size, mtime_epoch, perms, file_type = parts[:5]

            # Convert timestamp to readable format
            try:
                mtime_readable = datetime.fromtimestamp(float(mtime_epoch)).strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, OSError):
                mtime_readable = 'unknown'

            data[path] = {
                'type': file_type,
                'size': int(size) if size.isdigit() else 0,
                'mtime': mtime_readable,
                'mtime_epoch': float(mtime_epoch) if mtime_epoch.replace('.', '').isdigit() else 0,
                'permissions': perms,
                'is_file': file_type == 'f'
            }
        else:
            logger.warning(f"Failed to parse line: {line}. Expected format: path|size|mtime_epoch|permissions|type")
    return data


def build_tree_structure(files_data: dict, root_path: str) -> dict:
    """Build a tree structure from flat file list."""
    tree = {}

    for file_path, file_info in files_data.items():
        # Skip the root directory itself
        if file_path == root_path:
            continue

        # Get relative path from root
        try:
            rel_path = os.path.relpath(file_path, root_path)
            if rel_path.startswith('..'):
                continue
        except ValueError:
            continue

        # Split path into parts
        parts = rel_path.split(os.sep)
        current = tree

        # Build nested structure
        for i, part in enumerate(parts):
            if part not in current:
                current[part] = {'_info': None, '_children': {}}

            if i == len(parts) - 1:  # Last part (file/directory name)
                current[part]['_info'] = file_info
                current[part]['_path'] = file_path

            current = current[part]['_children']
    return tree


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0B"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def render_tree(tree: dict, prefix: str = "", is_last: bool = True, root_path: str = "", include_can_modif: bool = True,
                include_changed: bool = True, include_modif_time_size: bool = False) -> list[str]:
    """Render tree structure with enriched information."""
    lines = []

    items = list(tree.items())
    for i, (name, data) in enumerate(items):
        is_last_item = i == len(items) - 1

        # Determine tree symbols
        current_prefix = "└── " if is_last_item else "├── "
        next_prefix = prefix + ("    " if is_last_item else "│   ")

        # Get file information
        file_info = data.get('_info', {})
        file_path = data.get('_path', '')

        if file_info:
            # Use internal data to determine file status
            is_changed = file_info.get('is_changed', False)
            can_modify = file_info.get('can_modify', True)
            # Build status indicators
            # Format file line
            if file_info.get('is_file', False):
                status_indicators = []
                if include_can_modif:
                    if can_modify:
                        status_indicators.append("WRITABLE")
                    else:
                        status_indicators.append("READ-ONLY")
                if include_changed:
                    if is_changed:
                        status_indicators.append(f"CHANGED")
                    else:
                        status_indicators.append(f"UNCHANGED")
                if include_modif_time_size:
                    size_str = format_size(file_info.get('size', 0))
                    mtime_str = file_info.get('mtime', 'unknown')
                    size_time_str = f"({size_str}, {mtime_str})"
                else:
                    size_time_str = ""
                status_str = " [" + ", ".join(status_indicators) + "]" if status_indicators else ""
                line = f"{prefix}{current_prefix}{name} {size_time_str}{status_str}"
            else:
                # Directory
                line = f"{prefix}{current_prefix}{name}/"
            lines.append(line)
        else:
            # No file info available
            line = f"{prefix}{current_prefix}{name}"
            lines.append(line)

        # Recurse into children
        if data['_children']:
            lines.extend(render_tree(
                data['_children'],
                next_prefix,
                is_last_item,
                root_path,
                include_can_modif=include_can_modif,
                include_changed=include_changed,
                include_modif_time_size=include_modif_time_size
            ))
    return lines


def get_class_name_from_content(content: str, language: str = "java") -> Optional[str]:
    LANGUAGE_LOGIC_MAPPING = {
        "java": extract_java_fqn,
    }
    if language.lower() not in LANGUAGE_LOGIC_MAPPING:
        raise ValueError(f"Unsupported language: {language}. Currently only {list(LANGUAGE_LOGIC_MAPPING.keys())} "
                         f"is supported.")
    extractor = LANGUAGE_LOGIC_MAPPING[language.lower()]
    if not callable(extractor):
        raise ValueError(f"Extractor for {language} is not callable.")
    fqn = extractor(content)
    return fqn


def extract_java_fqn(source_code: str) -> Optional[str]:
    """
    Extracts the Fully Qualified Name (FQN) of a Java type from its source code.

    Args:
        source_code: A string containing the Java source code.

    Returns:
        The fully qualified name (e.g., "com.example.MyClass") as a string,
        or None if a public type declaration cannot be found.
    """
    if not isinstance(source_code, str):
        raise TypeError("source_code must be a string.")

    # A simple way to remove comments to avoid matching keywords inside them.
    # Remove block comments /* ... */
    code_no_blocks = re.sub(r"/\*.*?\*/", "", source_code, flags=re.DOTALL)
    # Remove line comments // ...
    code_no_comments = re.sub(r"//.*", "", code_no_blocks)

    # Looks for a line like "package com.example.project;"
    package_match = re.search(r"^\s*package\s+([\w\.]+);", code_no_comments, re.MULTILINE)
    package_name = package_match.group(1) if package_match else None

    # Looks for "public class MyClass", "public interface MyInterface", etc.
    # It prioritizes the public type, as is standard for Java files.
    # Regex breakdown:
    # \s*                     - optional leading whitespace
    # (?:public\s+)?          - an optional "public " group
    # (?:abstract\s+|final\s+)? - optional "abstract " or "final "
    # (class|interface|enum|record) - matches the type keyword
    # \s+                     - one or more spaces
    # ([a-zA-Z_]\w*)          - captures the valid Java identifier for the name
    type_match = re.search(
        r"public\s+(?:abstract\s+|final\s+)?(class|interface|enum|record)\s+([a-zA-Z_]\w*)",
        code_no_comments
    )

    # If no public type is found, fall back to any top-level type
    if not type_match:
        type_match = re.search(
            r"^(?:public\s+|protected\s+|private\s+)?\s*(?:abstract\s+|static\s+|final\s+|sealed\s+)?(class|interface|enum|record)\s+([a-zA-Z_]\w*)",
            code_no_comments,
            re.MULTILINE
        )

    class_name = type_match.group(2) if type_match else None

    # 3. If no class/type name was found, we can't proceed.
    if not class_name:
        return None

    # 4. Combine package and class name to form the FQN.
    if package_name:
        return f"{package_name}.{class_name}"
    else:
        # If no package, the FQN is just the class name.
        return class_name
