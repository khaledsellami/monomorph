import os
from difflib import get_close_matches
from typing import Optional, Any


class ClassChange:
    """A class to track changes made to classes during the error correction process."""

    def __init__(self, class_name: str, initial_path: str | None, container_path: str | None):
        self.class_name = class_name
        self.initial_path = initial_path
        self.container_path = container_path
        self.changes_log = []


class ClassChangeHistory:
    """A class to track changes made to classes during the error correction process."""

    def __init__(self, generated_classes: dict[str, ClassChange] = None,
                 relevant_classes: dict[str, ClassChange] = None):
        self.generated_classes: dict[str, ClassChange] = generated_classes or dict()
        self.relevant_classes: dict[str, ClassChange] = relevant_classes or dict()
        self.new_classes: dict[str, ClassChange] = dict()

    def get_with_class_name(self, class_name: str) -> Optional[ClassChange]:
        """
        Retrieve the ClassChange object for a given class name.
        If the class name is not found, return None.
        """
        for change_dict in [self.generated_classes, self.relevant_classes, self.new_classes]:
            if class_name in change_dict:
                return change_dict[class_name]
        return None

    def get_with_container_path(self, container_path: str) -> Optional[ClassChange]:
        """
        Retrieve the ClassChange object for a given container path.
        If the container path is not found, return None.
        """
        for change_dict in [self.generated_classes, self.relevant_classes, self.new_classes]:
            for change in change_dict.values():
                if change.container_path == container_path and change.container_path is not None:
                    return change
        return None


class FileContextManager:
    def __init__(self, refactoring_details: dict[str, tuple[str, str]],
                 class_change_history: Optional[ClassChangeHistory] = None):
        self.refactoring_details = refactoring_details
        self.class_change_history = class_change_history
        self._create_lookup_indexes()

    def _create_lookup_indexes(self):
        """Create various indexes for faster lookups."""
        self.basename_to_path = {}
        self.class_name_to_path = {}
        self.normalized_path_to_path = {}
        self.container_path_to_original = {}

        for file_path in self.refactoring_details.keys():
            # Index by basename
            basename = os.path.basename(file_path)
            if basename not in self.basename_to_path:
                self.basename_to_path[basename] = []
            self.basename_to_path[basename].append(file_path)

            # Index by potential class name (filename without extension)
            class_name = os.path.splitext(basename)[0]
            if class_name not in self.class_name_to_path:
                self.class_name_to_path[class_name] = []
            self.class_name_to_path[class_name].append(file_path)

            # Index by normalized path
            normalized = self._normalize_path(file_path)
            self.normalized_path_to_path[normalized] = file_path

        # Create mappings for moved/changed files if history is available
        if self.class_change_history:
            self._create_change_mappings()

    def _create_change_mappings(self):
        """Create mappings between current file locations and original context."""
        # Map current container paths to original file paths in refactoring_details
        for change_dict in [self.class_change_history.generated_classes,
                            self.class_change_history.relevant_classes,
                            self.class_change_history.new_classes]:
            for class_name, class_change in change_dict.items():
                if class_change.container_path and class_change.initial_path:
                    # If the initial path exists in refactoring_details, map current container to it
                    if class_change.initial_path in self.refactoring_details:
                        self.container_path_to_original[class_change.container_path] = class_change.initial_path

                    # Also try to match by class name if initial path not found
                    elif class_name in self.class_name_to_path:
                        # Find the most likely original path for this class
                        potential_originals = self.class_name_to_path[class_name]
                        if potential_originals:
                            # Prefer the path that's most similar to the initial path
                            best_match = min(potential_originals,
                                             key=lambda p: self._path_distance(p, class_change.initial_path or ''))
                            self.container_path_to_original[class_change.container_path] = best_match

    def _path_distance(self, path1: str, path2: str) -> int:
        """Calculate a simple distance between two paths."""
        if not path1 or not path2:
            return float('inf')

        # Simple distance based on common path components
        parts1 = self._normalize_path(path1).split('/')
        parts2 = self._normalize_path(path2).split('/')
        common_parts = 0
        for p1, p2 in zip(parts1, parts2):
            if p1 == p2:
                common_parts += 1
            else:
                break

    def find_file_context(self, query: str) -> Optional[tuple[str, str, str]]:
        """
        Find file context with improved matching.
        Returns (matched_path, prompt, reasoning) or None.
        """
        # Direct match
        if query in self.refactoring_details:
            prompt, reasoning = self.refactoring_details[query]
            return query, prompt, reasoning

        # Try various lookup strategies including change history
        strategies = [
            lambda q: self._try_direct_match(q),
            lambda q: self._try_change_history_match(q),
            lambda q: self._try_basename_match(q),
            lambda q: self._try_class_name_match(q),
            lambda q: self._try_normalized_path_match(q),
            lambda q: self._try_fuzzy_match(q),
            lambda q: self._try_contains_match(q)
        ]

        for strategy in strategies:
            result = strategy(query)
            if result:
                return result

        return None

    def _try_direct_match(self, query: str) -> Optional[tuple[str, str, str]]:
        """Try direct match against refactoring_details keys."""
        if query in self.refactoring_details:
            prompt, reasoning = self.refactoring_details[query]
            return query, prompt, reasoning
        return None

    def _try_change_history_match(self, query: str) -> Optional[tuple[str, str, str]]:
        """Try to match using change history to find moved/renamed files."""
        if not self.class_change_history:
            return None

        # Strategy 1: Query is a current container path, find original
        if query in self.container_path_to_original:
            original_path = self.container_path_to_original[query]
            if original_path in self.refactoring_details:
                prompt, reasoning = self.refactoring_details[original_path]
                return original_path, prompt, reasoning

        # Strategy 2: Query is a class name, find through change history
        class_change = self.class_change_history.get_with_class_name(query)
        if class_change and class_change.initial_path:
            if class_change.initial_path in self.refactoring_details:
                prompt, reasoning = self.refactoring_details[class_change.initial_path]
                return class_change.initial_path, prompt, reasoning

        # Strategy 3: Query might be a container path, find through change history
        class_change = self.class_change_history.get_with_container_path(query)
        if class_change and class_change.initial_path:
            if class_change.initial_path in self.refactoring_details:
                prompt, reasoning = self.refactoring_details[class_change.initial_path]
                return class_change.initial_path, prompt, reasoning

        # Strategy 4: Check if query matches current container path partially
        normalized_query = self._normalize_path(query)
        for container_path, original_path in self.container_path_to_original.items():
            if (normalized_query in self._normalize_path(container_path) or
                    self._normalize_path(container_path) in normalized_query):
                if original_path in self.refactoring_details:
                    prompt, reasoning = self.refactoring_details[original_path]
                    return original_path, prompt, reasoning

        # Strategy 5: Try basename matching with change history
        query_basename = os.path.basename(query)
        for change_dict in [self.class_change_history.generated_classes,
                            self.class_change_history.relevant_classes,
                            self.class_change_history.new_classes]:
            for class_name, class_change in change_dict.items():
                if class_change.container_path and class_change.initial_path:
                    container_basename = os.path.basename(class_change.container_path)
                    if query_basename == container_basename:
                        if class_change.initial_path in self.refactoring_details:
                            prompt, reasoning = self.refactoring_details[class_change.initial_path]
                            return class_change.initial_path, prompt, reasoning

        return None

    def _try_basename_match(self, query: str) -> Optional[tuple[str, str, str]]:
        basename = os.path.basename(query)
        if basename in self.basename_to_path:
            # If multiple matches, prefer the shortest path (most specific)
            best_match = min(self.basename_to_path[basename], key=len)
            prompt, reasoning = self.refactoring_details[best_match]
            return best_match, prompt, reasoning
        return None

    def _try_class_name_match(self, query: str) -> Optional[tuple[str, str, str]]:
        # Try query as class name
        if query in self.class_name_to_path:
            best_match = min(self.class_name_to_path[query], key=len)
            prompt, reasoning = self.refactoring_details[best_match]
            return best_match, prompt, reasoning
        return None

    def _try_normalized_path_match(self, query: str) -> Optional[tuple[str, str, str]]:
        normalized = self._normalize_path(query)
        if normalized in self.normalized_path_to_path:
            matched_path = self.normalized_path_to_path[normalized]
            prompt, reasoning = self.refactoring_details[matched_path]
            return matched_path, prompt, reasoning
        return None

    def _try_fuzzy_match(self, query: str) -> Optional[tuple[str, str, str]]:
        available_keys = list(self.refactoring_details.keys())
        close_matches = get_close_matches(query, available_keys, n=1, cutoff=0.7)
        if close_matches:
            matched_path = close_matches[0]
            prompt, reasoning = self.refactoring_details[matched_path]
            return matched_path, prompt, reasoning
        return None

    def _try_contains_match(self, query: str) -> Optional[tuple[str, str, str]]:
        # Check if query is contained in any path or vice versa
        for file_path in self.refactoring_details.keys():
            if query in file_path or file_path in query:
                prompt, reasoning = self.refactoring_details[file_path]
                return file_path, prompt, reasoning
        return None

    def get_debug_info(self) -> dict[str, Any]:
        """Get debug information about current mappings."""
        debug_info = {
            'refactoring_details_keys': list(self.refactoring_details.keys()),
            'basename_index': dict(self.basename_to_path),
            'class_name_index': dict(self.class_name_to_path),
            'container_to_original_mappings': dict(self.container_path_to_original),
        }

        if self.class_change_history:
            debug_info['change_history'] = {
                'generated_classes': {name: {
                    'class_name': change.class_name,
                    'initial_path': change.initial_path,
                    'container_path': change.container_path
                } for name, change in self.class_change_history.generated_classes.items()},
                'relevant_classes': {name: {
                    'class_name': change.class_name,
                    'initial_path': change.initial_path,
                    'container_path': change.container_path
                } for name, change in self.class_change_history.relevant_classes.items()},
                'new_classes': {name: {
                    'class_name': change.class_name,
                    'initial_path': change.initial_path,
                    'container_path': change.container_path
                } for name, change in self.class_change_history.new_classes.items()}
            }

        return debug_info

    def _normalize_path(self, path: str) -> str:
        return path.strip('/\\').replace('\\', '/')