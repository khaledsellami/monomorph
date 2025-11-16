import unittest


from monomorph.assembly.entrypoint.java_argparser import find_java_main_class


class TestFindJavaMainClass(unittest.TestCase):

    def test_basic_class_list(self):
        cmd = ["java", "com.example.Main"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Main")

    def test_basic_class_string(self):
        cmd = "java com.example.Main"
        self.assertEqual(find_java_main_class(cmd), "com.example.Main")

    def test_class_with_options_list(self):
        cmd = ["java", "-cp", "app.jar:/libs/*", "com.example.Main", "--server.port=8080"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Main")

    def test_class_with_options_string(self):
        cmd = 'java -Xmx512m -Dproperty=value myapp.MainApp arg1 arg2'
        self.assertEqual(find_java_main_class(cmd), "myapp.MainApp")

    def test_jar_specification_list(self):
        cmd = ["java", "-jar", "my-app.jar", "arg1"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_jar_specification_string(self):
        cmd = "java -Xms1G -jar my-app.jar"
        self.assertIsNone(find_java_main_class(cmd))

    def test_module_with_class_list_m(self):
        cmd = ["java", "-p", "mods", "-m", "my.module/com.example.Starter", "arg1"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Starter")

    def test_module_with_class_list_module(self):
        cmd = ["java", "--module-path", "mods", "--module", "my.module/com.example.Starter"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Starter")

    def test_module_with_class_string(self):
        cmd = "java -m my.module/com.example.another.App"
        self.assertEqual(find_java_main_class(cmd), "com.example.another.App")

    def test_module_without_class_list(self):
        cmd = ["java", "-m", "my.module"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_module_without_class_string(self):
        cmd = "java --module my.module --add-exports java.base/sun.nio.ch=ALL-UNNAMED"
        self.assertIsNone(find_java_main_class(cmd))

    def test_source_file_list(self):
        cmd = ["java", "MySimpleApp.java"]
        self.assertEqual(find_java_main_class(cmd), "MySimpleApp.java")

    def test_source_file_string_with_options(self):
        cmd = "java --enable-preview --source 17 MyProgram.java arg1"
        self.assertEqual(find_java_main_class(cmd), "MyProgram.java")

    def test_source_file_string_simple(self):
        cmd = "java MyScript.java --input file.txt"
        self.assertEqual(find_java_main_class(cmd), "MyScript.java")

    def test_invalid_source_path(self):
        # Contains '/' - not allowed for direct source execution this way
        cmd = ["java", "com/example/MyClass.java"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_simple_class_name_list(self):
        cmd = ["/usr/bin/java", "-cp", ".", "Main", "a", "b"]
        self.assertEqual(find_java_main_class(cmd), "Main")

    def test_java_with_full_path(self):
        cmd = "/opt/jdk/bin/java -cp app.jar com.example.App"
        self.assertEqual(find_java_main_class(cmd), "com.example.App")

    def test_empty_command(self):
        self.assertIsNone(find_java_main_class(""))
        self.assertIsNone(find_java_main_class([]))

    def test_minimal_command(self):
        self.assertIsNone(find_java_main_class("java"))
        self.assertIsNone(find_java_main_class(["java"]))
        self.assertIsNone(find_java_main_class(["/bin/java"]))

    def test_malformed_option_jar(self):
        cmd = ["java", "-jar"] # Missing jarfile argument
        self.assertIsNone(find_java_main_class(cmd))

    def test_malformed_option_m(self):
        cmd = ["java", "-m"] # Missing module argument
        self.assertIsNone(find_java_main_class(cmd))

    def test_malformed_option_cp(self):
         # Could be interpreted as Main being the classpath, which is wrong.
         # The current logic skips -cp and then looks for the next non-option.
         cmd = ["java", "-cp", "Main"]
         self.assertIsNone(find_java_main_class(cmd)) # Expect None as Main is consumed as cp arg

    def test_malformed_module_class_slash_only(self):
        cmd = ["java", "-m", "mymod/"]
        self.assertIsNone(find_java_main_class(cmd)) # Invalid class name

    def test_malformed_module_class_double_slash(self):
        # shlex might interpret this differently, but the pattern should reject //
        cmd = "java -m mymod//BadClass"
        # Depending on shlex, "//BadClass" might be one token.
        # The regex check `^[a-zA-Z_$][\w$.]*$` inside should fail "BadClass" because it follows "//"
        # Let's test the list form for certainty:
        cmd_list = ["java", "-m", "mymod//BadClass"]
        self.assertIsNone(find_java_main_class(cmd_list)) # Invalid class name part

    def test_class_name_looks_like_option(self):
        # Edge case: class name starts with - but isn't a known option
        # This *should* ideally be identified if it follows the rules, but the current
        # simple option skipping might mistake it for an option. Let's see.
        cmd = ["java", "-cp", ".", "-NotAnOptionClass"]
        # Expected: The current logic will see "-NotAnOptionClass" as an option and skip it.
        self.assertIsNone(find_java_main_class(cmd))

    def test_no_java_command(self):
        cmd = ["echo", "hello", "world"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_jar_without_override(self):
        cmd = ["java", "-jar", "my-app.jar", "arg1"]
        self.assertIsNone(find_java_main_class(cmd), "Should be None when -jar is used without -e/--main-class")

    def test_jar_with_e_override_list(self):
        cmd = ["java", "-jar", "my-app.jar", "-e", "com.example.Launcher", "arg1"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Launcher")

    def test_jar_with_main_class_override_list(self):
        cmd = ["java", "-jar", "my-app.jar", "--main-class", "com.example.Launcher", "arg1"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Launcher")

    def test_jar_with_e_override_string(self):
        cmd = "java -Xmx1g -jar my-app.jar -e com.example.AnotherEntry --foo bar"
        self.assertEqual(find_java_main_class(cmd), "com.example.AnotherEntry")

    def test_jar_with_main_class_override_string(self):
        cmd = "java -jar target/app.jar --main-class my.package.StartHere"
        self.assertEqual(find_java_main_class(cmd), "my.package.StartHere")

    def test_e_override_before_jar(self):
        # Order shouldn't matter for detection, although unusual cmd line
        cmd = ["java", "-e", "com.example.Launcher", "-jar", "my-app.jar", "arg1"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Launcher")

    def test_main_class_override_before_jar(self):
        cmd = ["java", "--main-class", "com.example.Launcher", "-jar", "my-app.jar"]
        self.assertEqual(find_java_main_class(cmd), "com.example.Launcher")

    def test_e_override_without_jar(self):
        # Technically valid for the parser, even if java might complain
        cmd = ["java", "-cp", ".", "-e", "com.example.SpecialEntry"]
        self.assertEqual(find_java_main_class(cmd), "com.example.SpecialEntry")

    def test_main_class_override_without_jar(self):
        cmd = ["java", "--main-class", "com.example.SpecialEntry", "-cp", "."]
        self.assertEqual(find_java_main_class(cmd), "com.example.SpecialEntry")

    def test_jar_with_positional_class_ignored(self):
        # Positional class is ignored when -jar is present (unless -e is used)
        cmd = ["java", "-jar", "app.jar", "com.example.IgnoredMain", "arg1"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_jar_with_e_and_positional_ignored(self):
        cmd = ["java", "-jar", "app.jar", "-e", "com.example.RealMain", "com.example.IgnoredMain", "arg1"]
        self.assertEqual(find_java_main_class(cmd), "com.example.RealMain")

    def test_malformed_option_e(self):
        cmd = ["java", "-jar", "app.jar", "-e"]  # Missing classname argument
        self.assertIsNone(find_java_main_class(cmd))

    def test_malformed_option_main_class(self):
        cmd = ["java", "-jar", "app.jar", "--main-class"]  # Missing classname argument
        self.assertIsNone(find_java_main_class(cmd))

    def test_malformed_option_e_invalid_class(self):
        cmd = ["java", "-jar", "app.jar", "-e", "invalid-class-name!"]
        self.assertIsNone(find_java_main_class(cmd))

    def test_module_takes_precedence_over_e(self):
        # -m module/class should win even if -e is present
        cmd = ["java", "-m", "my.mod/com.example.ModMain", "-e", "com.example.OtherMain"]
        self.assertEqual(find_java_main_class(cmd), "com.example.ModMain")