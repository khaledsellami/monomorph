DEFAULT_DOCKER_WORKDIR = "/app"

CONTAINER_TEMPLATE: str = """
{base_image_line}

WORKDIR {default_workdir}

# Copy the entire project context into the container
COPY . .

# Try to delete the .git directory if it exists
RUN rm -rf .git || true

# Create a new git repository and add user details
RUN git init && \
    git config --global user.name "Monomorph" && \
    git config --global user.email "monomoprh@notarealemaildonotuse.com"

# Apply the first commit to the repository
RUN git add -A && \
    git commit -m "Initial commit"

{entrypoint_script}
"""

CONTAINER_TEMPLATE_RESUME: str = """
{base_image_line}

WORKDIR {default_workdir}

# Copy the entire project context into the container
COPY . .

# No need to setup a new git repository, just ensure the .git directory is present and raise an error if it is not
RUN if [ ! -d ".git" ]; then echo "Error: .git directory not found. This is required for resuming the build."; exit 1; fi

# Configure git user details
RUN git config --global user.name "Monomorph" && \
    git config --global user.email "monomoprh@notarealemaildonotuse.com"

# Apply a commit to ensure the new changes are tracked
RUN git add -A && \
    git commit -m "Before resuming build" || true

{entrypoint_script}
"""

DEFAULT_DOCKER_IMAGES = {
    "maven": "maven:3.8.5-openjdk-17-slim",
    "gradle": "gradle:7.4.2-jdk17-jammy"
}

# Keep container running with interactive shell
DEFAULT_ENTYPOINT_SCRIPT = 'CMD ["tail", "-f", "/dev/null"]'
