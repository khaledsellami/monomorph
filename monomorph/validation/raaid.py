"""
A module for customized RA.Aid (https://github.com/ai-christianson/RA.Aid) methods
"""
import os
import fnmatch
import logging
from pathlib import Path
from typing import Optional, List

from fuzzywuzzy import process

from .docker import MicroserviceDocker, MicroserviceDockerError

logger = logging.getLogger("momomorph")


DEFAULT_EXCLUDE_PATTERNS = [
    "*.pyc",
    "__pycache__/*",
    ".git/*",
    "*.so",
    "*.o",
]


def fuzzy_find_project_files(
        ms_docker: MicroserviceDocker,
        search_term: str,
        *,
        repo_path: str = ".",
        threshold: int = 60,
        max_results: int = 10,
        include_paths: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        include_hidden: bool = False,
) -> list[tuple[str, int]]:
    """Fuzzy find files in a project matching the search term.

    This tool searches for files within a project directory using fuzzy string matching,
    allowing for approximate matches to the search term. It returns a list of matched
    files along with their match scores. Works with both git and non-git repositories.

    Args:
        ms_docker: MicroserviceDocker instance for accessing the Docker container
        search_term: String to match against file paths
        repo_path: Path to project directory (defaults to current directory)
        threshold: Minimum similarity score (0-100) for matches (default: 60)
        max_results: Maximum number of results to return (default: 10)
        include_paths: Optional list of path patterns to include in search
        exclude_patterns: Optional list of path patterns to exclude from search
        include_hidden: Whether to include hidden files in search (default: False)

    Returns:
        List of tuples containing (file_path, match_score)

    Raises:
        ValueError: If threshold is not between 0 and 100
        MicroserviceDockerError: If there's an error accessing or listing files in the Docker container
    """
    # Combine default and user-provided exclude patterns
    all_exclude_patterns = DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or [])

    # Validate threshold
    if not 0 <= threshold <= 100:
        error_msg = "Threshold must be between 0 and 100"
        raise ValueError(error_msg)

    # Handle empty search term as special case
    if not search_term:
        # Consider if we need to record trajectory here? For now, just return empty.
        # If we did record, it would be a success case with 0 matches.
        return []
    # Get all project files using the common utility function
    all_files = get_all_project_files_docker(
        ms_docker,
        repo_path,
        include_hidden=include_hidden,
        exclude_patterns=all_exclude_patterns  # Use combined list
    )

    # Apply include patterns if specified
    if include_paths:
        included_files = []
        for pattern in include_paths:
            included_files.extend(f for f in all_files if fnmatch.fnmatch(f, pattern))
        # Note: 'all_files' below this point refers to the files *after* include_paths filtering
        all_files = included_files

    # Perform fuzzy matching
    matches = process.extract(search_term, all_files, limit=max_results)

    # Filter by threshold
    filtered_matches = [(path, score) for path, score in matches if score >= threshold]

    return filtered_matches


def get_all_project_files_docker(ms_docker: MicroserviceDocker, directory: str, include_hidden: bool = False,
                                 exclude_patterns: Optional[List[str]] = None) -> List[str]:
    """
    Get a list of all files in a project directory, handling both git and non-git repositories.

    Args:
        ms_docker: MicroserviceDocker instance for accessing the Docker container
        directory: Path to the directory
        include_hidden: Whether to include hidden files (starting with .) in the results
        exclude_patterns: Optional list of patterns to exclude from the results

    Returns:
        List[str]: List of file paths relative to the directory

    Raises:
        MicroserviceDockerError: If there's an error accessing or listing files in the Docker container
    """
    # Default excluded directories
    excluded_dirs = {'.ra-aid', '.venv', '.git', '.aider', '__pycache__'}
    success, all_files, error_log = ms_docker.list_files(directory)
    if not success:
        logger.error(f"Error listing files in directory {directory}: {error_log}")
        raise MicroserviceDockerError(f"Error listing files in directory {directory}: {error_log}")
    # Filter out excluded directories
    all_files = [f for f in all_files if not any([p in excluded_dirs for p in Path(f).parts])]
    # Filter out hidden files if not included
    if not include_hidden:
        all_files = [f for f in all_files if not Path(f).name.startswith('.')]
    # Apply additional exclude patterns if specified
    if exclude_patterns:
        for pattern in exclude_patterns:
            all_files = [f for f in all_files if not fnmatch.fnmatch(f, pattern)]
    # Remove duplicates and sort
    return sorted(set(all_files))


def _is_binary_fallback(filepath):
    """Fallback method to detect binary files without using magic."""
    # Check for known source code file extensions first
    file_ext = os.path.splitext(filepath)[1].lower()
    text_extensions = ['.c', '.cpp', '.h', '.hpp', '.py', '.js', '.html', '.css', '.java',
                       '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.ts', '.json',
                       '.xml', '.yaml', '.yml', '.md', '.txt', '.sh', '.bat', '.cc', '.m',
                       '.mm', '.jsx', '.tsx', '.cxx', '.hxx', '.pl', '.pm']

    if file_ext in text_extensions:
        return False

    # Check if file has C/C++ header includes
    with open(filepath, 'rb') as f:
        content_start = f.read(1024)
        if b'#include' in content_start:
            return False

    # Fall back to content analysis
    return _is_binary_content(filepath)


def _is_binary_content(filepath):
    """Analyze file content to determine if it's binary."""
    try:
        # First check if file is empty
        if os.path.getsize(filepath) == 0:
            return False  # Empty files are not binary

        # Check file content for patterns
        with open(filepath, "rb") as f:
            chunk = f.read(1024)

            # Empty chunk is not binary
            if not chunk:
                return False

            # Check for null bytes which strongly indicate binary content
            if b"\0" in chunk:
                # Even with null bytes, check for common source patterns
                if (b'#include' in chunk or b'#define' in chunk or
                        b'void main' in chunk or b'int main' in chunk):
                    return False
                return True

            # Check for common source code headers/patterns
            source_patterns = [b'#include', b'#ifndef', b'#define', b'function', b'class', b'import',
                               b'package', b'using namespace', b'public', b'private', b'protected',
                               b'void main', b'int main']

            if any(pattern in chunk for pattern in source_patterns):
                return False

            # Try to decode as UTF-8
            try:
                chunk.decode('utf-8')

                # Count various character types to determine if it's text
                control_chars = sum(0 <= byte <= 8 or byte == 11 or byte == 12 or 14 <= byte <= 31 for byte in chunk)
                whitespace = sum(byte == 9 or byte == 10 or byte == 13 or byte == 32 for byte in chunk)
                printable = sum(33 <= byte <= 126 for byte in chunk)

                # Calculate ratios
                control_ratio = control_chars / len(chunk)
                printable_ratio = (printable + whitespace) / len(chunk)

                # Text files have high printable ratio and low control ratio
                if control_ratio < 0.2 and printable_ratio > 0.7:
                    return False

                return True

            except UnicodeDecodeError:
                # Try another encoding if UTF-8 fails
                # latin-1 always succeeds but helps with encoding detection
                latin_chunk = chunk.decode('latin-1')

                # Count the printable vs non-printable characters
                printable = sum(32 <= ord(char) <= 126 or ord(char) in (9, 10, 13) for char in latin_chunk)
                printable_ratio = printable / len(latin_chunk)

                # If more than 70% is printable, it's likely text
                if printable_ratio > 0.7:
                    return False

                return True

    except Exception:
        # If any error occurs, assume binary to be safe
        return True

