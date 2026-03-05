FROM mcr.microsoft.com/devcontainers/python:3.13

# Install Node.js (required at runtime by Claude CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs

# Install Bun and Claude CLI as the vscode user
USER vscode
RUN curl -fsSL https://bun.sh/install | bash \
    && /home/vscode/.bun/bin/bun install -g @anthropic-ai/claude-code
ENV PATH="/home/vscode/.bun/bin:${PATH}"
USER root
