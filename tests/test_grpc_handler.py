import unittest
import os
import shutil
import tempfile
import logging
import re

from monomorph.execution.dependency.buildfile import GRPC_VERSION, PROTOBUF_VERSION, ANNOTATION_API_VERSION, \
    CAFFEINE_VERSION, MAPSTRUCT_VERSION
from monomorph.execution.dependency.gradle import (GRADLE_PROTOBUF_PLUGIN_VERSION)
from monomorph.execution.dependency.maven import (OS_MAVEN_PLUGIN_VERSION, PROTOBUF_MAVEN_PLUGIN_VERSION,
                                                  MAVEN_COMPILER_PLUGIN_VERSION)
from monomorph.execution.dependency.dependency import GrpcDependencyHandler


class TestGrpcDependencyHandler(unittest.TestCase):

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

    def test_gradle(self):
        """Test full integration of adding dependencies and plugins with gradle."""
        filepath = self._create_dummy_file("build_full_integration.gradle", FULL_EXAMPLE_GRADLE)
        output_path = os.path.join(self.test_dir, "build_full_integration_out.gradle")
        dependency_handler = GrpcDependencyHandler(filepath, "17", output_path=output_path,
                                                   build_tool="gradle")
        dependency_handler.add_dependencies()
        self.assertTrue(dependency_handler._added_dependencies)
        # Check the output file
        self.assertTrue(os.path.exists(output_path))
        output_content = self._read_file_content(output_path)
        stripped_output_lines = [line.strip() for line in output_content.split("\n") if line.strip()]
        stripped_expected_lines = [line.strip() for line in EXPECTED_FULL_EXAMPLE_GRADLE.split("\n") if line.strip()]
        # self.assertListEqual(stripped_output_lines, stripped_expected_lines)
        self.assertEqual("\n".join(stripped_expected_lines), "\n".join(stripped_output_lines))

    def test_maven(self):
        """Test full integration of adding dependencies and plugins with maven."""
        filepath = self._create_dummy_file("pom_full_integration.xml", FULL_EXAMPLE_POM)
        output_path = os.path.join(self.test_dir, "pom_full_integration_out.xml")
        dependency_handler = GrpcDependencyHandler(filepath, "11", output_path=output_path,
                                                   build_tool="maven")
        dependency_handler.add_dependencies()
        self.assertTrue(dependency_handler._added_dependencies)
        # Check the output file
        self.assertTrue(os.path.exists(output_path))
        output_content = self._read_file_content(output_path)
        stripped_output_lines = [line.strip() for line in output_content.split("\n") if line.strip()]
        stripped_expected_lines = [line.strip() for line in EXPECTED_FULL_EXAMPLE_POM.split("\n") if line.strip()]
        self.assertEqual("\n".join(stripped_expected_lines), "\n".join(stripped_output_lines))

    def test_gradle_server_with_existing_dep(self):
        """Test full integration of adding dependencies and plugins with gradle when a dependency already exists."""
        filepath = self._create_dummy_file("build_full_integration.gradle", FULL_EXAMPLE_GRADLE)
        output_path = os.path.join(self.test_dir, "build_full_integration_out.gradle")
        dependency_handler = GrpcDependencyHandler(filepath, "17", output_path=output_path,
                                                   build_tool="gradle", mode="server")
        dependency_handler.add_dependencies()
        self.assertTrue(dependency_handler._added_dependencies)
        # Check the output file
        self.assertTrue(os.path.exists(output_path))
        output_content = self._read_file_content(output_path)
        stripped_output_lines = [line.strip() for line in output_content.split("\n") if line.strip()]
        stripped_expected_lines = [line.strip() for line in EXPECTED_FULL_EXAMPLE_GRADLE_SERVER.split("\n") if line.strip()]
        # self.assertListEqual(stripped_output_lines, stripped_expected_lines)
        # Since the gradle project already has caffeine, the dependency should not be added again
        self.assertEqual("\n".join(stripped_expected_lines), "\n".join(stripped_output_lines))

    def test_gradle_server(self):
        """Test full integration of adding dependencies and plugins with gradle when using server mode."""
        FULL_EXAMPLE_GRADLE_WITHOUT_CAFFEINE = re.sub(r"\n\s*runtimeOnly 'com.github.ben-manes.caffeine:caffeine'",
                                                      "", FULL_EXAMPLE_GRADLE)
        filepath = self._create_dummy_file("build_full_integration.gradle", FULL_EXAMPLE_GRADLE_WITHOUT_CAFFEINE)
        output_path = os.path.join(self.test_dir, "build_full_integration_out.gradle")
        dependency_handler = GrpcDependencyHandler(filepath, "17", output_path=output_path,
                                                   build_tool="gradle", mode="server")
        dependency_handler.add_dependencies()
        self.assertTrue(dependency_handler._added_dependencies)
        # Check the output file
        self.assertTrue(os.path.exists(output_path))
        output_content = self._read_file_content(output_path)
        stripped_output_lines = [line.strip() for line in output_content.split("\n") if line.strip()]
        stripped_expected_lines = [line.strip() for line in EXPECTED_FULL_EXAMPLE_GRADLE_SERVER_WITHOUT_CAFFEINE.split("\n") if line.strip()]
        # self.assertListEqual(stripped_output_lines, stripped_expected_lines)
        self.assertEqual("\n".join(stripped_expected_lines), "\n".join(stripped_output_lines))

    def test_maven_server(self):
        """Test full integration of adding dependencies and plugins with maven when using server mode."""
        filepath = self._create_dummy_file("pom_full_integration.xml", FULL_EXAMPLE_POM)
        output_path = os.path.join(self.test_dir, "pom_full_integration_out.xml")
        dependency_handler = GrpcDependencyHandler(filepath, "11", output_path=output_path,
                                                   build_tool="maven", mode="server")
        dependency_handler.add_dependencies()
        self.assertTrue(dependency_handler._added_dependencies)
        # Check the output file
        self.assertTrue(os.path.exists(output_path))
        output_content = self._read_file_content(output_path)
        expected_content = EXPECTED_FULL_EXAMPLE_POM_SERVER.replace("{java_version}", "11")
        stripped_output_lines = [line.strip() for line in output_content.split("\n") if line.strip()]
        stripped_expected_lines = [line.strip() for line in expected_content.split("\n") if line.strip()]
        self.assertEqual("\n".join(stripped_expected_lines), "\n".join(stripped_output_lines))




FULL_EXAMPLE_GRADLE = """
plugins {
  id 'org.springframework.boot' version '3.0.1'
  id 'io.spring.dependency-management' version '1.1.0'
  id 'java'
}

apply plugin: 'java'

group = 'org.springframework.samples'
version = '3.0.0'
sourceCompatibility = '17'

repositories {
  mavenCentral()
}

ext.webjarsFontawesomeVersion = "4.7.0"
ext.webjarsBootstrapVersion = "5.1.3"

dependencies {
  implementation 'org.springframework.boot:spring-boot-starter-cache'
  implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
  implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
  implementation 'org.springframework.boot:spring-boot-starter-web'
  implementation 'org.springframework.boot:spring-boot-starter-validation'
  implementation 'javax.cache:cache-api'
  implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
  runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
  runtimeOnly "org.webjars.npm:bootstrap:${webjarsBootstrapVersion}"
  runtimeOnly "org.webjars.npm:font-awesome:${webjarsFontawesomeVersion}"
  runtimeOnly 'com.github.ben-manes.caffeine:caffeine'
  runtimeOnly 'com.h2database:h2'
  runtimeOnly 'com.mysql:mysql-connector-j'
  runtimeOnly 'org.postgresql:postgresql'
  developmentOnly 'org.springframework.boot:spring-boot-devtools'
  testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
  useJUnitPlatform()
}
"""

EXPECTED_FULL_EXAMPLE_GRADLE = f"""
plugins {{
  id 'org.springframework.boot' version '3.0.1'
  id 'io.spring.dependency-management' version '1.1.0'
  id 'java'
  id 'com.google.protobuf' version '{GRADLE_PROTOBUF_PLUGIN_VERSION}'
}}

protobuf {{
    protoc {{ artifact = 'com.google.protobuf:protoc:{PROTOBUF_VERSION}' }}
    plugins {{
        grpc {{
            artifact = 'io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}'
        }}
    }}
    generateProtoTasks {{
        all()*.plugins {{
            grpc {{}}
        }}
    }}
}}

apply plugin: 'java'

group = 'org.springframework.samples'
version = '3.0.0'
sourceCompatibility = '17'

repositories {{
  mavenCentral()
}}

ext.webjarsFontawesomeVersion = "4.7.0"
ext.webjarsBootstrapVersion = "5.1.3"

dependencies {{
  implementation 'org.springframework.boot:spring-boot-starter-cache'
  implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
  implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
  implementation 'org.springframework.boot:spring-boot-starter-web'
  implementation 'org.springframework.boot:spring-boot-starter-validation'
  implementation 'javax.cache:cache-api'
  implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
  runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
  runtimeOnly "org.webjars.npm:bootstrap:${{webjarsBootstrapVersion}}"
  runtimeOnly "org.webjars.npm:font-awesome:${{webjarsFontawesomeVersion}}"
  runtimeOnly 'com.github.ben-manes.caffeine:caffeine'
  runtimeOnly 'com.h2database:h2'
  runtimeOnly 'com.mysql:mysql-connector-j'
  runtimeOnly 'org.postgresql:postgresql'
  developmentOnly 'org.springframework.boot:spring-boot-devtools'
  testImplementation 'org.springframework.boot:spring-boot-starter-test'
  runtimeOnly 'io.grpc:grpc-netty-shaded:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-protobuf:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-stub:{GRPC_VERSION}'
  implementation 'com.google.protobuf:protobuf-java:{PROTOBUF_VERSION}'
  compileOnly 'javax.annotation:javax.annotation-api:{ANNOTATION_API_VERSION}'
}}

tasks.named('test') {{
  useJUnitPlatform()
}}
"""

EXPECTED_FULL_EXAMPLE_GRADLE_SERVER = f"""
plugins {{
  id 'org.springframework.boot' version '3.0.1'
  id 'io.spring.dependency-management' version '1.1.0'
  id 'java'
  id 'com.google.protobuf' version '{GRADLE_PROTOBUF_PLUGIN_VERSION}'
}}

protobuf {{
    protoc {{ artifact = 'com.google.protobuf:protoc:{PROTOBUF_VERSION}' }}
    plugins {{
        grpc {{
            artifact = 'io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}'
        }}
    }}
    generateProtoTasks {{
        all()*.plugins {{
            grpc {{}}
        }}
    }}
}}

apply plugin: 'java'

group = 'org.springframework.samples'
version = '3.0.0'
sourceCompatibility = '17'

repositories {{
  mavenCentral()
}}

ext.webjarsFontawesomeVersion = "4.7.0"
ext.webjarsBootstrapVersion = "5.1.3"

dependencies {{
  implementation 'org.springframework.boot:spring-boot-starter-cache'
  implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
  implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
  implementation 'org.springframework.boot:spring-boot-starter-web'
  implementation 'org.springframework.boot:spring-boot-starter-validation'
  implementation 'javax.cache:cache-api'
  implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
  runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
  runtimeOnly "org.webjars.npm:bootstrap:${{webjarsBootstrapVersion}}"
  runtimeOnly "org.webjars.npm:font-awesome:${{webjarsFontawesomeVersion}}"
  runtimeOnly 'com.github.ben-manes.caffeine:caffeine'
  runtimeOnly 'com.h2database:h2'
  runtimeOnly 'com.mysql:mysql-connector-j'
  runtimeOnly 'org.postgresql:postgresql'
  developmentOnly 'org.springframework.boot:spring-boot-devtools'
  testImplementation 'org.springframework.boot:spring-boot-starter-test'
  runtimeOnly 'io.grpc:grpc-netty-shaded:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-protobuf:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-stub:{GRPC_VERSION}'
  implementation 'com.google.protobuf:protobuf-java:{PROTOBUF_VERSION}'
  compileOnly 'javax.annotation:javax.annotation-api:{ANNOTATION_API_VERSION}'
  implementation 'org.mapstruct:mapstruct:{MAPSTRUCT_VERSION}'
  annotationProcessor 'org.mapstruct:mapstruct-processor:{MAPSTRUCT_VERSION}'
}}

tasks.named('test') {{
  useJUnitPlatform()
}}
"""

EXPECTED_FULL_EXAMPLE_GRADLE_SERVER_WITHOUT_CAFFEINE = f"""
plugins {{
  id 'org.springframework.boot' version '3.0.1'
  id 'io.spring.dependency-management' version '1.1.0'
  id 'java'
  id 'com.google.protobuf' version '{GRADLE_PROTOBUF_PLUGIN_VERSION}'
}}

protobuf {{
    protoc {{ artifact = 'com.google.protobuf:protoc:{PROTOBUF_VERSION}' }}
    plugins {{
        grpc {{
            artifact = 'io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}'
        }}
    }}
    generateProtoTasks {{
        all()*.plugins {{
            grpc {{}}
        }}
    }}
}}

apply plugin: 'java'

group = 'org.springframework.samples'
version = '3.0.0'
sourceCompatibility = '17'

repositories {{
  mavenCentral()
}}

ext.webjarsFontawesomeVersion = "4.7.0"
ext.webjarsBootstrapVersion = "5.1.3"

dependencies {{
  implementation 'org.springframework.boot:spring-boot-starter-cache'
  implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
  implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
  implementation 'org.springframework.boot:spring-boot-starter-web'
  implementation 'org.springframework.boot:spring-boot-starter-validation'
  implementation 'javax.cache:cache-api'
  implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
  runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
  runtimeOnly "org.webjars.npm:bootstrap:${{webjarsBootstrapVersion}}"
  runtimeOnly "org.webjars.npm:font-awesome:${{webjarsFontawesomeVersion}}"
  runtimeOnly 'com.h2database:h2'
  runtimeOnly 'com.mysql:mysql-connector-j'
  runtimeOnly 'org.postgresql:postgresql'
  developmentOnly 'org.springframework.boot:spring-boot-devtools'
  testImplementation 'org.springframework.boot:spring-boot-starter-test'
  runtimeOnly 'io.grpc:grpc-netty-shaded:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-protobuf:{GRPC_VERSION}'
  implementation 'io.grpc:grpc-stub:{GRPC_VERSION}'
  implementation 'com.google.protobuf:protobuf-java:{PROTOBUF_VERSION}'
  compileOnly 'javax.annotation:javax.annotation-api:{ANNOTATION_API_VERSION}'
  implementation 'com.github.ben-manes.caffeine:caffeine:{CAFFEINE_VERSION}'
  implementation 'org.mapstruct:mapstruct:{MAPSTRUCT_VERSION}'
  annotationProcessor 'org.mapstruct:mapstruct-processor:{MAPSTRUCT_VERSION}'
}}

tasks.named('test') {{
  useJUnitPlatform()
}}
"""


FULL_EXAMPLE_POM = """<?xml version='1.0' encoding='utf-8'?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-boot-jpa-example</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>Spring Boot JPA Example</name>
    <description>A simple Spring Boot application with JPA</description>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>2.7.18</version>
        <relativePath /> <!-- lookup parent from repository -->
    </parent>

    <properties>
        <java.version>11</java.version>
    </properties>

    <dependencies>
        <!-- Spring Boot Starter for Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- Spring Boot Starter for JPA -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- H2 Database for Development -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- Lombok for cleaner code (optional) -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- Spring Boot Starter Test -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- javax.persistence dependency -->
        <dependency>
            <groupId>javax.persistence</groupId>
            <artifactId>javax.persistence-api</artifactId>
            <version>2.2</version>
        </dependency>

        <!-- JUnit Jupiter dependency -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.8.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

EXPECTED_FULL_EXAMPLE_POM = f"""<?xml version='1.0' encoding='utf-8'?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-boot-jpa-example</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>Spring Boot JPA Example</name>
    <description>A simple Spring Boot application with JPA</description>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>2.7.18</version>
        <relativePath /> 
        <!-- lookup parent from repository -->
    </parent>

    <properties>
        <java.version>11</java.version>
    </properties>

    <dependencies>
        <!-- Spring Boot Starter for Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- Spring Boot Starter for JPA -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- H2 Database for Development -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- Lombok for cleaner code (optional) -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- Spring Boot Starter Test -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- javax.persistence dependency -->
        <dependency>
            <groupId>javax.persistence</groupId>
            <artifactId>javax.persistence-api</artifactId>
            <version>2.2</version>
        </dependency>

        <!-- JUnit Jupiter dependency -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.8.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-netty-shaded</artifactId>
            <version>{GRPC_VERSION}</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-protobuf</artifactId>
            <version>{GRPC_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-stub</artifactId>
            <version>{GRPC_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>com.google.protobuf</groupId>
            <artifactId>protobuf-java</artifactId>
            <version>{PROTOBUF_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>javax.annotation</groupId>
            <artifactId>javax.annotation-api</artifactId>
            <version>{ANNOTATION_API_VERSION}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <extensions>
            <extension>
                <groupId>kr.motd.maven</groupId>
                <artifactId>os-maven-plugin</artifactId>
                <version>{OS_MAVEN_PLUGIN_VERSION}</version>
            </extension>
        </extensions>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.xolstice.maven.plugins</groupId>
                <artifactId>protobuf-maven-plugin</artifactId>
                <version>{PROTOBUF_MAVEN_PLUGIN_VERSION}</version>
                <configuration>
                    <protocArtifact>com.google.protobuf:protoc:{PROTOBUF_VERSION}:exe:${{os.detected.classifier}}</protocArtifact>
                    <pluginId>grpc-java</pluginId>
                    <pluginArtifact>io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}:exe:${{os.detected.classifier}}</pluginArtifact>
                    <protoSourceRoot>src/main/proto</protoSourceRoot>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>compile</goal>
                            <goal>compile-custom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
"""

EXPECTED_FULL_EXAMPLE_POM_SERVER = f"""<?xml version='1.0' encoding='utf-8'?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-boot-jpa-example</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>Spring Boot JPA Example</name>
    <description>A simple Spring Boot application with JPA</description>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>2.7.18</version>
        <relativePath /> 
        <!-- lookup parent from repository -->
    </parent>

    <properties>
        <java.version>11</java.version>
    </properties>

    <dependencies>
        <!-- Spring Boot Starter for Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- Spring Boot Starter for JPA -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
            <version>2.7.18</version>
        </dependency>

        <!-- H2 Database for Development -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- Lombok for cleaner code (optional) -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- Spring Boot Starter Test -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- javax.persistence dependency -->
        <dependency>
            <groupId>javax.persistence</groupId>
            <artifactId>javax.persistence-api</artifactId>
            <version>2.2</version>
        </dependency>

        <!-- JUnit Jupiter dependency -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.8.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-netty-shaded</artifactId>
            <version>{GRPC_VERSION}</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-protobuf</artifactId>
            <version>{GRPC_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-stub</artifactId>
            <version>{GRPC_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>com.google.protobuf</groupId>
            <artifactId>protobuf-java</artifactId>
            <version>{PROTOBUF_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>javax.annotation</groupId>
            <artifactId>javax.annotation-api</artifactId>
            <version>{ANNOTATION_API_VERSION}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>{CAFFEINE_VERSION}</version>
        </dependency>
        <dependency>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct</artifactId>
            <version>{MAPSTRUCT_VERSION}</version>
        </dependency>
    </dependencies>

    <build>
        <extensions>
            <extension>
                <groupId>kr.motd.maven</groupId>
                <artifactId>os-maven-plugin</artifactId>
                <version>{OS_MAVEN_PLUGIN_VERSION}</version>
            </extension>
        </extensions>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.xolstice.maven.plugins</groupId>
                <artifactId>protobuf-maven-plugin</artifactId>
                <version>{PROTOBUF_MAVEN_PLUGIN_VERSION}</version>
                <configuration>
                    <protocArtifact>com.google.protobuf:protoc:{PROTOBUF_VERSION}:exe:${{os.detected.classifier}}</protocArtifact>
                    <pluginId>grpc-java</pluginId>
                    <pluginArtifact>io.grpc:protoc-gen-grpc-java:{GRPC_VERSION}:exe:${{os.detected.classifier}}</pluginArtifact>
                    <protoSourceRoot>src/main/proto</protoSourceRoot>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>compile</goal>
                            <goal>compile-custom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>{MAVEN_COMPILER_PLUGIN_VERSION}</version>
                <configuration>
                    <source>{{java_version}}</source>
                    <target>{{java_version}}</target>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.mapstruct</groupId>
                            <artifactId>mapstruct-processor</artifactId>
                            <version>{MAPSTRUCT_VERSION}</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
"""





