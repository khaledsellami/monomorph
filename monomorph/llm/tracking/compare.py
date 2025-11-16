import re
from difflib import unified_diff


class CompilationLogComparator:
    def __init__(self):
        # Common timestamp patterns
        self.timestamp_patterns = [
            # ISO format: 2024-01-15T10:30:45.123Z
            re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?'),
            # Maven format: [10:30:45] or [2024-01-15 10:30:45]
            re.compile(r'\[\d{2}:\d{2}:\d{2}\]'),
            re.compile(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]'),
            # Gradle format: 10:30:45.123
            re.compile(r'\d{2}:\d{2}:\d{2}\.\d{3}'),
            # General timestamp formats
            re.compile(r'\d{1,2}:\d{2}:\d{2}(?:\.\d{3})?(?:\s*[AP]M)?'),
            # Date formats
            re.compile(r'\d{4}-\d{2}-\d{2}'),
            re.compile(r'\d{2}/\d{2}/\d{4}'),
        ]

        # Build-specific patterns
        self.build_patterns = [
            # Execution times: "Execution time: 1.234s", "took 5.67 seconds"
            re.compile(r'(?:execution time|took|completed in)[:\s]+\d+(?:\.\d+)?(?:s|ms|seconds|milliseconds)',
                       re.IGNORECASE),
            # Execution time: "950ms"
            re.compile(r'\d+(?:\.\d+)?(?:ms|s|seconds)', re.IGNORECASE),
            # Memory usage: "Memory: 512MB", "Heap: 1.2GB"
            re.compile(r'(?:memory|heap)[:\s]+\d+(?:\.\d+)?(?:MB|GB|KB)', re.IGNORECASE),
            # Process/Thread IDs
            re.compile(r'(?:PID|TID|Thread)[:\s#]+\d+', re.IGNORECASE),
            # Build session IDs or hashes
            re.compile(r'(?:session|build|task)[:\s-]+[a-f0-9]{8,}', re.IGNORECASE),
            # Temporary file references
            re.compile(r'/tmp/[a-zA-Z0-9_-]+'),
            re.compile(r'\\temp\\[a-zA-Z0-9_-]+'),
            # Remove our line numbers (e.g. "L27: ")
            re.compile(r'L\d+\s*:\s*'),
        ]

    def normalize_log_line(self, log_content: str) -> str:
        """
        Normalize a compilation log by removing timestamps and variable elements.

        Args:
            log_content: The raw log content

        Returns:
            Normalized log content
        """
        normalized = log_content

        # Remove timestamps
        for pattern in self.timestamp_patterns:
            normalized = pattern.sub('[TIMESTAMP]', normalized)

        # Remove build-specific data
        for pattern in self.build_patterns:
            normalized = pattern.sub('[BUILD_DATA]', normalized)

        # Remove empty lines and normalize whitespace
        lines = [line.strip() for line in normalized.split('\n') if line.strip()]
        sorted_lines = list(sorted(lines))
        normalized = '\n'.join(sorted_lines)

        return normalized

    def extract_error_messages(self, log_content: str) -> list[str]:
        """
        Extract compilation error messages from the log.

        Returns:
            list of error message strings
        """
        errors = []
        lines = log_content.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()

            # Java compilation errors
            if re.search(r'error:', line, re.IGNORECASE):
                errors.append(line)
                # Include context (file location, error details)
                if i > 0:
                    prev_line = lines[i - 1].strip()
                    if prev_line and not prev_line.startswith('['):
                        errors.append(prev_line)

            # Maven compilation failure
            elif '[ERROR]' in line and any(keyword in line.lower() for keyword in ['compilation', 'compile', 'error']):
                errors.append(line)

            # Gradle compilation failure  
            elif line.startswith('> ') and 'error' in line.lower():
                errors.append(line)

            # Generic compilation errors
            elif any(pattern in line.lower() for pattern in
                     ['compilation failed', 'build failed', 'cannot find symbol']):
                errors.append(line)

        return errors

    def has_compilation_error_changed(self, previous_log: str, current_log: str,
                                      compare_full_log: bool = False) -> bool:
        """
        Compare two compilation logs to determine if the error changed.

        Args:
            previous_log: Previous compilation log content
            current_log: Current compilation log content  
            compare_full_log: If True, compare full normalized logs. If False, compare only error messages.

        Returns:
            True if the compilation error has changed, False otherwise
        """
        if compare_full_log:
            # Compare full normalized logs
            normalized_previous = self.normalize_log_line(previous_log)
            normalized_current = self.normalize_log_line(current_log)
            return normalized_previous != normalized_current
        else:
            # Compare only error messages
            previous_errors = self.extract_error_messages(previous_log)
            current_errors = self.extract_error_messages(current_log)

            # Normalize error messages
            normalized_previous_errors = [self.normalize_log_line(error) for error in previous_errors]
            normalized_current_errors = [self.normalize_log_line(error) for error in current_errors]

            return normalized_previous_errors != normalized_current_errors
        
    def normalize_log(self, log_content: str, compare_full_log: bool = False) -> str:
        """
        Normalize a compilation log by removing timestamps and variable elements.

        Args:
            log_content: The raw log content
            compare_full_log: If True, normalize the full log content. If False, normalize only error messages.
        Returns:
            Normalized log content
        """
        if compare_full_log:
            return self.normalize_log_line(log_content)
        else:
            errors = self.extract_error_messages(log_content)
            sorted_errors = list(sorted(errors))
            return '\n'.join(self.normalize_log_line(error) for error in sorted_errors)

    def get_error_diff(self, previous_log: str, current_log: str) -> str:
        """
        Get a human-readable diff of the compilation errors.

        Returns:
            String containing the diff, or empty string if no changes
        """
        previous_errors = self.extract_error_messages(previous_log)
        current_errors = self.extract_error_messages(current_log)

        # Normalize error messages
        normalized_previous = [self.normalize_log_line(error) for error in previous_errors]
        normalized_current = [self.normalize_log_line(error) for error in current_errors]

        if normalized_previous == normalized_current:
            return ""

        diff_lines = list(unified_diff(
            normalized_previous,
            normalized_current,
            fromfile='Previous Compilation',
            tofile='Current Compilation',
            lineterm=''
        ))
        return '\n'.join(diff_lines)
