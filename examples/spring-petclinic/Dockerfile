# Build stage - using official Maven image with Java 8
FROM maven:3.8.5-openjdk-17 AS build

# Set working directory
WORKDIR /app

# Copy pom.xml for dependency resolution
COPY pom.xml .

# Download dependencies - this will be cached unless pom.xml changes
RUN mvn dependency:go-offline -B

# Copy source code
COPY src ./src

# Build the application (but don't run tests yet)
RUN mvn package -DskipTests -B

# Test stage
FROM build AS test

# Create a helper script that makes it easy to run specific tests
RUN echo '#!/bin/bash\n\
if [ "$1" = "" ]; then\n\
  # Run all tests by default\n\
  mvn test -B\n\
else\n\
  # Run specific tests with the passed arguments\n\
  mvn test -B -Dtest="$@"\n\
fi' > /app/run-tests.sh && \
chmod +x /app/run-tests.sh

# Default to running all tests
ENTRYPOINT ["/app/run-tests.sh"]