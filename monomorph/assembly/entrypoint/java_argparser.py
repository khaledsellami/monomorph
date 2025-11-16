import shlex
import re


def find_java_main_class(command_line: str | list[str]) -> str | None:
    """
    Parses a Java command line string or list to find the main class.

    Handles different java command syntaxes:
    - java [options] mainclass [args ...]
    - java [options] -m module/mainclass [args ...]
    - java [options] --module module/mainclass [args ...]
    - java [options] source-file [args ...]
    - java [options] -jar jarfile [-e|--main-class CLASSNAME] [args ...]

    Ignores main class specification via -jar (unless overridden by -e/--main-class)
    or module-only (-m/--module).

    Args:
        command_line: A string representing the full java command,
                      or a list of strings already split (e.g., from Dockerfile JSON).

    Returns:
        The identified main class name (String) or source file name (String),
        or None if no explicit main class is specified on the command line
        (e.g., relying on JAR manifest without -e/--main-class).
    """
    if isinstance(command_line, str):
        try:
            args = shlex.split(command_line, posix=True)
        except ValueError as e:
            print(f"Warning: Could not parse command line: {e}")
            return None
    elif isinstance(command_line, list):
        args = command_line
    else:
        raise TypeError("command_line must be a string or a list of strings")

    if not args:
        return None

    # Find the 'java' executable
    java_index = -1
    for i, arg in enumerate(args):
        if re.search(r'(?:^|[/\\:])java(?:.exe)?$', arg):
            java_index = i
            break
    if java_index == -1:
        try: # Fallback for exact 'java' match if path search failed
            java_index = args.index('java')
        except ValueError:
            return None # 'java' command not found

    # --- State variables during parsing ---
    main_class_found = None
    in_jar_mode = False
    # Priority: -m/--module > -e/--main-class > positional/source-file

    i = java_index + 1
    while i < len(args):
        arg = args[i]

        # --- Check for specific syntaxes first ---
        # 1. Module specification with main class (highest priority)
        if arg in ("-m", "--module"):
            if i + 1 < len(args):
                module_arg = args[i+1]
                if "/" in module_arg:
                    parts = module_arg.split("/", 1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        potential_class = parts[1]
                        if re.match(r"^[a-zA-Z_$][\w$.]*$", potential_class):
                            return potential_class # Found module/class, return immediately
                        else:
                            return None # Invalid class name format in module
                    else:
                         return None # Malformed module/class string
                else:
                    return None # Only module name provided, not class. Stop search.
            else:
                return None # Malformed: -m/--module requires an argument
            # If we got here, it was module-only or malformed - exit

        # 2. JAR file specification - sets mode, continues search for -e/--main-class
        elif arg == "-jar":
            in_jar_mode = True
            i += 1 # Skip '-jar'
            if i < len(args):
                i += 1 # Skip the jarfile argument
            else:
                 return None # Malformed, -jar needs argument
            continue # Continue parsing for other options like -e

        # 3. Main class override for JARs (second priority)
        elif arg in ("-e", "--main-class"):
            if i + 1 < len(args):
                potential_class = args[i+1]
                # Basic validation for the class name argument
                if re.match(r"^[a-zA-Z_$][\w$.]*$", potential_class) and "/" not in potential_class and "\\" not in potential_class:
                    main_class_found = potential_class # Store the override class
                    i += 2 # Skip option and its argument
                    continue # Continue parsing for other options
                else:
                    # Invalid or missing class name after -e/--main-class
                    return None # Or you might want to log an error
            else:
                # Malformed: -e/--main-class requires an argument
                return None

        # --- Handle options (skip them and their potential arguments) ---
        elif arg in ("-cp", "-classpath", "--class-path", "-p", "--module-path", "--upgrade-module-path", "--patch-module", "-d", "--source"):
             i += 1 # Skip the option
             # Skip the argument only if it exists and doesn't look like another option
             if i < len(args) and not args[i].startswith("-"):
                 i += 1
             continue

        elif arg.startswith("-") or arg.startswith("@"):
            # Skip other options (-X, -D, --add-opens, @file etc.)
            i += 1
            continue

        # --- Found a potential positional main class or source file (lowest priority) ---
        else:
            # Only consider this if we are NOT in jar mode AND haven't already found a class via -e/--main-class
            if not in_jar_mode and main_class_found is None:
                potential_main = arg
                is_valid_class = re.match(r"^[a-zA-Z_$][\w$.]*$", potential_main) and "/" not in potential_main and "\\" not in potential_main
                is_valid_source = potential_main.endswith(".java") and "/" not in potential_main and "\\" not in potential_main and re.match(r"^[a-zA-Z_$][\w$]*$", potential_main[:-5])

                if is_valid_class or is_valid_source:
                    main_class_found = potential_main
                    # Found the positional class/source, assume subsequent non-options are args to it
                    # We can stop searching for *this type* of main class.
                    # We still need `break` or similar if we are *certain* no `-e` etc can follow,
                    # but it's safer to let the loop finish to catch all options.
                    # So, just store it and let loop continue. If -e appears later, it will overwrite.
                    i += 1 # Move to the next token (likely program args)
                    continue # Continue parsing (maybe other Java options follow args)
                else:
                    # This token is likely an argument to the main class/source file
                    # or an argument to an unknown option. Stop searching for a positional class.
                    # We can just break or return the current main_class_found (which might be None).
                    # Let's break to treat remaining tokens as program args.
                    break # Treat rest as program arguments
            else:
                # We are in JAR mode (expecting -e or nothing) OR
                # we already found a class via -e/--main-class OR
                # this token doesn't look like a class/source file.
                # Treat it and subsequent tokens as program arguments.
                break # Treat rest as program arguments

    # Loop finished or broke early
    return main_class_found


def extract_docker_command(dockerfile_line: str) -> str:
    """
    Parse Dockerfile ENTRYPOINT and CMD instructions and convert them to the actual
    command that would be executed when the container starts.

    Handles:
    - Exec form: CMD ["nginx", "-g", "daemon off;"] -> nginx -g daemon off;
    - Shell form: CMD echo "Hello World" -> echo "Hello World"
    - Combined ENTRYPOINT and CMD

    Args:
        dockerfile_line (str): A line or block from a Dockerfile containing
                              ENTRYPOINT and/or CMD instructions

    Returns:
        str: The formatted command as it would be executed
    """
    # Find all exec-form commands (with square brackets)
    exec_pattern = r'(ENTRYPOINT|CMD)\s+\[(.*?)\]'
    exec_matches = re.findall(exec_pattern, dockerfile_line)

    # Find all shell-form commands
    shell_pattern = r'(ENTRYPOINT|CMD)\s+([^[].+?)(?=\s*(?:ENTRYPOINT|CMD|$))'
    shell_matches = re.findall(shell_pattern, dockerfile_line)

    entrypoint = None
    cmd = None

    # Process exec-form matches
    for directive, content in exec_matches:
        # Parse the JSON-like array, splitting by commas but respecting quotes
        parts = []
        current_part = ""
        in_quotes = False
        quote_char = None

        for char in content:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current_part += char
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip().strip('"\''))
                current_part = ""
            else:
                current_part += char

        if current_part:
            parts.append(current_part.strip().strip('"\''))

        if directive == "ENTRYPOINT":
            entrypoint = parts
        else:  # CMD
            cmd = parts

    # Process shell-form matches
    for directive, content in shell_matches:
        command = content.strip()
        if directive == "ENTRYPOINT":
            # For shell form, we take the whole command as is
            entrypoint = [command]
            # Shell form implicitly uses /bin/sh -c
            # But we'll keep it simple and just use the command directly
        else:  # CMD
            cmd = [command]

    # Combine ENTRYPOINT and CMD according to Docker rules
    if entrypoint:
        if len(entrypoint) == 1 and not entrypoint[0].startswith("/bin/sh"):
            # If it's shell form or a single command without parameters
            if cmd and len(cmd) == 1 and " " not in cmd[0]:
                # If CMD is a single word, it's treated as a parameter
                return f"{entrypoint[0]} {cmd[0]}"
            elif cmd:
                # If CMD has multiple parts or contains spaces
                return f"{entrypoint[0]} {' '.join(cmd)}"
            else:
                return entrypoint[0]
        else:
            # For exec form with multiple parameters
            result = " ".join(entrypoint)
            if cmd:
                result += " " + " ".join(cmd)
            return result
    elif cmd:
        # Only CMD, no ENTRYPOINT
        if len(cmd) == 1:
            return cmd[0]
        else:
            return " ".join(cmd)

    return ""
