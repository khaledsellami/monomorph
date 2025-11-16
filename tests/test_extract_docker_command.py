import unittest

from monomorph.assembly.entrypoint.java_argparser import extract_docker_command


class TestDockerCommandFormatter(unittest.TestCase):
    def test_simple_cmd_exec_form(self):
        dockerfile_line = 'CMD ["nginx", "-g", "daemon off;"]'
        expected_output = 'nginx -g daemon off;'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_simple_cmd_with_space(self):
        dockerfile_line = 'CMD [ "nginx", "-g", "daemon off;" ]'
        expected_output = 'nginx -g daemon off;'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_entrypoint_and_cmd_exec_form(self):
        dockerfile_line = 'ENTRYPOINT ["/usr/bin/nginx"] \n CMD ["-g", "daemon off;"]'
        expected_output = '/usr/bin/nginx -g daemon off;'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_complex_entrypoint_and_cmd(self):
        dockerfile_line = 'ENTRYPOINT ["python", "-m", "flask", "run"] \n CMD ["--host=0.0.0.0"]'
        expected_output = 'python -m flask run --host=0.0.0.0'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_cmd_shell_form(self):
        dockerfile_line = 'CMD echo "Hello World"'
        expected_output = 'echo "Hello World"'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_entrypoint_shell_and_cmd_exec(self):
        dockerfile_line = 'ENTRYPOINT /docker-entrypoint.sh \n CMD ["postgres"]'
        expected_output = '/docker-entrypoint.sh postgres'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_entrypoint_exec_shell_cmd_exec(self):
        dockerfile_line = 'ENTRYPOINT ["sh", "-c"] \n CMD ["echo $HOME"]'
        expected_output = 'sh -c echo $HOME'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_cmd_exec_with_jar(self):
        dockerfile_line = 'CMD ["java", "-jar", "app.jar"]'
        expected_output = 'java -jar app.jar'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_bash_entrypoint_with_cmd(self):
        dockerfile_line = 'ENTRYPOINT ["/bin/bash", "-c"] \n CMD ["echo Hello World"]'
        expected_output = '/bin/bash -c echo Hello World'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_with_other_directives_between(self):
        dockerfile_line = 'ENTRYPOINT ["/bin/bash", "-c"] \n COPY . . \n CMD ["echo Hello World"]'
        expected_output = '/bin/bash -c echo Hello World'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_cmd_before_entrypoint(self):
        dockerfile_line = 'CMD ["echo Hello World"] \n ENTRYPOINT ["/bin/bash", "-c"]'
        expected_output = '/bin/bash -c echo Hello World'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)

    def test_multiple_entrypoints(self):
        dockerfile_line = 'CMD ["echo Hello World"] \n ENTRYPOINT ["/bin/bash", "-c"] \n ENTRYPOINT ["/bin/bash", "-other"]'
        expected_output = '/bin/bash -other echo Hello World'
        self.assertEqual(extract_docker_command(dockerfile_line), expected_output)